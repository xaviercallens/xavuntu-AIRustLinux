#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
#![allow(warnings)]
#![allow(non_camel_case_types)]
#![allow(clippy::not_unsafe_ptr_arg_deref)]

// SyncWrapper for safe global mutability
#[repr(transparent)]
pub struct SyncWrapper<T>(pub core::cell::UnsafeCell<T>);
unsafe impl<T> Sync for SyncWrapper<T> {}
impl<T> SyncWrapper<T> {
    pub const fn new(value: T) -> Self {
        Self(core::cell::UnsafeCell::new(value))
    }
    #[inline(always)]
    pub unsafe fn get_mut(&self) -> &mut T {
        // SAFETY: The caller must guarantee exclusive access or single-threaded context.
        unsafe { &mut *self.0.get() }
    }
}

use core::ptr;
use kernel_types::*;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_icmp {
    pub type_: u8,
    pub code: u8,
    pub checksum: __be16,
    pub un: ip6_icmp_body,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub union ip6_icmp_body {
    pub u_echo: ip6_icmp_echo,
    pub u_paramprob: ip6_icmp_paramprob,
    pub u_redirect: ip6_icmp_redirect,
    pub u_neighbor: ip6_icmp_neighbor,
    pub u_router: ip6_icmp_router,
    pub u_routersolicit: ip6_icmp_routersolicit,
    pub u_timeexceed: ip6_icmp_timeexceed,
    pub u_unreach: ip6_icmp_unreach,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_icmp_echo { pub identifier: __be16, pub sequence: __be16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_icmp_paramprob { pub pointer: __be32 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_icmp_redirect { pub target: in6_addr }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_icmp_neighbor { pub target: in6_addr }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_icmp_router { pub lifetime: __be32, pub addr: in6_addr }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_icmp_routersolicit { pub reserved: __be32 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_icmp_timeexceed { pub unused: __be32 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_icmp_unreach { pub unused: __be32 }

/// Pointer to the UDP disconnect function.
pub static __UDP_DISCONNECT: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());

/// Pointer to the ICMPv6 error conversion function.
pub static ICMPV6_ERR_CONVERT: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());

/// Pointer to the IPv6 sockraw operations.
pub static INET6_SOCKRAW_OPS: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());

/// Pointer to the IPv6 datagram connect function for v6 only.
pub static IP6_DATAGRAM_CONNECT_V6_ONLY: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());

/// Pointer to the IPv6 datagram receive common control function.
pub static IP6_DATAGRAM_RECV_COMMON_CTL: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());

extern "C" {
    pub fn ip6_icmp_send(
        skb: *mut sk_buff,
        type_: u8,
        code: u8,
        offset: c_int,
        mtu: __be32,
    ) -> c_int;

    pub fn ip6_icmp_error(
        skb: *mut sk_buff,
        type_: u8,
        code: u8,
        offset: c_int,
        mtu: __be32,
    ) -> c_int;
}

#[inline]
fn skb_cb_as_icmp(skb: *mut sk_buff) -> *mut ip6_icmp {
    if skb.is_null() {
        return ptr::null_mut();
    }
    let cb_ptr = unsafe { (*skb).cb.as_mut_ptr() };
    cb_ptr.cast::<ip6_icmp>()
}

pub fn ip6_icmp_send_echo_reply(
    skb: *mut sk_buff,
    type_: u8,
    code: u8,
    offset: c_int,
    mtu: __be32,
) -> c_int {
    if skb.is_null() {
        return -1;
    }

    let icmp6h = skb_cb_as_icmp(skb);
    if icmp6h.is_null() {
        return -1;
    }

    unsafe {
        let icmp6h_ref = &*icmp6h;

        if icmp6h_ref.type_ != type_ || icmp6h_ref.code != code {
            return -1;
        }

        let echo = &mut (*icmp6h).un.u_echo;
        echo.identifier = icmp6h_ref.un.u_echo.identifier;
        echo.sequence = icmp6h_ref.un.u_echo.sequence;

        (*icmp6h).type_ = type_;
        (*icmp6h).code = code;

        ip6_icmp_send(skb, type_, code, offset, mtu)
    }
}

pub fn ip6_icmp_send_error(
    skb: *mut sk_buff,
    type_: u8,
    code: u8,
    offset: c_int,
    mtu: __be32,
) -> c_int {
    if skb.is_null() {
        return -1;
    }

    let icmp6h = skb_cb_as_icmp(skb);
    if icmp6h.is_null() {
        return -1;
    }

    unsafe {
        let icmp6h_ref = &*icmp6h;

        if icmp6h_ref.type_ != type_ || icmp6h_ref.code != code {
            return -1;
        }

        (*icmp6h).type_ = type_;
        (*icmp6h).code = code;

        ip6_icmp_error(skb, type_, code, offset, mtu)
    }
}

#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
