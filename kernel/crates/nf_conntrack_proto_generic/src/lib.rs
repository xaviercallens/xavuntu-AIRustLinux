#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! This module provides FFI-compatible Rust bindings for the Linux kernel's
//! generic protocol connection tracking implementation. It maintains ABI
//! compatibility with the original C implementation for netfilter/conntrack.

#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(clippy::all)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::ffi::c_void;
use core::ptr;
use kernel_types::*;

pub const HZ: c_uint = 100;
pub const CTA_TIMEOUT_GENERIC_TIMEOUT: usize = 1;
pub const CTA_TIMEOUT_GENERIC_MAX: usize = 2;
pub const ENOSPC: c_int = -12;

pub const NLA_U32: c_uint = 1; pub const IPPROTO_RAW: u8 = 255;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nlattr { _unused: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
struct NfGenericNet { timeout: c_uint }

#[repr(C)]
#[derive(Copy, Clone)]
struct NlaPolicy { type_: c_uint }

unsafe impl Send for NlaPolicy {}
unsafe impl Sync for NlaPolicy {}

#[repr(C)]
#[derive(Copy, Clone)]
struct NfCtnlTimeout {
    nlattr_to_obj: Option<
        unsafe extern "C" fn(tb: *mut *mut nlattr, net: *mut c_void, data: *mut c_void) -> c_int,
    >,
    obj_to_nlattr: Option<unsafe extern "C" fn(skb: *mut c_void, data: *const c_void) -> c_int>,
    nlattr_max: c_int,
    obj_size: size_t,
    nla_policy: *const NlaPolicy,
}

unsafe impl Send for NfCtnlTimeout {}
unsafe impl Sync for NfCtnlTimeout {}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct NfConntrackL4proto { l4proto: u8, ctnl_timeout: NfCtnlTimeout }

#[cfg(CONFIG_NF_CONNTRACK_TIMEOUT)]
#[no_mangle]
static generic_timeout_nla_policy: [NlaPolicy; CTA_TIMEOUT_GENERIC_MAX + 1] = {
    let mut arr = [NlaPolicy { type_: 0 }; CTA_TIMEOUT_GENERIC_MAX + 1];
    arr[CTA_TIMEOUT_GENERIC_TIMEOUT] = NlaPolicy { type_: NLA_U32 };
    arr
};

#[no_mangle]
pub static NF_CONNTRACK_L4PROTO_GENERIC: NfConntrackL4proto = NfConntrackL4proto {
    l4proto: 255,
    ctnl_timeout: NfCtnlTimeout {
        #[cfg(CONFIG_NF_CONNTRACK_TIMEOUT)]
        nlattr_to_obj: Some(generic_timeout_nlattr_to_obj),
        #[cfg(not(CONFIG_NF_CONNTRACK_TIMEOUT))]
        nlattr_to_obj: None,

        #[cfg(CONFIG_NF_CONNTRACK_TIMEOUT)]
        obj_to_nlattr: Some(generic_timeout_obj_to_nlattr),
        #[cfg(not(CONFIG_NF_CONNTRACK_TIMEOUT))]
        obj_to_nlattr: None,

        #[cfg(CONFIG_NF_CONNTRACK_TIMEOUT)]
        nlattr_max: CTA_TIMEOUT_GENERIC_MAX,
        #[cfg(not(CONFIG_NF_CONNTRACK_TIMEOUT))]
        nlattr_max: 0,

        #[cfg(CONFIG_NF_CONNTRACK_TIMEOUT)]
        obj_size: size_of::<c_uint>(),
        #[cfg(not(CONFIG_NF_CONNTRACK_TIMEOUT))]
        obj_size: 0,

        #[cfg(CONFIG_NF_CONNTRACK_TIMEOUT)]
        nla_policy: &GENERIC_TIMEOUT_NLA_POLICY as *const NlaPolicy,
        #[cfg(not(CONFIG_NF_CONNTRACK_TIMEOUT))]
        nla_policy: ptr::null(),
    },
};

// Static data
#[cfg(CONFIG_NF_CONNTRACK_TIMEOUT)]
#[no_mangle]
static GENERIC_TIMEOUT_NLA_POLICY: [NlaPolicy; CTA_TIMEOUT_GENERIC_MAX as usize + 1] = {
    let mut arr = [NlaPolicy { type_: 0 }; CTA_TIMEOUT_GENERIC_MAX as usize + 1];
    arr[CTA_TIMEOUT_GENERIC_TIMEOUT as usize] = NlaPolicy { type_: 1 }; // NLA_U32
    arr
};

// Extern declarations for kernel functions
extern "C" {
    fn nf_generic_pernet(net: *mut c_void) -> *mut NfGenericNet;
    fn nla_get_be32(attr: *const nlattr) -> u32;
    fn nla_put_be32(skb: *mut c_void, type_: c_int, data: u32) -> c_int;
    fn ntohl(x: u32) -> u32;
    fn htonl(x: u32) -> u32;
}

#[inline(always)]
unsafe extern "C" fn nf_ct_generic_timeout() -> c_uint {
    600 * HZ
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_generic_init_net(net: *mut c_void) {
    let gn = nf_generic_pernet(net);
    (*gn).timeout = NF_CT_GENERIC_TIMEOUT;
}

#[no_mangle]
pub unsafe extern "C" fn generic_timeout_nlattr_to_obj(
    tb: *mut *mut nlattr,
    net: *mut c_void,
    data: *mut c_void,
) -> c_int {
    let gn = nf_generic_pernet(net);
    let timeout = data as *mut c_uint;
    let gn_timeout = &mut (*gn).timeout;

    if timeout.is_null() {
        return EINVAL;
    }

    let attr = *tb.add(CTA_TIMEOUT_GENERIC_TIMEOUT);

    if !attr.is_null() {
        let value = nla_get_be32(attr);
        *timeout = ntohl(value) * HZ;
    } else {
        *timeout = *gn_timeout;
    }

    0
}

#[no_mangle]
pub unsafe extern "C" fn generic_timeout_obj_to_nlattr(
    skb: *mut c_void,
    data: *const c_void,
) -> c_int {
    let timeout = data as *const c_uint;
    let timeout_val = *timeout;

    if nla_put_be32(skb, CTA_TIMEOUT_GENERIC_TIMEOUT as c_int, htonl(timeout_val / HZ)) != 0 {
        return ENOSPC;
    }

    0
}

// Constants
#[no_mangle]
pub static NF_CT_GENERIC_TIMEOUT: c_uint = 600 * HZ as u32;
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
