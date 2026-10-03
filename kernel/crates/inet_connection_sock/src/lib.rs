#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(clippy::all)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::{ptr, ffi::c_int, panic::PanicInfo};
use kernel_types::*;

pub const AF_INET6: c_int = 10;

pub const IPV6_ADDR_ANY: c_int = 0;
pub const IPV6_ADDR_MAPPED: c_int = 1;
pub const SK_CAN_REUSE: c_int = 2;
pub const TCP_LISTEN: c_int = 1;
pub const TCP_TIME_WAIT: c_int = 7;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_bind_bucket {
    pub port: u16,
    pub l3mdev: c_int,
    pub fastreuseport: i32,
    pub fastuid: u32,
    pub fast_rcv_saddr: u32,
    pub fast_ipv6_only: c_uchar,
    pub fast_sk_family: c_int,
    pub fast_v6_rcv_saddr: in6_addr,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_hashinfo { pub bhash_size: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net { pub ipv4: ipv4_net }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv4_net { pub ip_local_ports: seqlock }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct seqlock { pub lock: spinlock, pub range: [c_int; 2] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct spinlock { pub _priv: u8 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sock_common {
    pub skc_family: u16,
    pub skc_rcv_saddr: u32,
    pub skc_v6_rcv_saddr: in6_addr,
}

unsafe extern "C" {
    fn ipv6_addr_type(addr: *const in6_addr) -> c_int;
    fn ipv6_addr_equal(a: *const in6_addr, b: *const in6_addr) -> c_uchar;
    fn ipv6_addr_any(addr: *const in6_addr) -> c_uchar;
    fn inet_is_local_reserved_port(net: *mut net, port: c_int) -> c_uchar;
    fn read_seqbegin(seq: *mut spinlock) -> c_int;
    fn read_seqretry(seq: *mut spinlock, start: c_int) -> c_uchar;
    fn prandom_u32() -> u32;
    fn cond_resched();
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}

#[inline]
fn cbool(v: bool) -> c_uchar { if v { 1 } else { 0 } }

#[inline]
fn rbool(v: c_uchar) -> bool { v != 0 }

#[inline]
unsafe fn sk_common(sk: *const sock) -> *const sock_common {
    sk.cast::<sock_common>()
}

#[inline]
unsafe fn sk_family(sk: *const sock) -> c_int { (*sk_common(sk)).skc_family as c_int }

#[inline]
unsafe fn sk_rcv_saddr(sk: *const sock) -> u32 { (*sk_common(sk)).skc_rcv_saddr }

#[inline]
unsafe fn sk_v6_rcv_saddr(sk: *const sock) -> *const in6_addr {
    &(*sk_common(sk)).skc_v6_rcv_saddr
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_rcv_saddr_equal(
    sk1_rcv_saddr6: *const in6_addr,
    sk2_rcv_saddr6: *const in6_addr,
    sk1_rcv_saddr: u32,
    sk2_rcv_saddr: u32,
    sk1_ipv6only: c_uchar,
    sk2_ipv6only: c_uchar,
    match_sk1_wildcard: c_uchar,
    match_sk2_wildcard: c_uchar,
) -> c_uchar {
    if sk1_rcv_saddr6.is_null() || sk2_rcv_saddr6.is_null() {
        return 0;
    }

    let addr_type = ipv6_addr_type(sk1_rcv_saddr6);
    let addr_type2 = ipv6_addr_type(sk2_rcv_saddr6);

    if addr_type == IPV6_ADDR_MAPPED && addr_type2 == IPV6_ADDR_MAPPED {
        if !rbool(sk2_ipv6only) {
            if sk1_rcv_saddr == sk2_rcv_saddr {
                return 1;
            }
            return cbool(
                (rbool(match_sk1_wildcard) && sk1_rcv_saddr == 0)
                    || (rbool(match_sk2_wildcard) && sk2_rcv_saddr == 0),
            );
        }
        return 0;
    }

    if addr_type == IPV6_ADDR_ANY && addr_type2 == IPV6_ADDR_ANY {
        return 1;
    }

    if addr_type2 == IPV6_ADDR_ANY
        && rbool(match_sk2_wildcard)
        && !(rbool(sk2_ipv6only) && addr_type == IPV6_ADDR_MAPPED)
    {
        return 1;
    }

    if addr_type == IPV6_ADDR_ANY
        && rbool(match_sk1_wildcard)
        && !(rbool(sk1_ipv6only) && addr_type2 == IPV6_ADDR_MAPPED)
    {
        return 1;
    }

    if rbool(ipv6_addr_equal(sk1_rcv_saddr6, sk2_rcv_saddr6)) {
        return 1;
    }

    0
}

#[no_mangle]
pub unsafe extern "C" fn ipv4_rcv_saddr_equal(
    sk1_rcv_saddr: u32,
    sk2_rcv_saddr: u32,
    sk2_ipv6only: c_uchar,
    match_sk1_wildcard: c_uchar,
    match_sk2_wildcard: c_uchar,
) -> c_uchar {
    if !rbool(sk2_ipv6only) {
        if sk1_rcv_saddr == sk2_rcv_saddr {
            return 1;
        }
        return cbool(
            (rbool(match_sk1_wildcard) && sk1_rcv_saddr == 0)
                || (rbool(match_sk2_wildcard) && sk2_rcv_saddr == 0),
        );
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn inet_rcv_saddr_equal(
    sk: *const sock,
    sk2: *const sock,
    match_wildcard: c_uchar,
) -> c_uchar {
    if sk.is_null() || sk2.is_null() {
        return 0;
    }

    if sk_family(sk) == AF_INET6 {
        let sk2_rcv_saddr6 = sk_v6_rcv_saddr(sk2);
        return ipv6_rcv_saddr_equal(
            sk_v6_rcv_saddr(sk),
            sk2_rcv_saddr6,
            sk_rcv_saddr(sk),
            sk_rcv_saddr(sk2),
            1, // ipv6_only for sk
            1, // ipv6_only for sk2
            match_wildcard,
            match_wildcard,
        );
    }

    ipv4_rcv_saddr_equal(
        sk_rcv_saddr(sk),
        sk_rcv_saddr(sk2),
        0, // not ipv6_only for sk2
        match_wildcard,
        match_wildcard,
    )
}

// Get local port range
#[no_mangle]
pub unsafe extern "C" fn inet_get_local_port_range(
    net: *mut net,
    low: *mut c_int,
    high: *mut c_int,
) {
    if net.is_null() || low.is_null() || high.is_null() {
        return;
    }

    let mut seq: c_int = 0;
    loop {
        seq = read_seqbegin(&mut (*net).ipv4.ip_local_ports.lock);
        *low = (*net).ipv4.ip_local_ports.range[0];
        *high = (*net).ipv4.ip_local_ports.range[1];
        if read_seqretry(&mut (*net).ipv4.ip_local_ports.lock, seq) == 0 {
            break;
        }
    }
}

// Check for bind conflicts
#[no_mangle]
pub unsafe extern "C" fn inet_csk_bind_conflict(
    sk: *const sock,
    tb: *const inet_bind_bucket,
    relax: bool,
    reuseport_ok: bool,
) -> bool {
    if sk.is_null() || tb.is_null() {
        return false;
    }

    let reuse = (*sk).sk_reuse != 0;
    let reuseport = !(*sk).sk_reuseport.is_null();
    let uid = sock_i_uid(sk);

    let sk2: *const sock = ptr::null();
    // Implementation would iterate through (*tb).owners list
    // Implementation deferred.
    while !sk2.is_null() {
        if sk != sk2
            && ((*sk).sk_bound_dev_if.is_null()
                || (*sk2).sk_bound_dev_if.is_null()
                || (*sk).sk_bound_dev_if == (*sk2).sk_bound_dev_if)
        {
            if reuse && (*sk2).sk_reuse != 0 && (*sk2).sk_state != TCP_LISTEN as u32 {
                if !relax
                    || (!reuseport_ok
                        && reuseport
                        && !(*sk2).sk_reuseport.is_null()
                        && (*sk).sk_reuseport_cb.is_null()
                        && ((*sk2).sk_state == TCP_TIME_WAIT as u32 || uid_eq(uid, sock_i_uid(sk2))))
                        && rbool(inet_rcv_saddr_equal(sk, sk2, 1))
                {
                    return true;
                }
            } else if !reuseport_ok
                || !reuseport
                || (*sk2).sk_reuseport.is_null()
                || !(*sk).sk_reuseport_cb.is_null()
                || ((*sk2).sk_state != TCP_TIME_WAIT as u32 && !uid_eq(uid, sock_i_uid(sk2)))
            {
                if rbool(inet_rcv_saddr_equal(sk, sk2, 1)) {
                    return true;
                }
            }
        }
    }
    false
}

// Helper functions
#[inline]
unsafe fn sock_i_uid(_sk: *const sock) -> u32 {
    // Implementation deferred.
    0
}

#[inline]
unsafe fn rcu_access_pointer<T>(ptr: *mut T) -> Option<*mut T> {
    if !ptr.is_null() {
        Some(ptr)
    } else {
        None
    }
}

#[inline]
unsafe fn uid_eq(uid1: u32, uid2: u32) -> bool { uid1 == uid2 }

// Exported symbols
#[no_mangle]
pub unsafe extern "C" fn inet_rcv_saddr_any(sk: *const sock) -> bool {
    if sk.is_null() {
        return false;
    }

    if (*sk).sk_family == AF_INET6 as u16 {
        rbool(ipv6_addr_any((*sk).sk_v6_rcv_saddr as *const in6_addr))
    } else {
        (*sk).sk_rcv_saddr.is_null()
    }
}

// Constants
pub const AF_INET: c_int = 2;
