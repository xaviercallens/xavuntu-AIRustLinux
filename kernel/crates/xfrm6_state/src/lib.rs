#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
//! IPv6 XFRM state management module
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]

use core::ffi::c_int;
use core::panic::PanicInfo;
use kernel_types::*;

pub const AF_INET6: c_int = 10; pub const IPPROTO_IPV6: c_int = 41;

// Function pointer types
type OutputFn = unsafe extern "C" fn(*mut c_void, *mut c_void) -> c_int;
type TransportFinishFn = unsafe extern "C" fn(*mut c_void, *mut c_void) -> c_int;
type LocalErrorFn = unsafe extern "C" fn(*mut c_void, *mut sockaddr, *mut c_void) -> c_int;

#[repr(C)]
pub struct xfrm_state { _priv: [u8; 0] }

#[repr(C)]
pub struct sk_buff { _priv: [u8; 0] }

#[repr(C)]
pub struct sockaddr { _priv: [u8; 0] }

#[repr(C)]
pub struct xfrm_state_afinfo {
    family: c_int,
    proto: c_int,
    output: OutputFn,
    transport_finish: TransportFinishFn,
    local_error: LocalErrorFn,
}

extern "C" {
    fn xfrm_state_register_afinfo(info: *mut xfrm_state_afinfo) -> c_int;
    fn xfrm_state_unregister_afinfo(info: *mut xfrm_state_afinfo);
    fn xfrm6_output(x: *mut c_void, skb: *mut c_void) -> c_int;
    fn xfrm6_transport_finish(skb: *mut c_void, x: *mut c_void) -> c_int;
    fn xfrm6_local_error(skb: *mut c_void, addr: *mut sockaddr, x: *mut c_void) -> c_int;
}

struct SyncWrapper<T>(core::cell::UnsafeCell<T>);
unsafe impl<T> Sync for SyncWrapper<T> {}

static XFRM6_STATE_AFINFO: SyncWrapper<xfrm_state_afinfo> = SyncWrapper(core::cell::UnsafeCell::new(xfrm_state_afinfo {
    family: AF_INET6,
    proto: IPPROTO_IPV6,
    output: xfrm6_output,
    transport_finish: xfrm6_transport_finish,
    local_error: xfrm6_local_error,
}));

#[unsafe(no_mangle)]
pub unsafe extern "C" fn xfrm6_state_init() -> c_int {
    unsafe { xfrm_state_register_afinfo(XFRM6_STATE_AFINFO.0.get()) }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn xfrm6_state_fini() {
    unsafe { xfrm_state_unregister_afinfo(XFRM6_STATE_AFINFO.0.get()) }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}
