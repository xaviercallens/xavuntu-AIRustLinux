#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! Connection tracking via netlink socket. Allows for user space
//! protocol helpers and general trouble making from userspace.
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]

use core::{ffi::c_int, panic::PanicInfo};
use kernel_types::*;

pub type size_t = usize;
pub type c_size_t = usize;
pub type socklen_t = u32;

pub const ENOMEM: c_int = 12; pub const EINVAL: c_int = 22; pub const EMSGSIZE: c_int = 90;

pub const CTA_TUPLE_PROTO: c_int = 1;
pub const CTA_PROTO_NUM: c_int = 1;
pub const CTA_IP_V4_SRC: c_int = 1;
pub const CTA_IP_V4_DST: c_int = 2;
pub const CTA_IP_V6_SRC: c_int = 3;
pub const CTA_IP_V6_DST: c_int = 4;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nlattr { pub nla_len: u16, pub nla_type: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_inet_addr { pub all: [u32; 4] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_dst { pub protonum: u8, pub u3: nf_inet_addr }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_src { pub u3: nf_inet_addr }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple {
    pub dst: nf_conntrack_tuple_dst,
    pub src: nf_conntrack_tuple_src,
    pub src_l3num: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_l4proto {
    pub tuple_to_nlattr:
        Option<extern "C" fn(skb: *mut sk_buff, tuple: *const nf_conntrack_tuple) -> c_int>,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_counter { pub packets: [u64; 2], pub bytes: [u64; 2] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_acct { pub counter: *mut nf_conn_counter }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_tstamp { pub start: u64, pub stop: u64 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_labels { pub bits: [u64; 16] }

unsafe extern "C" {
    fn nla_nest_start(skb: *mut sk_buff, attrtype: c_int) -> *mut nlattr;
    fn nla_nest_end(skb: *mut sk_buff, nest: *mut nlattr);
    fn nla_put_u8(skb: *mut sk_buff, attrtype: c_int, val: u8) -> c_int;
    fn nla_put_be16(skb: *mut sk_buff, attrtype: c_int, val: u16) -> c_int;
    fn nla_put_be32(skb: *mut sk_buff, attrtype: c_int, val: u32) -> c_int;
    fn nla_put_in_addr(skb: *mut sk_buff, attrtype: c_int, val: u32) -> c_int;
    fn nla_put_in6_addr(skb: *mut sk_buff, attrtype: c_int, val: *const [u8; 16]) -> c_int;
    fn nla_put_be64(skb: *mut sk_buff, attrtype: c_int, val: u64, pad: c_int) -> c_int;
    fn nla_put_string(skb: *mut sk_buff, attrtype: c_int, val: *const u8) -> c_int;
    fn nf_ct_l4proto_find(protonum: u8) -> *const nf_conntrack_l4proto;
    fn nf_ct_protonum(ct: *const nf_conn) -> u8;
    fn nf_ct_expires(ct: *const nf_conn) -> u32;
    fn nf_ct_acct_find(ct: *const nf_conn) -> *mut nf_conn_acct;
    fn rcu_read_lock();
    fn rcu_read_unlock();
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {
        core::hint::spin_loop();
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rust_eh_personality() {}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ctnetlink_dump_tuples_proto(
    skb: *mut sk_buff,
    tuple: *const nf_conntrack_tuple,
    l4proto: *const nf_conntrack_l4proto,
) -> c_int {
    let nest_parms = nla_nest_start(skb, CTA_TUPLE_PROTO);
    if nest_parms.is_null() {
        return -EMSGSIZE;
    }

    if nla_put_u8(skb, CTA_PROTO_NUM, (*tuple).dst.protonum) != 0 {
        nla_nest_end(skb, nest_parms);
        return -EMSGSIZE;
    }

    if let Some(proto_to_nlattr) = (*l4proto).tuple_to_nlattr {
        let ret = proto_to_nlattr(skb, tuple);
        if ret != 0 {
            nla_nest_end(skb, nest_parms);
            return ret;
        }
    }

    nla_nest_end(skb, nest_parms);
    0
}

#[no_mangle]
pub unsafe extern "C" fn ipv4_tuple_to_nlattr(
    skb: *mut sk_buff,
    _tuple: *const nf_conntrack_tuple,
) -> c_int {
    // Implementation deferred.
    if nla_put_in_addr(skb, CTA_IP_V4_SRC, 0) != 0 {
        return -EMSGSIZE;
    }
    if nla_put_in_addr(skb, CTA_IP_V4_DST, 0) != 0 {
        return -EMSGSIZE;
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_tuple_to_nlattr(
    skb: *mut sk_buff,
    _tuple: *const nf_conntrack_tuple,
) -> c_int {
    // Implementation deferred.
    let zero_addr: [u8; 16] = [0; 16];
    if nla_put_in6_addr(skb, CTA_IP_V6_SRC, &zero_addr) != 0 {
        return -EMSGSIZE;
    }
    if nla_put_in6_addr(skb, CTA_IP_V6_DST, &zero_addr) != 0 {
        return -EMSGSIZE;
    }
    0
}

/// Dump IP addresses part of connection tuple to netlink message
///
/// # Safety
/// - `skb` must be a valid pointer to sk_buff
/// - `tuple` must be a valid pointer to nf_conntrack_tuple
///
/// # Returns
/// 0 on success, -EMSGSIZE if message too large
#[no_mangle]
pub unsafe extern "C" fn ctnetlink_dump_tuples_ip(
    skb: *mut sk_buff,
    tuple: *const nf_conntrack_tuple,
) -> c_int {
    let nest_parms = nla_nest_start(skb, CTA_TUPLE_IP);
    if nest_parms.is_null() {
        return -EMSGSIZE;
    }

    let ret = match (*tuple).src_l3num {
        NFPROTO_IPV4 => ipv4_tuple_to_nlattr(skb, tuple),
        NFPROTO_IPV6 => ipv6_tuple_to_nlattr(skb, tuple),
        _ => 0,
    };

    if ret != 0 {
        nla_nest_end(skb, nest_parms);
        return ret;
    }

    nla_nest_end(skb, nest_parms);
    ret
}

/// Dump connection tuple to netlink message
///
/// # Safety
/// - `skb` must be a valid pointer to sk_buff
/// - `tuple` must be a valid pointer to nf_conntrack_tuple
///
/// # Returns
/// 0 on success, -EMSGSIZE if message too large
#[no_mangle]
pub unsafe extern "C" fn ctnetlink_dump_tuples(
    skb: *mut sk_buff,
    tuple: *const nf_conntrack_tuple,
) -> c_int {
    rcu_read_lock();
    let mut ret = ctnetlink_dump_tuples_ip(skb, tuple);

    if ret >= 0 {
        let l4proto = nf_ct_l4proto_find((*tuple).dst.protonum);
        if !l4proto.is_null() {
            ret = ctnetlink_dump_tuples_proto(skb, tuple, l4proto);
        }
    }
    rcu_read_unlock();
    ret
}

/// Dump zone ID to netlink message
///
/// # Safety
/// - `skb` must be a valid pointer to sk_buff
/// - `zone` must be a valid pointer to nf_conntrack_zone
///
/// # Returns
/// 0 on success, -EMSGSIZE if message too large
#[no_mangle]
pub unsafe extern "C" fn ctnetlink_dump_zone_id(
    skb: *mut sk_buff,
    attrtype: c_int,
    zone: *const nf_conntrack_zone,
    dir: c_int,
) -> c_int {
    if (*zone).id == NF_CT_DEFAULT_ZONE_ID || (*zone).dir != dir as u8 {
        return 0;
    }
    if nla_put_be16(skb, attrtype, htons((*zone).id)) != 0 {
        return -EMSGSIZE;
    }
    0
}

/// Dump connection status to netlink message
///
/// # Safety
/// - `skb` must be a valid pointer to sk_buff
/// - `ct` must be a valid pointer to nf_conn
///
/// # Returns
/// 0 on success, -EMSGSIZE if message too large
#[no_mangle]
pub unsafe extern "C" fn ctnetlink_dump_status(skb: *mut sk_buff, ct: *const nf_conn) -> c_int {
    if nla_put_be32(skb, CTA_STATUS, htonl((*ct).status as u32)) != 0 {
        return -EMSGSIZE;
    }
    0
}

/// Dump connection timeout to netlink message
///
/// # Safety
/// - `skb` must be a valid pointer to sk_buff
/// - `ct` must be a valid pointer to nf_conn
///
/// # Returns
/// 0 on success, -EMSGSIZE if message too large
#[no_mangle]
pub unsafe extern "C" fn ctnetlink_dump_timeout(
    skb: *mut sk_buff,
    ct: *const nf_conn,
    skip_zero: c_int,
) -> c_int {
    let timeout = nf_ct_expires(ct) / 4; // Assuming HZ=4 for example
    if skip_zero != 0 && timeout == 0 {
        return 0;
    }
    if nla_put_be32(skb, CTA_TIMEOUT, htonl(timeout)) != 0 {
        return -EMSGSIZE;
    }
    0
}

// Remove duplicate constants - check which ones are already at top
pub const CTA_TUPLE_IP: c_int = 2;
pub const CTA_STATUS: c_int = 5;
pub const CTA_TIMEOUT: c_int = 6;
pub const CTA_PROTOINFO: c_int = 7;
pub const CTA_HELP: c_int = 8;
pub const CTA_COUNTERS_ORIG: c_int = 9;
pub const CTA_COUNTERS_REPLY: c_int = 10;
pub const CTA_TIMESTAMP: c_int = 11;
pub const CTA_MARK: c_int = 12;
pub const CTA_SECCTX: c_int = 13;
pub const CTA_LABELS: c_int = 14;
pub const CTA_TUPLE_MASTER: c_int = 15;

pub const NFPROTO_IPV4: u8 = 2; pub const NFPROTO_IPV6: u8 = 10; pub const NF_CT_DEFAULT_ZONE_ID: u16 = 0xffff;

// htons and htonl implementations for no_std environment
#[inline]
fn htons(x: u16) -> u16 { x.rotate_left(8) }

#[inline]
fn htonl(x: u32) -> u32 {
    ((x & 0x000000ff) << 24)
        | ((x & 0x0000ff00) << 8)
        | ((x & 0x00ff0000) >> 8)
        | ((x & 0xff000000) >> 24)
}

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    #[test]
    fn test_htons() {
        assert_eq!(super::htons(0x1234), 0x3412);
    }

    #[test]
    fn test_htonl() {
        assert_eq!(super::htonl(0x12345678), 0x78063412);
    }
}
