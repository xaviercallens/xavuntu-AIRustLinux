#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons)]
use core::{ffi::{c_int, c_void}, mem::size_of};
use kernel_types::*;

// Error codes from errno.h
pub const EINVAL: c_int = -22;
pub const ENOMSG: c_int = -96;
pub const ENODATA: c_int = -61;
pub const ENOMEM: c_int = -12;

// Constants from C
pub const IPPROTO_HOPOPTS: u8 = 0;
pub const IPPROTO_ICMPV6: u8 = 58;
pub const ICMPV6_MGM_REDUCTION: u8 = 143;
pub const ICMPV6_MGM_REPORT: u8 = 137;
pub const ICMPV6_MLD2_REPORT: u8 = 144;
pub const ICMPV6_MGM_QUERY: u8 = 138;
pub const IPV6_ADDR_MULTICAST: c_int = 0x0010;

// Kernel function declarations
extern "C" {
    fn pskb_may_pull(skb: *mut sk_buff, len: c_int) -> c_int;
    fn skb_network_offset(skb: *mut sk_buff) -> c_int;
    fn ipv6_hdr(skb: *mut sk_buff) -> *const ipv6hdr;
    fn skb_set_transport_header(skb: *mut sk_buff, offset: c_int);
    fn skb_transport_header(skb: *const sk_buff) -> *mut u8;
    fn ipv6_skip_exthdr(
        skb: *mut sk_buff,
        offset: c_int,
        nexthdr: *mut u8,
        frag_off: *mut u16,
    ) -> c_int;
    fn ipv6_transport_len(skb: *mut sk_buff) -> c_int;
    fn ipv6_addr_type(addr: *const in6_addr) -> c_int;
    fn ipv6_addr_any(addr: *const in6_addr) -> c_int;
    fn ipv6_addr_is_ll_all_nodes(addr: *const in6_addr) -> c_int;
    fn ipv6_mc_may_pull(skb: *mut sk_buff, len: c_int) -> c_int;
    fn skb_checksum_trimmed(
        skb: *mut sk_buff,
        transport_len: c_int,
        validate: extern "C" fn(*mut sk_buff) -> u16,
    ) -> *mut sk_buff;
    fn kfree_skb(skb: *mut sk_buff);
    fn ntohs(netshort: __be16) -> __u16;
}

// Type definitions
#[repr(C)]
#[derive(Copy, Clone)]
pub struct mld_msg {
    mld_type: u8,
    mld_code: u8,
    mld_checksum: u16,
    mld_mca: in6_addr,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct mld2_query {
    mld2q_type: u8,
    mld2q_resv1: u8,
    mld2q_maxdelay: u16,
    mld2q_mindelay: u16,
    mld2q_code: u16,
    mld2q_mca: in6_addr,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct mld2_report {
    mld2r_type: u8,
    mld2r_resv1: u8,
    mld2r_resv2: u16,
    mld2r_num: u32,
}

#[inline]
fn ipv6_transport_header(skb: *mut sk_buff) -> *const c_void {
    unsafe { skb_transport_header(skb as *const sk_buff) as *const c_void }
}

fn ipv6_mc_check_ip6hdr(skb: *mut sk_buff) -> c_int {
    let offset = unsafe { skb_network_offset(skb) } + size_of::<ipv6hdr>() as c_int;
    if unsafe { pskb_may_pull(skb, offset) } == 0 {
        return EINVAL;
    }

    let ip6h = unsafe { ipv6_hdr(skb) };
    let version = unsafe { (*ip6h).version_priority };
    if ((version & 0xF0) >> 4) != 6 {
        return EINVAL;
    }

    let payload_len = unsafe { ntohs((*ip6h).payload_len) } as c_int;
    let len = offset + payload_len;
    if unsafe { (*skb).len as c_int } < len || len <= offset {
        return EINVAL;
    }

    unsafe { skb_set_transport_header(skb, offset) };
    0
}

fn ipv6_mc_check_exthdrs(skb: *mut sk_buff) -> c_int {
    let ip6h = unsafe { ipv6_hdr(skb) };
    let mut nexthdr = IPPROTO_HOPOPTS;
    let offset = unsafe { skb_network_offset(skb) } + size_of::<ipv6hdr>() as c_int;

    if unsafe { (*ip6h).nexthdr } != IPPROTO_HOPOPTS {
        return ENOMSG;
    }

    let mut frag_off: u16 = 0;
    let new_offset = unsafe { ipv6_skip_exthdr(skb, offset, &mut nexthdr, &mut frag_off) };
    if new_offset < 0 {
        return EINVAL;
    }

    if nexthdr != IPPROTO_ICMPV6 {
        return ENOMSG;
    }

    unsafe { skb_set_transport_header(skb, new_offset) };
    0
}

fn ipv6_mc_check_mld_reportv2(skb: *mut sk_buff) -> c_int {
    let len = unsafe { ipv6_transport_len(skb) };
    let required_len = len + size_of::<mld2_report>() as c_int;

    if unsafe { ipv6_mc_may_pull(skb, required_len) } == 0 {
        return EINVAL;
    }

    0
}

fn ipv6_mc_check_mld_query(skb: *mut sk_buff) -> c_int {
    let transport_len = unsafe { ipv6_transport_len(skb) };
    let ip6h = unsafe { ipv6_hdr(skb) };

    if (unsafe { ipv6_addr_type(&(*ip6h).daddr) } & IPV6_ADDR_MULTICAST) == 0 {
        return EINVAL;
    }

    if transport_len != size_of::<mld_msg>() as c_int {
        if transport_len < size_of::<mld2_query>() as c_int {
            return EINVAL;
        }

        let len = transport_len + size_of::<mld2_query>() as c_int;
        if unsafe { ipv6_mc_may_pull(skb, len) } == 0 {
            return EINVAL;
        }
    }

    let mld = unsafe { skb_transport_header(skb as *const _) as *const mld_msg };
    let mld_mca = unsafe { &(*mld).mld_mca };

    if unsafe { ipv6_addr_any(mld_mca) } != 0
        && unsafe { ipv6_addr_is_ll_all_nodes(&(*ip6h).daddr) } == 0
    {
        return EINVAL;
    }

    0
}

fn ipv6_mc_check_mld_msg(skb: *mut sk_buff) -> c_int {
    let len = unsafe { ipv6_transport_len(skb) } + size_of::<mld_msg>() as c_int;

    if unsafe { ipv6_mc_may_pull(skb, len) } == 0 {
        return ENODATA;
    }

    let mld = unsafe { skb_transport_header(skb as *const _) as *const mld_msg };
    let mld_type = unsafe { (*mld).mld_type };

    match mld_type {
        ICMPV6_MGM_REDUCTION | ICMPV6_MGM_REPORT => 0,
        ICMPV6_MLD2_REPORT => ipv6_mc_check_mld_reportv2(skb),
        ICMPV6_MGM_QUERY => ipv6_mc_check_mld_query(skb),
        _ => ENOMSG,
    }
}

#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
