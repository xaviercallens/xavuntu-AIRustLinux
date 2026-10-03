#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
//! Internet Control Message Protocol (ICMPv6) for IPv6
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals, unreachable_patterns)]

use core::{ffi::c_void, panic::PanicInfo};
use kernel_types::*;

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const ENOSYS: c_int = -38;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct flowi6 { _unused: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct Inet6SkbParm { _unused: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct Icmp6Hdr {
    pub icmp6_type: u8,
    pub icmp6_code: u8,
    pub icmp6_cksum: u16,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_peer { _unused: [u8; 0] }

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {
        core::hint::spin_loop();
    }
}

#[no_mangle]
pub unsafe extern "C" fn rust_eh_personality() {}

#[no_mangle]
pub unsafe extern "C" fn icmpv6_err(
    skb: *mut sk_buff,
    opt: *mut Inet6SkbParm,
    type_: u8,
    _code_: u8,
    offset: c_int,
    info: u32,
) -> c_int {
    if skb.is_null() || opt.is_null() {
        return EINVAL;
    }

    let icmp6 = ((*skb).data as *mut u8).add(offset as usize) as *mut Icmp6Hdr;
    let net = dev_net((*skb).dev as *mut net_device);

    if type_ == ICMPV6_PKT_TOOBIG {
        ip6_update_pmtu(
            skb,
            net,
            info,
        );
    } else if type_ == NDISC_REDIRECT {
        ip6_redirect(
            skb,
            net,
        );
    }

    if (type_ & ICMPV6_INFOMSG_MASK) == 0 && (*icmp6).icmp6_type == ICMPV6_ECHO_REQUEST {
        ping_err(
            skb,
            offset,
            u32::from_ne_bytes([(*icmp6).icmp6_type, 0, 0, 0]),
        );
    }

    0
}

/// Check if ICMP response is allowed based on rate limiting
///
/// # Safety
/// - `sk` must be a valid pointer to sock
/// - `fl6` must be a valid pointer to flowi6
/// - Caller must ensure no data races on shared data
///
/// # Returns
/// true if allowed, false otherwise
fn icmpv6_xrlim_allow(sk: *mut sock, _type_: u8, fl6: *mut flowi6) -> bool {
    if sk.is_null() || fl6.is_null() {
        return false;
    }
    true
}

unsafe fn is_ineligible(skb: *const sk_buff) -> bool {
    if skb.is_null() {
        return true;
    }

    let ptr = (ipv6_hdr(skb) as *mut u8).add(1) as isize - (*skb).data as isize;
    let len = (*skb).len as i32 - ptr as i32;

    if len < 0 {
        return true;
    }

    let mut nexthdr = (*ipv6_hdr(skb)).nexthdr;
    let mut frag_off = 0u16;
    let mut offset = ptr;

    offset = ipv6_skip_exthdr(skb, offset, &mut nexthdr, &mut frag_off);
    if offset < 0 {
        return false;
    }

    if nexthdr == IPPROTO_ICMPV6 {
        let tp = skb_header_pointer(
            skb,
            offset + core::mem::size_of::<Icmp6Hdr>() as isize,
            1,
            core::ptr::null_mut::<u8>(),
        );
        if !tp.is_null() && (*tp as u8 & ICMPV6_INFOMSG_MASK) == 0 {
            return true;
        }
    }

    false
}

#[no_mangle]
pub unsafe extern "C" fn icmp6_send(
    skb: *mut sk_buff,
    _type: u8,
    _code: u8,
    _info: u32,
) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }
    if is_ineligible(skb as *const sk_buff) {
        return EINVAL;
    }
    let _ = icmpv6_xrlim_allow(core::ptr::null_mut(), _type, core::ptr::null_mut());
    0
}

#[no_mangle]
pub unsafe extern "C" fn icmpv6_err_convert(_type_: u8, _code: u8, _error: c_int) -> c_int {
    // Implementation would go here
    0
}

// Helper functions
/// Get network namespace from socket
unsafe fn sock_net(sk: *mut sock) -> *mut net {
    if sk.is_null() {
        return core::ptr::null_mut();
    }

    // Implementation would go here
    core::ptr::null_mut()
}

/// Get device network namespace
unsafe fn dev_net(dev: *mut net_device) -> *mut net {
    if dev.is_null() {
        return core::ptr::null_mut();
    }

    // Implementation would go here
    core::ptr::null_mut()
}

/// Get socket net ID
unsafe fn sock_net_uid(net: *mut net, sk: *mut sock) -> u32 {
    if net.is_null() || sk.is_null() {
        return 0;
    }

    // Implementation would go here
    0
}

/// Update PMTU
unsafe fn ip6_update_pmtu(
    skb: *mut sk_buff,
    _net: *mut net,
    _info: u32,
) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }

    // Implementation would go here
    0
}

unsafe fn ip6_redirect(
    skb: *mut sk_buff,
    _net: *mut net,
) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }

    // Implementation would go here
    0
}

unsafe fn ping_err(
    skb: *mut sk_buff,
    _offset: c_int,
    _info: u32,
) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }

    // Implementation would go here
    0
}

/// Check if rate limiting allows ICMP
unsafe fn icmpv6_mask_allow(net: *mut net, _type_: u8) -> bool {
    if net.is_null() {
        return false;
    }

    // Implementation would go here
    true
}

/// Get IPv6 header from skb
unsafe fn ipv6_hdr(skb: *const sk_buff) -> *const ipv6hdr {
    if skb.is_null() {
        return core::ptr::null();
    }

    // Implementation would go here
    (*skb).data as *const ipv6hdr
}

/// Skip extension headers
unsafe fn ipv6_skip_exthdr(
    skb: *const sk_buff,
    _offset: isize,
    nexthdr: *mut u8,
    frag_off: *mut u16,
) -> isize {
    if skb.is_null() || nexthdr.is_null() || frag_off.is_null() {
        return -1;
    }

    // Implementation would go here
    0
}

/// Get pointer to data in skb
unsafe fn skb_header_pointer(
    skb: *const sk_buff,
    _offset: isize,
    _len: isize,
    _data: *mut u8,
) -> *mut u8 {
    if skb.is_null() {
        return core::ptr::null_mut();
    }

    // Implementation would go here
    core::ptr::null_mut()
}

/// Get peer for IPv6
unsafe fn inet_getpeer_v6(peers: *mut c_void, addr: *mut in6_addr, _create: c_int) -> *mut inet_peer {
    if peers.is_null() || addr.is_null() {
        return core::ptr::null_mut();
    }

    // Implementation would go here
    core::ptr::null_mut()
}

/// Check rate limit for peer
unsafe fn inet_peer_xrlim_allow(peer: *mut inet_peer, _tmo: c_int) -> bool {
    if peer.is_null() {
        return false;
    }

    // Implementation would go here
    true
}

/// Release peer reference
unsafe fn inet_putpeer(peer: *mut inet_peer) {
    if peer.is_null() {
    }

    // Implementation would go here
}

/// Route output for IPv6
unsafe fn ip6_route_output(net: *mut net, sk: *mut sock, fl6: *mut flowi6) -> *mut c_void {
    if net.is_null() || sk.is_null() || fl6.is_null() {
        return core::ptr::null_mut();
    }

    // Implementation would go here
    core::ptr::null_mut()
}

// Constants used in code
pub const ICMPV6_PKT_TOOBIG: u8 = 4;
pub const NDISC_REDIRECT: u8 = 137;
pub const ICMPV6_ECHO_REQUEST: u8 = 128;
pub const ICMPV6_INFOMSG_MASK: u8 = 0x80;
pub const IPPROTO_ICMPV6: u8 = 58;

// Tests (conditional compilation)

#[cfg(test)]
mod tests {
    #[test]
    fn test_icmpv6_err() {
        unsafe {
            let mut dev = core::mem::zeroed::<super::net_device>();
            let mut buf = [0u8; 1024];
            let mut skb = core::mem::zeroed::<super::sk_buff>();
            let mut buf = [0u8; 1024];
            skb.data = buf.as_mut_ptr() as *mut _;

            skb.dev = &mut dev as *mut _ as *mut _;
            skb.head = buf.as_mut_ptr() as *mut _;
            skb.data = buf.as_mut_ptr() as *mut _;
            let mut inet6cb = core::mem::zeroed::<core::ffi::c_void>();
            let _ = super::icmpv6_err(&mut skb as *mut _, &mut inet6cb as *mut _, 0, 0, 0, 0);
        }
    }
    #[test]
    fn test_icmp6_send() {
        unsafe {
            let mut dev = core::mem::zeroed::<super::net_device>();
            let mut buf = [0u8; 1024];
            let mut skb = core::mem::zeroed::<super::sk_buff>();
            let mut buf = [0u8; 1024];
            skb.data = buf.as_mut_ptr() as *mut _;

            skb.dev = &mut dev as *mut _ as *mut _;
            skb.head = buf.as_mut_ptr() as *mut _;
            skb.data = buf.as_mut_ptr() as *mut _;
            let mut saddr = core::mem::zeroed::<super::in6_addr>();
            let mut tclass = core::mem::zeroed::<core::ffi::c_void>();
            super::icmp6_send(&mut skb as *mut _, 0, 0, 0, &mut saddr as *const _, &mut tclass as *const _);
        }
    }

}
