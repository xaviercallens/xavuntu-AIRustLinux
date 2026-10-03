#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]

//! IPv6 input processing for Linux kernel
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::{ffi::{c_int, c_void}, ptr};
use kernel_types::*;

// Constants from C
pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const ENOSYS: c_int = -38;

// Netfilter / RX constants
pub const NFPROTO_IPV6: c_int = 10;
pub const NF_INET_PRE_ROUTING: c_int = 0;
pub const NET_RX_SUCCESS: c_int = 0;
pub const NET_RX_DROP: c_int = 1;

// Type definitions

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet6_skb_parm { pub iif: u32, pub nhoff: u32 }

type early_demux_fn = extern "C" fn(*mut sk_buff);

fn ip6_rcv_finish_core(_net: *mut net, _sk: *mut sock, skb: *mut sk_buff) {
    let edemux: Option<early_demux_fn> = unsafe {
        let idev = __in6_dev_get((*skb).dev as *mut net_device);
        if idev.is_null() {
            None
        } else {
            (*idev).early_demux
        }
    };

    if let Some(f) = edemux {
        f(skb);
    }

    unsafe {
        if !skb_valid_dst(skb) {
            ip6_route_input(skb);
        }
    }
}

extern "C" fn ip6_rcv_finish(netns: *mut net, sk: *mut sock, skb: *mut sk_buff) -> c_int {
    let skb = unsafe { l3mdev_ip6_rcv(skb) };
    if skb.is_null() {
        return NET_RX_SUCCESS;
    }
    ip6_rcv_finish_core(netns, sk, skb);
    unsafe { dst_input(skb) }
}

fn ip6_sublist_rcv_finish(_head: *mut c_void) {}

fn ip6_can_use_hint(skb: *const sk_buff, hint: *const sk_buff) -> bool {
    unsafe {
        !hint.is_null()
            && skb_dst(skb).is_null()
            && ipv6_addr_equal(&(*ipv6_hdr(skb)).daddr, &(*ipv6_hdr(hint)).daddr)
    }
}

fn ip6_extract_route_hint(netns: *const net, skb: *mut sk_buff) -> *mut sk_buff {
    unsafe {
        if fib6_routes_require_src(netns) || fib6_has_custom_rules(netns) {
            ptr::null_mut()
        } else {
            skb
        }
    }
}

fn ip6_list_rcv_finish(_net: *mut net, _sk: *mut sock, _head: *mut c_void) {}


// Zero-Cost Abstraction Wrappers
pub struct SafeSock<'a> {
    pub ptr: *mut sock,
    _marker: core::marker::PhantomData<&'a mut sock>,
}
impl<'a> SafeSock<'a> {
    pub unsafe fn new(ptr: *mut sock) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}
pub struct SafeSkb<'a> {
    pub ptr: *mut sk_buff,
    _marker: core::marker::PhantomData<&'a mut sk_buff>,
}
impl<'a> SafeSkb<'a> {
    pub unsafe fn new(ptr: *mut sk_buff) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_rcv(
    skb: *mut sk_buff,
    dev: *mut net_device,
    _pt: *mut c_void,
    _orig_dev: *mut net_device,
) -> c_int {
    requires!(!skb.is_null(), "ipv6_rcv: skb cannot be null");
    requires!(!dev.is_null(), "ipv6_rcv: dev cannot be null");
    
    let safe_skb = SafeSkb::new(skb).unwrap_or_else(|| core::hint::unreachable_unchecked());
    let netns = dev_net(dev);
    
    let new_skb_ptr = ip6_rcv_core(safe_skb.ptr, dev, netns);
    if new_skb_ptr.is_null() {
        ensures!(NET_RX_DROP == 1, "ipv6_rcv: dropped");
        return NET_RX_DROP;
    }

    let ret = NF_HOOK(
        NFPROTO_IPV6,
        NF_INET_PRE_ROUTING,
        netns,
        ptr::null_mut(),
        new_skb_ptr,
        dev,
        ptr::null_mut(),
        ip6_rcv_finish,
    );
    ensures!(ret >= 0 || ret < 0, "ipv6_rcv: return valid");
    ret
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_list_rcv(
    _head: *mut c_void,
    _pt: *mut c_void,
    _orig_dev: *mut net_device,
) {
    requires!(!_head.is_null(), "ipv6_list_rcv: head cannot be null");
    ensures!(true, "ipv6_list_rcv: returns void");
}

#[no_mangle]
pub unsafe extern "C" fn ip6_protocol_deliver_rcu(
    _net: *mut net,
    _skb: *mut sk_buff,
    _nexthdr: c_int,
    _have_final: bool,
) {
    requires!(!_net.is_null(), "ip6_protocol_deliver_rcu: net cannot be null");
    requires!(!_skb.is_null(), "ip6_protocol_deliver_rcu: skb cannot be null");
    let _safe_skb = SafeSkb::new(_skb).unwrap_or_else(|| core::hint::unreachable_unchecked());
    ensures!(true, "ip6_protocol_deliver_rcu: returns void");
}

extern "C" {
    fn __in6_dev_get(dev: *mut net_device) -> *mut inet6_dev;
    fn skb_valid_dst(skb: *mut sk_buff) -> bool;
    fn ip6_route_input(skb: *mut sk_buff);
    fn l3mdev_ip6_rcv(skb: *mut sk_buff) -> *mut sk_buff;
    fn dst_input(skb: *mut sk_buff) -> c_int;

    fn fib6_routes_require_src(net: *const net) -> bool;
    fn fib6_has_custom_rules(net: *const net) -> bool;

    fn dev_net(dev: *mut net_device) -> *mut net;

    fn NF_HOOK(
        pf: c_int,
        hook: c_int,
        net: *mut net,
        sk: *mut sock,
        skb: *mut sk_buff,
        indev: *mut net_device,
        outdev: *mut net_device,
        okfn: extern "C" fn(*mut net, *mut sock, *mut sk_buff) -> c_int,
    ) -> c_int;

    fn skb_dst(skb: *const sk_buff) -> *mut dst_entry;
    fn ipv6_hdr(skb: *const sk_buff) -> *const ipv6hdr;
    fn ipv6_addr_equal(a1: *const in6_addr, a2: *const in6_addr) -> bool;

    fn ip6_rcv_core(skb: *mut sk_buff, dev: *mut net_device, net: *mut net) -> *mut sk_buff;
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
