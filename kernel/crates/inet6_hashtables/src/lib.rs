#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

use core::{ptr, ffi::{c_int, c_void}};

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOSYS: c_int = -38;
pub const EADDRNOTAVAIL: c_int = -125;

pub type socklen_t = u32;
pub type size_t = usize;
pub type c_size_t = usize;

pub const AF_INET6: u16 = 10;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct hlist_nulls_node {
    pub next: *const hlist_nulls_node,
    pub pprev: *mut *const hlist_nulls_node,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct hlist_nulls_head { pub first: *const hlist_nulls_node }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_hashinfo { pub ehash_mask: u32, pub ehash: *mut inet_ehash_bucket }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_ehash_bucket { pub chain: hlist_nulls_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sock_common {
    pub skc_family: u16,
    pub skc_num: u16,
    pub skc_dport: u16,
    pub skc_nulls_node: hlist_nulls_node,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sock_min { pub __sk_common: sock_common }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sock { pub sk: sock_min }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_addr_union { pub u6_addr32: [u32; 4] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct in6_addr { pub in6_u: ipv6_addr_union }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_pinfo { pub saddr: in6_addr, pub daddr: in6_addr }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_sock {
    pub sk: sock_min,
    pub inet_sport: u16,
    pub inet_dport: u16,
    pub pinet6: *mut ipv6_pinfo,
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

#[inline(always)]
unsafe fn sk_from_nulls_node(node: *const hlist_nulls_node) -> *mut sock {
    let off = core::mem::offset_of!(sock_min, __sk_common.skc_nulls_node);
    ((node as usize).wrapping_sub(off)) as *mut sock
}

#[inline(always)]
unsafe fn ipv6_addr_jhash(addr: *const in6_addr, seed: u32) -> u32 {
    let a = (*addr).in6_u.u6_addr32;
    let mut h =
        seed ^ a[0].rotate_left(5) ^ a[1].rotate_left(11) ^ a[2].rotate_left(17) ^ a[3].rotate_left(23);
    h ^= h >> 16;
    h = h.wrapping_mul(0x7feb_352d);
    h ^= h >> 15;
    h = h.wrapping_mul(0x846c_a68b);
    h ^ (h >> 16)
}

#[inline(always)]
unsafe fn net_hash_mix(net: *const c_void) -> u32 {
    let x = net as usize as u64;
    let mut h = (x as u32) ^ ((x >> 32) as u32);
    h ^= h.rotate_left(13);
    h = h.wrapping_mul(0x9e37_79b1);
    h ^ (h >> 16)
}

#[inline(always)]
unsafe fn inet6_ehash_mix(lhash: u32, lport: u16, fhash: u32, fport: u16, secret: u32) -> u32 {
    let mut h =
        secret ^ lhash.rotate_left(7) ^ fhash.rotate_left(19) ^ (((lport as u32) << 16) | (fport as u32));
    h ^= h >> 16;
    h = h.wrapping_mul(0x85eb_ca6b);
    h ^= h >> 13;
    h = h.wrapping_mul(0xc2b2_ae35);
    h ^ (h >> 16)
}

#[no_mangle]
pub unsafe extern "C" fn inet6_ehashfn(
    net: *const c_void,
    laddr: *const in6_addr,
    lport: u16,
    faddr: *const in6_addr,
    fport: u16,
) -> u32 {
    const INET6_EHASH_SECRET: u32 = 0x1234_5678;
    const IPV6_HASH_SECRET: u32 = 0x8765_4321;

    let lhash = (*laddr).in6_u.u6_addr32[3];
    let fhash = ipv6_addr_jhash(faddr, IPV6_HASH_SECRET);

    inet6_ehash_mix(
        lhash,
        lport,
        fhash,
        fport,
        INET6_EHASH_SECRET.wrapping_add(net_hash_mix(net)),
    )
}

#[no_mangle]
pub unsafe extern "C" fn __inet6_lookup_established(
    net: *const c_void,
    hashinfo: *mut inet_hashinfo,
    saddr: *const in6_addr,
    sport: u16,
    daddr: *const in6_addr,
    hnum: u16,
    _dif: c_int,
    _sdif: c_int,
) -> *mut sock {
    let hashinfo_ref = &*hashinfo;
    let slot = inet6_ehashfn(net, daddr, hnum, saddr, sport) & hashinfo_ref.ehash_mask;
    let head = &*hashinfo_ref.ehash.add(slot as usize);

    let mut node: *const hlist_nulls_node = ptr::null();

    loop {
        node = if node.is_null() { head.chain.first } else { (*node).next };

        if node.is_null() {
            break;
        }

        let entry = sk_from_nulls_node(node);
        let entry_sk = &*(entry as *const sock_min);

        if entry_sk.__sk_common.skc_family != AF_INET6 {
            continue;
        }

        let inet6_sk = &*(entry as *const inet_sock);

        if inet6_sk.inet_sport != sport || inet6_sk.inet_dport != hnum {
            continue;
        }

        if inet6_sk.pinet6.is_null() {
            continue;
        }

        let pinet6 = &*inet6_sk.pinet6;

        if pinet6.saddr.in6_u.u6_addr32[0] != (*saddr).in6_u.u6_addr32[0]
            || pinet6.saddr.in6_u.u6_addr32[1] != (*saddr).in6_u.u6_addr32[1]
            || pinet6.saddr.in6_u.u6_addr32[2] != (*saddr).in6_u.u6_addr32[2]
            || pinet6.saddr.in6_u.u6_addr32[3] != (*saddr).in6_u.u6_addr32[3]
            || pinet6.daddr.in6_u.u6_addr32[0] != (*daddr).in6_u.u6_addr32[0]
            || pinet6.daddr.in6_u.u6_addr32[1] != (*daddr).in6_u.u6_addr32[1]
            || pinet6.daddr.in6_u.u6_addr32[2] != (*daddr).in6_u.u6_addr32[2]
            || pinet6.daddr.in6_u.u6_addr32[3] != (*daddr).in6_u.u6_addr32[3]
        {
            continue;
        }

        return entry;
    }

    ptr::null_mut()
}

#[cfg(not(test))]
#[no_mangle]
pub extern "C" fn rust_eh_personality() {}

#[cfg(not(test))]
#[no_mangle]
pub extern "C" fn _Unwind_Resume() -> ! {
    loop {}
}
