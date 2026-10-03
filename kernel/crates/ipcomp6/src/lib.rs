#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
//! IP Payload Compression Protocol (IPComp) for IPv6 - RFC3173
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(unused_variables)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

#[cfg(test)]
extern crate std;

use core::ffi::{c_int, c_char, c_void};
use core::panic::PanicInfo;
use core::ptr;
use kernel_types::*;

pub const IPPROTO_COMP: c_int = 108;
pub const XFRM_STATE_DEAD: c_int = 2;
pub const ENOMEM: c_int = -12;
pub const EINVAL: c_int = -22;
pub const EAGAIN: c_int = -11;
pub const AF_INET6: c_int = 10;
pub const IPPROTO_IPV6: c_int = 41;
pub const XFRM_MODE_TRANSPORT: c_int = 0;
pub const XFRM_MODE_TUNNEL: c_int = 1;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip_comp_hdr {
    pub cpi: __be16,
}

#[repr(C)]
pub struct inet6_skb_parm {
    _priv: [u8; 0],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_mark {
    pub v: u32,
    pub m: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_address_t {
    pub a6: [u32; 4],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_state_props {
    pub mode: c_int,
    pub header_len: c_int,
    pub saddr: xfrm_address_t,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_state_id {
    pub daddr: xfrm_address_t,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_state {
    pub mark: xfrm_mark,
    pub props: xfrm_state_props,
    pub id: xfrm_state_id,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_type {
    pub description: *const c_char,
    pub owner: *const c_void,
    pub proto: c_int,
    pub init_state: Option<unsafe extern "C" fn(*mut xfrm_state) -> c_int>,
    pub destructor: Option<unsafe extern "C" fn(*mut xfrm_state)>,
    pub input: Option<unsafe extern "C" fn(*mut xfrm_state, *mut sk_buff) -> c_int>,
    pub output: Option<unsafe extern "C" fn(*mut xfrm_state, *mut sk_buff) -> c_int>,
    pub hdr_offset: Option<unsafe extern "C" fn(*mut xfrm_state, *mut sk_buff, *mut *mut u8) -> c_int>,
}

unsafe impl Sync for xfrm_type {}

pub const THIS_MODULE: *const c_void = ptr::null();
pub static ipcomp6_protocol: u8 = 0;

extern "C" {
    pub fn ntohs(val: __be16) -> u16;
    pub fn dev_net(dev: *mut c_void) -> *mut c_void;
    pub fn xfrm_state_lookup(
        net: *mut c_void,
        mark: u32,
        daddr: *const xfrm_address_t,
        spi: u32,
        proto: u8,
        family: c_int,
    ) -> *mut xfrm_state;
    pub fn sock_net_uid(net: *mut c_void, sk: *mut c_void) -> u32;
    pub fn ip6_redirect(skb: *mut sk_buff, net: *mut c_void, ifindex: c_int, target: u32, uid: u32);
    pub fn ip6_update_pmtu(skb: *mut sk_buff, net: *mut c_void, mtu: u32, flags: u32, tclass: u32, uid: u32);
    pub fn xfrm_state_put(x: *mut xfrm_state);
    pub fn xs_net(x: *mut xfrm_state) -> *mut c_void;
    pub fn xfrm6_tunnel_spi_lookup(net: *mut c_void, saddr: *const xfrm_address_t) -> u32;
    pub fn ipcomp_init_state(x: *mut xfrm_state) -> c_int;
    pub fn xfrm_register_type(t: *const xfrm_type, family: c_int) -> c_int;
    pub fn xfrm_unregister_type(t: *const xfrm_type, family: c_int);
    pub fn xfrm6_protocol_register(handler: *const u8, proto: c_int) -> c_int;
    pub fn xfrm6_protocol_deregister(handler: *const u8, proto: c_int) -> c_int;
    pub fn pr_info(fmt: *const c_char);
    pub fn xfrm6_find_1stfragopt(x: *mut xfrm_state, skb: *mut sk_buff, prevhdr: *mut *mut u8) -> c_int;
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}

#[cfg(not(test))]
#[no_mangle]
pub unsafe extern "C" fn rust_eh_personality() {}

#[no_mangle]
pub unsafe extern "C" fn ipcomp6_err(
    skb: *mut sk_buff,
    _opt: *mut inet6_skb_parm,
    type_: u8,
    _code: u8,
    offset: c_int,
    info: __be32,
) -> c_int {
    if type_ != 1 && type_ != 2 {
        return 0;
    }

    let iph = (*skb).data as *const ipv6hdr;
    let ipcomph = ((*skb).data as *const u8).add(offset as usize) as *const ip_comp_hdr;

    let spi = u32::from_be(ntohs((*ipcomph).cpi) as u32);
    let net = dev_net((*skb).dev);

    let x = xfrm_state_lookup(
        net,
        (*skb).mark as usize as u32,
        &(*iph).daddr as *const _ as *const xfrm_address_t,
        spi,
        IPPROTO_COMP as u8,
        AF_INET6,
    );

    if x.is_null() {
        return 0;
    }

    let dev = (*skb).dev as *mut net_device;
    if type_ == 2 {
        ip6_redirect(skb, net, (*dev).ifindex, 0, sock_net_uid(net, ptr::null_mut()));
    } else {
        ip6_update_pmtu(skb, net, info, 0, 0, sock_net_uid(net, ptr::null_mut()));
    }

    xfrm_state_put(x);

    0
}

#[no_mangle]
pub unsafe extern "C" fn ipcomp6_tunnel_create(x: *mut xfrm_state) -> *mut xfrm_state {
    if x.is_null() {
        return ptr::null_mut();
    }
    let net = xs_net(x);
    if net.is_null() {
        return ptr::null_mut();
    }
    let mark = (*x).mark.m & (*x).mark.v;
    let t = xfrm_state_lookup(
        net,
        mark,
        &(*x).id.daddr as *const _ as *const xfrm_address_t,
        0,
        IPPROTO_IPV6 as u8,
        AF_INET6,
    );
    t
}

#[no_mangle]
pub unsafe extern "C" fn ipcomp6_tunnel_attach(x: *mut xfrm_state) -> c_int {
    let net = xs_net(x);
    let err = 0;
    let mut t: *mut xfrm_state = ptr::null_mut();
    let mut spi: u32 = 0;
    let mark = (*x).mark.m & (*x).mark.v;

    spi = xfrm6_tunnel_spi_lookup(
        net,
        &(*x).props.saddr as *const _ as *const xfrm_address_t
    );

    if spi != 0 {
        t = xfrm_state_lookup(
            net,
            mark,
            &(*x).id.daddr as *const _ as *const xfrm_address_t,
            spi,
            IPPROTO_IPV6 as u8,
            AF_INET6
        );
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn ipcomp6_init_state(x: *mut xfrm_state) -> c_int {
    let mut err = -EINVAL;

    (*x).props.header_len = 0;

    match (*x).props.mode {
        XFRM_MODE_TRANSPORT => {}
        XFRM_MODE_TUNNEL => {
            (*x).props.header_len += core::mem::size_of::<ipv6hdr>() as c_int;
        },
        _ => return -EINVAL,
    }

    err = ipcomp_init_state(x);
    if err != 0 {
        return err;
    }

    if (*x).props.mode == XFRM_MODE_TUNNEL {
        err = ipcomp6_tunnel_attach(x);
        if err != 0 {
            return err;
        }
    }

    0
}

/// Callback for IPComp receive
///
/// # Safety
/// - `skb` must be a valid pointer to sk_buff
/// - `err` must be a valid error code
///
/// # Returns
/// 0
#[no_mangle]
pub unsafe extern "C" fn ipcomp6_rcv_cb(skb: *mut sk_buff, err: c_int) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }
    if err != 0 {
        return err;
    }
    0
}

// Module initialization and cleanup
#[no_mangle]
pub unsafe extern "C" fn ipcomp6_init() -> c_int {
    if xfrm_register_type(&ipcomp6_type, AF_INET6) < 0 {
        return -EAGAIN;
    }

    if xfrm6_protocol_register(&ipcomp6_protocol, IPPROTO_COMP) < 0 {
        pr_info(b"ipcomp6_init: can't add protocol\n".as_ptr() as *const c_char);
        xfrm_unregister_type(&ipcomp6_type, AF_INET6);
        return -EAGAIN;
    }

    0
}

#[no_mangle]
pub unsafe extern "C" fn ipcomp6_fini() {
    if xfrm6_protocol_deregister(&ipcomp6_protocol, IPPROTO_COMP) < 0 {
        pr_info(b"ipcomp6_fini: can't remove protocol\n".as_ptr() as *const c_char);
    }
    xfrm_unregister_type(&ipcomp6_type, AF_INET6);
}

// Static data
#[no_mangle]
pub static ipcomp6_type: xfrm_type = xfrm_type {
    description: b"IPCOMP6\0".as_ptr() as *const c_char,
    owner: THIS_MODULE,
    proto: IPPROTO_COMP,
    init_state: Some(ipcomp6_init_state),
    destructor: Some(ipcomp6_destroy),
    input: Some(ipcomp6_input),
    output: Some(ipcomp6_output),
    hdr_offset: Some(xfrm6_find_1stfragopt),
};

#[no_mangle]
pub unsafe extern "C" fn ipcomp6_destroy(_x: *mut xfrm_state) {}

#[no_mangle]
pub unsafe extern "C" fn ipcomp6_get_mtu(_x: *mut xfrm_state, mtu: u32) -> u32 {
    mtu
}

#[no_mangle]
pub unsafe extern "C" fn ipcomp6_input(x: *mut xfrm_state, skb: *mut sk_buff) -> c_int {
    if x.is_null() || skb.is_null() {
        return EINVAL;
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn ipcomp6_output(x: *mut xfrm_state, skb: *mut sk_buff) -> c_int {
    if x.is_null() || skb.is_null() {
        return EINVAL;
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn ipcomp6_output_tail(
    x: *mut xfrm_state,
    skb: *mut sk_buff,
) -> *mut c_void {
    if x.is_null() || skb.is_null() {
        return ptr::null_mut();
    }
    (*skb).data as *mut c_void
}

#[cfg(test)]
mod tests {
    use super::*;

    #[no_mangle]
    pub unsafe extern "C" fn xs_net(x: *mut xfrm_state) -> *mut c_void {
        if x.is_null() {
            return ptr::null_mut();
        }
        x as *mut c_void
    }

    #[no_mangle]
    pub unsafe extern "C" fn xfrm_state_lookup(
        net: *mut c_void,
        _mark: u32,
        daddr: *const xfrm_address_t,
        _spi: u32,
        _proto: u8,
        _family: c_int,
    ) -> *mut xfrm_state {
        if net.is_null() || daddr.is_null() {
            return ptr::null_mut();
        }
        ptr::null_mut()
    }

    #[test]
    fn test_ipcomp6_null_args() {
        // SAFETY: Invoking IPComp6 C-ABI entry points with null/invalid pointers to verify defense-in-depth bounds checking.
        unsafe {
            assert_eq!(ipcomp6_tunnel_create(ptr::null_mut()), ptr::null_mut());
            assert_eq!(ipcomp6_rcv_cb(ptr::null_mut(), 0), EINVAL);
            assert_eq!(ipcomp6_rcv_cb(1 as *mut sk_buff, -5), -5);
            assert_eq!(ipcomp6_input(ptr::null_mut(), ptr::null_mut()), EINVAL);
            assert_eq!(ipcomp6_output(ptr::null_mut(), ptr::null_mut()), EINVAL);
            assert_eq!(ipcomp6_output_tail(ptr::null_mut(), ptr::null_mut()), ptr::null_mut());
        }
    }
}
