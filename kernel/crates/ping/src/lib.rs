#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]

use core::{ffi::{c_int, c_void}, panic::PanicInfo};
use kernel_types::*;

pub type size_t = usize;
pub type c_size_t = usize;
pub type socklen_t = u32;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOSYS: c_int = -38;
pub const EAFNOSUPPORT: c_int = -125;
pub const EDESTADDRREQ: c_int = -39;

// Type definitions

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sockaddr_in6 {
    pub sin6_family: u16,
    pub sin6_port: u16,
    pub sin6_flowinfo: u32,
    pub sin6_addr: in6_addr,
    pub sin6_scope_id: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct icmp6_echo { pub id: u16, pub sequence: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct icmp6hdr {
    pub icmp6_type: u8,
    pub icmp6_code: u8,
    pub checksum: u16,
    pub un: icmp6_echo,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct pingfakehdr {
    pub icmph: icmp6hdr,
    pub msg: *mut msghdr,
    pub wcheck: u16,
    pub family: u16,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct proto {
    pub name: *const u8,
    pub owner: *mut c_void,
    pub init: extern "C" fn(*mut sock) -> c_int,
    pub close: extern "C" fn(*mut sock, c_int),
    pub connect: extern "C" fn(*mut sock, *const sockaddr_in6, socklen_t, c_int) -> c_int,
    pub disconnect: extern "C" fn(*mut sock, c_int),
    pub setsockopt: extern "C" fn(*mut sock, c_int, c_int, *const c_void, socklen_t) -> c_int,
    pub getsockopt: extern "C" fn(*mut sock, c_int, c_int, *mut c_void, *mut socklen_t) -> c_int,
    pub sendmsg: extern "C" fn(*mut sock, *mut msghdr, size_t) -> c_int,
    pub recvmsg: extern "C" fn(*mut sock, *mut msghdr, size_t, c_int) -> c_int,
    pub bind: extern "C" fn(*mut sock, *const sockaddr_in6, socklen_t) -> c_int,
    pub backlog_rcv: extern "C" fn(*mut sock, *mut sk_buff) -> c_int,
    pub hash: extern "C" fn(*mut sock),
    pub unhash: extern "C" fn(*mut sock),
    pub get_port: extern "C" fn(*mut sock, u16) -> c_int,
    pub obj_size: size_t,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_protosw {
    pub type_: c_int,
    pub protocol: c_int,
    pub prot: *mut proto,
    pub ops: *mut c_void,
    pub flags: c_int,
}

#[repr(C)]
pub struct msghdr { _priv: [u8; 0] }

#[repr(C)]
pub struct net_device { _priv: [u8; 0] }

#[repr(C)]
pub struct net { _priv: [u8; 0] }

#[no_mangle]
// SAFETY: Callers must ensure `_sk` is either null or a valid `sock` pointer, `_msg` is either
// null or a valid `msghdr` pointer, `_len` is a non-negative length, and `_addr_len` is either
// Implementation deferred.
pub unsafe extern "C" fn dummy_ipv6_recv_error(
    _sk: *mut sock,
    _msg: *mut msghdr,
    _len: c_int,
    _addr_len: *mut c_int,
) -> c_int {
    EAFNOSUPPORT
}

#[no_mangle]
// SAFETY: Callers must ensure `_sk` is either null or a valid `sock` pointer, `_msg` is either
// null or a valid `msghdr` pointer, and `_skb` is either null or a valid `sk_buff` pointer.
// Implementation deferred.
pub unsafe extern "C" fn dummy_ip6_datagram_recv_ctl(
    _sk: *mut sock,
    _msg: *mut msghdr,
    _skb: *mut sk_buff,
) {
}

#[no_mangle]
// SAFETY: Callers must ensure `_err` is either null or a valid, writable `c_int` pointer.
// Implementation deferred.
pub unsafe extern "C" fn dummy_icmpv6_err_convert(
    _type_: u8,
    _code: u8,
    _err: *mut c_int,
) -> c_int {
    EAFNOSUPPORT
}

#[no_mangle]
// SAFETY: Callers must ensure all pointer arguments are either null or valid for the duration
// Implementation deferred.
pub unsafe extern "C" fn dummy_ipv6_icmp_error(
    _sk: *mut sock,
    _skb: *mut sk_buff,
    _err: c_int,
    _port: u16,
    _info: u32,
    _payload: *mut u8,
) {
}

#[no_mangle]
// SAFETY: Callers must ensure `net` is either null or a valid `net` namespace pointer and
// `addr` is either null or a valid, aligned `in6_addr` pointer. `_dev` and `_strict` are
// Implementation deferred.
pub unsafe extern "C" fn dummy_ipv6_chk_addr(
    net: *mut net,
    addr: *const in6_addr,
    _dev: *const net_device,
    _strict: c_int,
) -> c_int {
    if net.is_null() || addr.is_null() {
        0
    } else {
        1
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dummy_ipv6_chk_addr() {
        // SAFETY: null pointers exercise the early-return path (returns 0) without any deref.
        // The stack-allocated zeroed `net` and `in6_addr` are valid for the duration of the
        // call; only a null-check is performed before returning 1.
        unsafe {
            assert_eq!(dummy_ipv6_chk_addr(core::ptr::null_mut(), core::ptr::null(), core::ptr::null(), 0), 0);
            let mut dummy_net = net { _priv: [] };
            let dummy_addr: in6_addr = core::mem::zeroed();
            assert_eq!(dummy_ipv6_chk_addr(&mut dummy_net as *mut _, &dummy_addr as *const _, core::ptr::null(), 0), 1);
        }
    }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}

