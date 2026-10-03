#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! This module provides FFI-compatible Rust bindings for the Linux kernel's
//! nf_conntrack_proto_icmp implementation. It handles ICMP protocol-specific
//! connection tracking logic for netfilter.
//!
//! The implementation maintains ABI compatibility with the original C code and
//! uses raw pointers and unsafe operations where necessary to match the kernel's
//! low-level interface.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(clippy::transmutes_expressible_as_ptr_cast)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons)]

use core::ffi::{c_int, c_uint, c_void};
use kernel_types::*;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOSYS: c_int = -38;
pub const NF_ACCEPT: c_int = 1;
pub const NF_DROP: c_int = 0;
pub const HZ: c_int = 100;

pub const ICMP_ECHO: u8 = 8;
pub const ICMP_ECHOREPLY: u8 = 0;
pub const ICMP_TIMESTAMP: u8 = 13;
pub const ICMP_TIMESTAMPREPLY: u8 = 14;
pub const ICMP_INFO_REQUEST: u8 = 15;
pub const ICMP_INFO_REPLY: u8 = 16;
pub const ICMP_ADDRESS: u8 = 17;
pub const ICMP_ADDRESSREPLY: u8 = 18;
pub const NR_ICMP_TYPES: u8 = 18;

pub const NFPROTO_IPV4: u8 = 2;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct icmp_echo { pub id: u16, pub sequence: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct icmp_ipv4 { pub gateway: u32 }

#[repr(C)]
#[derive(Copy, Clone)]
pub union icmp_un {
    pub echo: icmp_echo,
    pub ipv4: icmp_ipv4,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct icmphdr {
    pub type_: u8,
    pub code: u8,
    pub checksum: u16,
    pub un: icmp_un,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_icmp {
    pub id: u16,
    pub type_: u8,
    pub code: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_u3 { pub ip: u32 }

#[repr(C)]
#[derive(Copy, Clone)]
pub union nf_conntrack_tuple_u {
    pub icmp: nf_conntrack_tuple_icmp,
    pub u3: nf_conntrack_tuple_u3,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_src { pub u: nf_conntrack_tuple_u }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_dst { pub u: nf_conntrack_tuple_u }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple { pub src: nf_conntrack_tuple_src, pub dst: nf_conntrack_tuple_dst }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_hash { pub tuple: nf_conntrack_tuple }

#[repr(C)]
pub struct nf_conn { pub tuplehash: [nf_conntrack_tuple_hash; 2] }

// Static data
pub static INV_MAP: [u8; 256] = {
    let mut arr = [0u8; 256];
    arr[ICMP_ECHO as usize] = ICMP_ECHOREPLY + 1;
    arr[ICMP_ECHOREPLY as usize] = ICMP_ECHO + 1;
    arr[ICMP_TIMESTAMP as usize] = ICMP_TIMESTAMPREPLY + 1;
    arr[ICMP_TIMESTAMPREPLY as usize] = ICMP_TIMESTAMP + 1;
    arr[ICMP_INFO_REQUEST as usize] = ICMP_INFO_REPLY + 1;
    arr[ICMP_INFO_REPLY as usize] = ICMP_INFO_REQUEST + 1;
    arr[ICMP_ADDRESS as usize] = ICMP_ADDRESSREPLY + 1;
    arr[ICMP_ADDRESSREPLY as usize] = ICMP_ADDRESS + 1;
    arr
};

#[no_mangle]
pub unsafe extern "C" fn icmp_pkt_to_tuple(
    skb: *const sk_buff,
    dataoff: c_uint,
    _net: *mut c_void,
    tuple: *mut nf_conntrack_tuple,
) -> bool {
    let mut _hdr: icmphdr = core::mem::zeroed();
    let hp = skb_header_pointer(skb, dataoff, core::mem::size_of_val(&_hdr) as c_uint, &mut _hdr as *mut _ as *mut c_void);

    if hp.is_null() {
        return false;
    }

    let hp = hp.cast::<icmphdr>();

    (*tuple).dst.u.icmp.type_ = (*hp).type_;
    (*tuple).src.u.icmp.id = (*hp).un.echo.id;
    (*tuple).dst.u.icmp.code = (*hp).code;

    true
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_invert_icmp_tuple(
    tuple: *mut nf_conntrack_tuple,
    orig: *const nf_conntrack_tuple,
) -> bool {
    let orig_type = (*orig).dst.u.icmp.type_;

    if orig_type >= INV_MAP.len() as u8 || INV_MAP[orig_type as usize] == 0 {
        return false;
    }

    (*tuple).src.u.icmp.id = (*orig).src.u.icmp.id;
    (*tuple).dst.u.icmp.type_ = INV_MAP[orig_type as usize] - 1;
    (*tuple).dst.u.icmp.code = (*orig).dst.u.icmp.code;

    true
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_icmp_packet(
    ct: *mut nf_conn,
    _skb: *mut sk_buff,
    _ctinfo: c_int,
    state: *const nf_hook_state,
) -> c_int {
    if (*state).pf != NFPROTO_IPV4 {
        return -NF_ACCEPT;
    }

    let tuple = &(*ct).tuplehash[0].tuple;
    let type_ = tuple.dst.u.icmp.type_;

    if type_ >= VALID_NEW.len() as u8 || VALID_NEW[type_ as usize] == 0 {
        return -NF_ACCEPT;
    }

    NF_ACCEPT
}

/// Handles ICMP error messages for connection tracking
///
/// # Safety
/// - `skb` must be a valid pointer to sk_buff
/// - `state` must be a valid pointer to nf_hook_state
#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_icmpv4_error(
    _tmpl: *mut nf_conn,
    skb: *mut sk_buff,
    dataoff: c_uint,
    state: *const nf_hook_state,
) -> c_int {
    let mut outer_daddr: nf_inet_addr = core::mem::zeroed();
    let mut _ih: icmphdr = core::mem::zeroed();
    let icmph = skb_header_pointer(skb, dataoff, core::mem::size_of_val(&_ih) as c_uint, &mut _ih as *mut _ as *mut c_void);

    if icmph.is_null() {
        icmp_error_log(skb, state, b"short packet\0".as_ptr() as *const c_char);
        return -NF_ACCEPT;
    }

    let icmph = icmph as *const icmphdr;

    if (*icmph).type_ > NR_ICMP_TYPES {
        icmp_error_log(skb, state, b"invalid icmp type\0".as_ptr() as *const c_char);
        return -NF_ACCEPT;
    }

    if !icmp_is_err((*icmph).type_) {
        return NF_ACCEPT;
    }

    outer_daddr.ip = (*ip_hdr(skb)).daddr;

    let new_dataoff = dataoff + core::mem::size_of::<icmphdr>() as c_uint;

    extern "C" {
        fn nf_conntrack_inet_error(_tmpl: *mut nf_conn, skb: *const sk_buff, dataoff: c_uint,
                                   state: *const nf_hook_state, proto: c_int,
                                   outer_daddr: *const nf_inet_addr) -> c_int;
    }
    nf_conntrack_inet_error(_tmpl, skb, new_dataoff, state, IPPROTO_ICMP as c_int, &outer_daddr as *const _)
}

// Helper functions (these would be implemented in the kernel)
#[link(name = "kernel")]
extern "C" {
    fn skb_header_pointer(skb: *const sk_buff,
                         offset: c_uint,
                         size: c_uint,
                         data: *mut c_void) -> *mut c_void;
    fn ip_hdr(skb: *const sk_buff) -> *const iphdr;
    fn nf_ct_timeout_lookup(ct: *mut nf_conn) -> *mut c_uint;
    fn nf_ct_refresh_acct(ct: *mut nf_conn, ctinfo: c_int, skb: *mut sk_buff, timeout: c_uint);
    fn nf_ct_get_tuplepr(skb: *mut sk_buff, dataoff: c_uint, pf: c_int, net: *mut c_void, tuple: *mut nf_conntrack_tuple) -> bool;
    fn nf_ct_invert_tuple(tuple: *mut nf_conntrack_tuple, orig: *const nf_conntrack_tuple) -> bool;
    fn nf_conntrack_find_get(net: *mut c_void, zone: *mut nf_conntrack_zone, tuple: *mut nf_conntrack_tuple) -> *mut nf_conntrack_tuple_hash;
    fn nf_ct_tuplehash_to_ctrack(h: *mut nf_conntrack_tuple_hash) -> *mut nf_conn;
    fn nf_ct_set(skb: *mut sk_buff, ct: *mut nf_conn, ctinfo: c_int);
    fn nf_l4proto_log_invalid(skb: *mut sk_buff, net: *mut c_void, pf: c_int, proto: c_int, fmt: *const c_char, ...);
    fn nf_ip_checksum(skb: *mut sk_buff, hook: c_int, dataoff: c_uint, protocol: c_int) -> c_int;
    fn icmp_is_err(type_: u8) -> bool;
}

// Additional helper functions
#[no_mangle]
pub unsafe extern "C" fn icmp_error_log(
    skb: *const sk_buff,
    state: *const nf_hook_state,
    msg: *const c_char,
) {
    nf_l4proto_log_invalid(skb as *mut _, (*state).net, (*state).pf as c_int, IPPROTO_ICMP, msg);
}

// Constants
pub const IPPROTO_ICMP: c_int = 1;
pub const IP_CT_DIR_REPLY: c_int = 1;
pub const IP_CT_IS_REPLY: c_int = 1;
pub const IP_CT_RELATED: c_int = 2;
pub const NF_INET_PRE_ROUTING: c_int = 0;

// Static data
pub static VALID_NEW: [u8; 256] = {
    let mut arr = [0u8; 256];
    arr[ICMP_ECHO as usize] = 1;
    arr[ICMP_TIMESTAMP as usize] = 1;
    arr[ICMP_INFO_REQUEST as usize] = 1;
    arr[ICMP_ADDRESS as usize] = 1;
    arr
};
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
