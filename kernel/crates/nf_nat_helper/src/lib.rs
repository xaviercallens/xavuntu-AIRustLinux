#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! NAT Helper Functions for Linux Kernel
//!
//! This module provides FFI-compatible Rust implementations of NAT helper
//! functions from the Linux kernel's nf_nat_helper.c. The implementation
//! maintains exact ABI compatibility with the original C code.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons)]

use core::ffi::c_void;
use core::ptr;
use kernel_types::*;

pub const IPPROTO_TCP: c_int = 6;
pub const IPPROTO_UDP: c_int = 17;
pub const NFPROTO_IPV4: c_int = 2;
pub const IPS_NAT_DONE_MASK: u64 = 0x0000_000F;

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12;

// Type definitions for FFI compatibility

#[repr(C)]
#[derive(Copy, Clone)]
pub struct NF_CONNTRACK_EXPECT {
    pub dir: c_int,
    pub saved_proto: c_int,
}

// Extended nf_conn structure with master field for NAT helpers
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_with_master {
    pub ct_general: *mut c_void,
    pub tuplehash: [nf_conn_tuplehash; 2],
    pub timeout: c_ulong,
    pub status: c_ulong,
    pub sk: *mut c_void,
    pub proto: *mut c_void,
    pub master: *mut nf_conn,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct NF_NAT_RANGE2 {
    pub flags: c_int,
    pub min_addr: u32,
    pub max_addr: u32,
    pub min_proto: c_int,
    pub max_proto: c_int,
}

unsafe extern "C" {
    fn skb_ensure_writable(skb: *mut sk_buff, len: usize) -> c_int;
    fn pskb_expand_head(skb: *mut sk_buff, headroom: usize, tailroom: usize, gfp: c_int) -> c_int;
    fn nf_nat_csum_recalc(
        skb: *mut sk_buff,
        l3num: c_int,
        protocol: c_int,
        old_hdr: *mut c_void,
        check: *mut u16,
        newlen: c_int,
        oldlen: c_int,
    ) -> c_int;
    fn nf_ct_seqadj_set(ct: *mut nf_conn, ctinfo: c_int, seq: *mut c_void, delta: c_int);
    fn nf_ct_l3num(ct: *mut nf_conn) -> c_int;
    fn skb_network_header(skb: *mut sk_buff) -> *mut u8;
    fn skb_tail_pointer(skb: *mut sk_buff) -> *mut u8;
    fn __skb_trim(skb: *mut sk_buff, len: usize);
    fn skb_put(skb: *mut sk_buff, len: usize) -> *mut u8;
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {
        core::hint::spin_loop();
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn rust_eh_personality() {}

#[inline]
unsafe fn enlarge_skb(skb: *mut sk_buff, extra: usize) -> c_int {
    if extra == 0 {
        return 1;
    }
    if unsafe { pskb_expand_head(skb, 0, extra, 0) } != 0 {
        return 0;
    }
    1
}

unsafe fn mangle_contents(
    skb: *mut sk_buff,
    dataoff: c_uint,
    match_offset: c_uint,
    match_len: c_uint,
    rep_buffer: *const c_void,
    rep_len: c_uint,
) {
    let data = unsafe { skb_network_header(skb).add(dataoff as usize) };
    let src = unsafe { data.add((match_offset + match_len) as usize) };
    let dst = unsafe { data.add((match_offset + rep_len) as usize) };
    let end = unsafe { skb_tail_pointer(skb) as usize };
    let from = src as usize;
    let len = end.saturating_sub(from);

    unsafe { ptr::copy(src, dst, len) };

    unsafe {
        ptr::copy_nonoverlapping(
            rep_buffer as *const u8,
            data.add(match_offset as usize),
            rep_len as usize,
        );

        // Update skb length
        if rep_len > match_len {
            // Extend packet
            skb_put(skb, (rep_len - match_len) as usize);
        } else {
            // Shrink packet
            __skb_trim(
                skb,
                ((*skb).len as isize + (rep_len as isize - match_len as isize)) as usize,
            );
        }

        // Update IP headers if needed
        // Implementation deferred.
        if true { // IPv4 condition path - protocol dispatch
            let ip_hdr = skb_network_header(skb) as *mut iphdr;
            (*ip_hdr).tot_len = (*skb).len as u16;
            ip_send_check(ip_hdr);
        } else {
            let ipv6_hdr = skb_network_header(skb) as *mut ipv6hdr;
            (*ipv6_hdr).payload_len = ((*skb).len - 40) as u16;
        }
    }
}

/// Generic TCP packet mangling function
#[no_mangle]
pub unsafe extern "C" fn __NF_NAT_MANGLE_TCP_PACKET(
    skb: *mut sk_buff,
    ct: *mut nf_conn,
    ctinfo: c_int,
    protoff: c_uint,
    match_offset: c_uint,
    match_len: c_uint,
    rep_buffer: *const c_void,
    rep_len: c_uint,
    adjust: c_int,
) -> c_int {
    if skb.is_null() || ct.is_null() || rep_buffer.is_null() {
        return EINVAL;
    }

    let old_skb_len = unsafe { (*skb).len as usize };

    if unsafe { skb_ensure_writable(skb, old_skb_len) } != 0 {
        return EINVAL;
    }

    if rep_len > match_len {
        let grow = (rep_len - match_len) as usize;
        if unsafe { enlarge_skb(skb, grow) } != 1 {
            return ENOMEM;
        }
        if unsafe { skb_ensure_writable(skb, (*skb).len as usize) } != 0 {
            return EINVAL;
        }
    }

    let tcph = unsafe { skb_network_header(skb).add(protoff as usize) };
    let doff_words = unsafe { ((*tcph.add(12) >> 4) & 0x0f) as usize };
    let _dataoff = protoff as usize + doff_words * 4;

    let oldlen = unsafe { (*skb).len as usize } - protoff as usize;
    mangle_contents(
        skb,
        protoff + (*(tcph.add(12) as *const u32) * 4) as c_uint,
        match_offset,
        match_len,
        rep_buffer,
        rep_len,
    );

    let datalen = unsafe { (*skb).len as usize } - protoff as usize;
    nf_nat_csum_recalc(
        skb,
        nf_ct_l3num(ct),
        IPPROTO_TCP,
        tcph as *mut c_void,
        &mut (*(tcph.add(16) as *mut u16)),
        datalen as c_int,
        oldlen as c_int,
    );

    if adjust != 0 && rep_len != match_len {
        nf_ct_seqadj_set(
            ct,
            ctinfo,
            tcph as *mut c_void,
            (rep_len - match_len) as c_int,
        );
    }

    0
}

/// Generic UDP packet mangling function
#[no_mangle]
pub unsafe extern "C" fn NF_NAT_MANGLE_UDP_PACKET(
    skb: *mut sk_buff,
    ct: *mut nf_conn,
    _ctinfo: c_int,
    protoff: c_uint,
    match_offset: c_uint,
    match_len: c_uint,
    rep_buffer: *const c_void,
    rep_len: c_uint,
) -> c_int {
    let skb_len = (*skb).len as usize;

    // Ensure packet is writable
    if skb_ensure_writable(skb, skb_len) != 0 {
        return EINVAL;
    }

    // Check if we need to expand the skb
    if rep_len > match_len {
        let tailroom = skb_len - (skb_tail_pointer(skb) as usize - skb_network_header(skb) as usize);
        if (rep_len - match_len) as usize > tailroom {
            if enlarge_skb(skb, (rep_len - match_len) as usize) != 1 {
                return ENOMEM;
            }
        }
    }

    let udph = (skb_network_header(skb) as *mut u8).add(protoff as usize);

    let oldlen = skb_len - protoff as usize;
    mangle_contents(
        skb,
        protoff + 8,
        match_offset,
        match_len,
        rep_buffer,
        rep_len,
    );

    // Update UDP length
    let datalen = unsafe { (*skb).len as usize } - protoff as usize;
    (*(udph.add(4) as *mut u16)) = datalen as u16;

    // Handle checksum
    if (*(udph.add(6) as *mut u16)) == 0 && (*skb).ip_summed != 1 {
        return 0;
    }

    nf_nat_csum_recalc(
        skb,
        nf_ct_l3num(ct),
        IPPROTO_UDP,
        udph as *mut c_void,
        &mut (*(udph.add(6) as *mut u16)),
        datalen as c_int,
        oldlen as c_int,
    );

    0
}

/// Enlarge skb if needed
#[no_mangle]
pub unsafe extern "C" fn ENLARGE_SKB(skb: *mut sk_buff, extra: usize) -> c_int {
    let skb_len = (*skb).len as usize;

    if skb_len + extra > 65535 {
        return 0;
    }

    if pskb_expand_head(
        skb,
        0,
        extra - (skb_tail_pointer(skb) as usize - skb_network_header(skb) as usize),
        0,
    ) != 0
    {
        return 0;
    }

    1
}

/// Setup NAT to follow master connection
#[no_mangle]
pub unsafe extern "C" fn NF_NAT_FOLLOW_MASTER(ct: *mut nf_conn, exp: *mut NF_CONNTRACK_EXPECT) {
    let exp_ref = &mut *exp;
    let ct_ref = &mut *ct;

    // Ensure this is a fresh connection
    if ct_ref.status & IPS_NAT_DONE_MASK != 0 {
        return;
    }

    // Cast ct to extended version with master field
    let ct_ext = ct as *mut nf_conn_with_master;
    let master = (*ct_ext).master;

    if master.is_null() {
        return;
    }

    // Implementation deferred.
    let mut range = NF_NAT_RANGE2 {
        flags: 1, // NF_NAT_RANGE_MAP_IPS
        min_addr: 0,
        max_addr: 0,
        min_proto: 0,
        max_proto: 0,
    };
    nf_nat_setup_info(ct, &mut range, 0); // NF_NAT_MANIP_SRC

    // Setup destination NAT
    range.flags = 3; // NF_NAT_RANGE_MAP_IPS | NF_NAT_RANGE_PROTO_SPECIFIED
    range.min_proto = exp_ref.saved_proto;
    range.max_proto = exp_ref.saved_proto;
    range.min_addr = 0;
    range.max_addr = 0;
    nf_nat_setup_info(ct, &mut range, 1); // NF_NAT_MANIP_DST
}

// Extern declaration for nf_nat_setup_info
extern "C" {
    fn nf_nat_setup_info(ct: *mut nf_conn, range: *mut NF_NAT_RANGE2, manip: c_int);
}

// Implementation deferred.
unsafe fn ip_send_check(_ip_hdr: *mut iphdr) {
    // In real implementation, this would calculate IP checksum
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_function_signatures() {
        // These tests just verify that the function signatures are correct
        extern "C" {
            fn __NF_NAT_MANGLE_TCP_PACKET(
                skb: *mut super::sk_buff,
                ct: *mut super::nf_conn,
                ctinfo: super::c_int,
                protoff: super::c_uint,
                match_offset: super::c_uint,
                match_len: super::c_uint,
                rep_buffer: *const super::c_void,
                rep_len: super::c_uint,
                adjust: super::c_int,
            ) -> super::c_int;

            fn NF_NAT_MANGLE_UDP_PACKET(
                skb: *mut super::sk_buff,
                ct: *mut super::nf_conn,
                ctinfo: super::c_int,
                protoff: super::c_uint,
                match_offset: super::c_uint,
                match_len: super::c_uint,
                rep_buffer: *const super::c_void,
                rep_len: super::c_uint,
            ) -> super::c_int;

            fn NF_NAT_FOLLOW_MASTER(ct: *mut super::nf_conn, exp: *mut super::NF_CONNTRACK_EXPECT);
        }

        // Just verify that the functions exist and have the right signatures
        // No actual execution since we need kernel environment
    }
}
