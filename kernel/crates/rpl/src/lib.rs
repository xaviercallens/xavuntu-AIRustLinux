#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::ptr;
use kernel_types::*;

const IPV6_RPL_BEST_ADDR_COMPRESSION: u8 = 15;

// Type definitions

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_rpl_sr_hdr {
    pub nexthdr: u8,
    pub hdrlen: u8,
    pub pad: u8,
    pub rsvd: u8,
    pub type_: u8,
    pub segments_left: u8,
    pub cmpri: u8,
    pub cmpre: u8,
    pub rpl_segaddr: [in6_addr; 1],
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

#[no_mangle]
pub unsafe extern "C" fn rust_eh_personality() {}

#[no_mangle]
pub unsafe extern "C" fn ipv6_rpl_addr_decompress(
    dst: *mut in6_addr,
    daddr: *const in6_addr,
    post: *const c_void,
    pfx: u8,
) {
    // SAFETY: Caller guarantees valid pointers and pfx <= 16
    if pfx > 16 {
        return;
    }

    let dst_ptr = dst as *mut u8;
    let daddr_ptr = daddr as *const u8;
    let post_ptr = post as *const u8;

    ptr::copy_nonoverlapping(daddr_ptr, dst_ptr, pfx as usize);
    let dst_post = dst_ptr.add(pfx as usize);
    let tail_len = (16 - pfx) as usize;
    ptr::copy_nonoverlapping(post_ptr, dst_post, tail_len);
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_rpl_addr_compress(
    dst: *mut c_void,
    addr: *const in6_addr,
    pfx: u8,
) {
    // SAFETY: Caller guarantees valid pointers and pfx <= 16
    if pfx > 16 {
        return;
    }

    let src = (addr as *const u8).add(pfx as usize);
    ptr::copy_nonoverlapping(src, dst as *mut u8, (16 - pfx) as usize);
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_rpl_segdata_pos(
    hdr: *const ipv6_rpl_sr_hdr,
    i: c_int,
) -> *mut c_void {
    if hdr.is_null() {
        return ptr::null_mut();
    }

    let cmpri = (*hdr).cmpri;
    let offset = i as usize * (16 - cmpri as usize);
    // SAFETY: hdr is valid and points to a valid ipv6_rpl_sr_hdr
    ((hdr as *const u8).add(core::mem::size_of::<ipv6_rpl_sr_hdr>() + offset)) as *mut c_void
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_rpl_srh_size(
    n: u8,
    cmpri: u8,
    cmpre: u8,
) -> size_t {
    if cmpri > 16 || cmpre > 16 {
        return 0;
    }

    let seg_len = (n as usize * (16 - cmpri as usize)) + (16 - cmpre as usize);
    seg_len as size_t
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_rpl_srh_decompress(
    outhdr: *mut ipv6_rpl_sr_hdr,
    inhdr: *const ipv6_rpl_sr_hdr,
    daddr: *const in6_addr,
    n: u8,
) {
    if outhdr.is_null() || inhdr.is_null() || daddr.is_null() {
        return;
    }

    let outhdr = &mut *outhdr;
    let inhdr = &*inhdr;

    outhdr.nexthdr = inhdr.nexthdr;
    outhdr.hdrlen = (((n + 1) * 16) >> 3) as u8;
    outhdr.pad = 0;
    outhdr.type_ = inhdr.type_;
    outhdr.segments_left = inhdr.segments_left;
    outhdr.cmpri = 0;
    outhdr.cmpre = 0;

    for i in 0..n {
        let dst = &mut outhdr.rpl_segaddr[i as usize];
        let post = ipv6_rpl_segdata_pos(inhdr as *const _, i as c_int);
        if post.is_null() {
            continue;
        }
        ipv6_rpl_addr_decompress(dst as *mut _, daddr, post, inhdr.cmpri);
    }

    let dst = &mut outhdr.rpl_segaddr[n as usize];
    let post = ipv6_rpl_segdata_pos(inhdr as *const _, n as c_int);
    if !post.is_null() {
        ipv6_rpl_addr_decompress(dst as *mut _, daddr, post, inhdr.cmpre);
    }
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_rpl_srh_compress(
    outhdr: *mut ipv6_rpl_sr_hdr,
    inhdr: *const ipv6_rpl_sr_hdr,
    daddr: *const in6_addr,
    n: u8,
) {
    if outhdr.is_null() || inhdr.is_null() || daddr.is_null() {
        return;
    }

    let inhdr = &*inhdr;
    let mut cmpri = 0;
    let mut cmpre = 0;

    // Calculate compression values
    for plen in 0..16 {
        let mut mismatch = false;
        for i in 0..n {
            if (*daddr).in6_u.u6_addr8[plen] != inhdr.rpl_segaddr[i as usize].in6_u.u6_addr8[plen] {
                cmpri = plen as u8;
                mismatch = true;
                break;
            }
        }
        if mismatch {
            break;
        }
        if plen == 15 {
            cmpri = 16;
        }
    }

    for plen in 0..16 {
        if (*daddr).in6_u.u6_addr8[plen] != inhdr.rpl_segaddr[n as usize].in6_u.u6_addr8[plen] {
            cmpre = plen as u8;
            break;
        }
    }

    let outhdr = &mut *outhdr;
    outhdr.nexthdr = inhdr.nexthdr;
    let seg_len = (n as usize * (16 - cmpri as usize)) + (16 - cmpre as usize);
    outhdr.hdrlen = (seg_len >> 3) as u8;

    if seg_len & 0x7 != 0 {
        outhdr.hdrlen += 1;
        outhdr.pad = (8 - (seg_len & 0x7)) as u8;
    } else {
        outhdr.pad = 0;
    }

    outhdr.type_ = inhdr.type_;
    outhdr.segments_left = inhdr.segments_left;
    outhdr.cmpri = cmpri;
    outhdr.cmpre = cmpre;

    for i in 0..n {
        let pos = ipv6_rpl_segdata_pos(outhdr as *mut _, i as c_int);
        if !pos.is_null() {
            ipv6_rpl_addr_compress(pos, &inhdr.rpl_segaddr[i as usize], cmpri);
        }
    }

    let pos = ipv6_rpl_segdata_pos(outhdr as *mut _, n as c_int);
    if !pos.is_null() {
        ipv6_rpl_addr_compress(pos, &inhdr.rpl_segaddr[n as usize], cmpre);
    }
}

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    use super::*;
    use core::ptr;

    #[test]
    fn test_address_compression() {
        let mut dst = in6_addr { in6_u: in6_addr_union { u6_addr8: [0; 16] } };
        let daddr = in6_addr {
            in6_u: in6_addr_union { u6_addr8: [1; 16] },
        };
        let post = [2; 16];
        unsafe {
            ipv6_rpl_addr_decompress(&mut dst as *mut _, &daddr as *const _, post.as_ptr() as *const _, 8);
            assert_eq!(dst.in6_u.u6_addr8[0..8], [1; 8]);
            assert_eq!(dst.in6_u.u6_addr8[8..], [2; 8]);
        }
    }
}
