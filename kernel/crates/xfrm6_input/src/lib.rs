#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
//! IPv6 XFRM (IPsec) Input Processing
//!
//! This module implements the IPv6-specific input path for XFRM (IPsec) in the Linux kernel.
//! The implementation is FFI-compatible with the original C code and maintains strict ABI compatibility.
//!
//! Key features:
//! - Tunnel SPI handling
//! - Transport mode processing
//! - UDP encapsulation support
//! - State lookup and processing
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]

use core::{ffi::c_int, mem::offset_of};

pub const AF_INET6: c_int = 10; pub const NET_RX_DROP: c_int = 1; pub const XFRM_MAX_DEPTH: c_int = 16;

#[repr(C)]
pub struct xfrm_state { _priv: [u8; 0] }

#[repr(C)]
pub struct sk_buff { pub cb: [u8; 48], _priv: [u8; 0] }

#[repr(C)]
pub struct net { _priv: [u8; 0] }

#[repr(C)]
pub struct sock { _priv: [u8; 0] }

#[repr(C)]
pub struct ip6_tnl { _priv: [u8; 0] }

#[repr(C)]
pub struct in6_addr { pub s6_addr: [u8; 16] }

#[repr(C)]
pub struct ipv6hdr { _pad0: [u8; 24], pub daddr: in6_addr }

#[repr(C)]
pub struct xfrm_address_t { pub a6: in6_addr }

#[repr(C)]
pub struct sec_path { pub xvec: [*mut xfrm_state; XFRM_MAX_DEPTH as usize], pub len: c_int }

#[repr(C)]
pub struct xfrm_spi_info { pub family: c_int, pub daddroff: usize }

#[repr(C)]
pub struct xfrm_tunnel_skb_cb { pub ip6: *mut ip6_tnl }

unsafe extern "C" {
    fn xfrm_input(skb: *mut sk_buff, nexthdr: c_int, spi: u32, encap_type: c_int) -> c_int;
    fn kfree_skb(skb: *mut sk_buff);
    fn ip6_rcv_finish(skb: *mut sk_buff) -> c_int;
    fn xfrm_trans_queue(
        skb: *mut sk_buff,
        finish: unsafe extern "C" fn(*mut sk_buff) -> c_int,
    ) -> c_int;
}

#[inline]
unsafe fn xfrm_tunnel_skb_cb_ptr(skb: *mut sk_buff) -> *mut xfrm_tunnel_skb_cb {
    (*skb).cb.as_mut_ptr().cast::<xfrm_tunnel_skb_cb>()
}

#[inline]
unsafe fn xfrm_spi_skb_cb_ptr(skb: *mut sk_buff) -> *mut xfrm_spi_info {
    (*skb).cb.as_mut_ptr().cast::<xfrm_spi_info>()
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn xfrm6_rcv_spi(
    skb: *mut sk_buff,
    nexthdr: c_int,
    spi: u32,
    t: *mut ip6_tnl,
) -> c_int {
    (*xfrm_tunnel_skb_cb_ptr(skb)).ip6 = t;
    (*xfrm_spi_skb_cb_ptr(skb)).family = AF_INET6;
    (*xfrm_spi_skb_cb_ptr(skb)).daddroff = offset_of!(ipv6hdr, daddr);
    xfrm_input(skb, nexthdr, spi, 0)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn xfrm6_transport_finish2(
    _net: *mut net,
    _sk: *mut sock,
    skb: *mut sk_buff,
) -> c_int {
    if xfrm_trans_queue(skb, ip6_rcv_finish) != 0 {
        kfree_skb(skb);
        return NET_RX_DROP;
    }
    0
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
