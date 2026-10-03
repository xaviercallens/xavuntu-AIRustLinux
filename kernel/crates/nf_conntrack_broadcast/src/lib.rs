#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
#[cfg(not(target_arch = "x86_64"))]
extern crate alloc;
#[cfg(not(target_arch = "x86_64"))]
use alloc::boxed::Box;
use kernel_types::*;

#[cfg(not(target_arch = "x86_64"))]
use core::alloc::{GlobalAlloc, Layout};

#[cfg(not(target_arch = "x86_64"))]
struct KernelAlloc;

#[cfg(not(target_arch = "x86_64"))]
unsafe impl GlobalAlloc for KernelAlloc {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        unsafe extern "C" {
            fn kmalloc(size: core::ffi::c_ulong) -> *mut core::ffi::c_void;
        }
        unsafe { kmalloc(layout.size() as core::ffi::c_ulong) as *mut u8 }
    }

    unsafe fn dealloc(&self, ptr: *mut u8, _layout: Layout) {
        unsafe extern "C" {
            fn kfree(ptr: *mut core::ffi::c_void);
        }
        unsafe { kfree(ptr as *mut core::ffi::c_void) }
    }
}

#[cfg(not(target_arch = "x86_64"))]
#[global_allocator]
static GLOBAL_ALLOCATOR: KernelAlloc = KernelAlloc;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_broadcast {
    pub ct: *mut c_void,
    pub ctinfo: u8,
    pub ctproto: u8,
    pub ctzone: u16,
    pub ctmark: u32,
    pub ctmask: u32,
    pub ctmark_mask: u32,
    pub ctmark_set: u32,
    pub ctmark_clear: u32,
    pub ctmark_xor: u32,
    pub ctmark_or: u32,
    pub ctmark_and: u32,
    pub ctmark_set_mask: u32,
    pub ctmark_clear_mask: u32,
    pub ctmark_xor_mask: u32,
    pub ctmark_or_mask: u32,
    pub ctmark_and_mask: u32,
    pub ctmark_set_xor: u32,
    pub ctmark_clear_xor: u32,
    pub ctmark_xor_xor: u32,
    pub ctmark_or_xor: u32,
    pub ctmark_and_xor: u32,
    pub ctmark_set_or: u32,
    pub ctmark_clear_or: u32,
    pub ctmark_xor_or: u32,
    pub ctmark_or_or: u32,
    pub ctmark_and_or: u32,
    pub ctmark_set_and: u32,
    pub ctmark_clear_and: u32,
    pub ctmark_xor_and: u32,
    pub ctmark_or_and: u32,
    pub ctmark_and_and: u32,
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_broadcast_init(
    ct: *mut c_void,
    ctinfo: u8,
    ctproto: u8,
    ctzone: u16,
    ctmark: u32,
    ctmask: u32,
) -> *mut nf_conntrack_broadcast {
    let nfct_broadcast = Box::new(nf_conntrack_broadcast {
        ct,
        ctinfo,
        ctproto,
        ctzone,
        ctmark,
        ctmask,
        ctmark_mask: 0,
        ctmark_set: 0,
        ctmark_clear: 0,
        ctmark_xor: 0,
        ctmark_or: 0,
        ctmark_and: 0,
        ctmark_set_mask: 0,
        ctmark_clear_mask: 0,
        ctmark_xor_mask: 0,
        ctmark_or_mask: 0,
        ctmark_and_mask: 0,
        ctmark_set_xor: 0,
        ctmark_clear_xor: 0,
        ctmark_xor_xor: 0,
        ctmark_or_xor: 0,
        ctmark_and_xor: 0,
        ctmark_set_or: 0,
        ctmark_clear_or: 0,
        ctmark_xor_or: 0,
        ctmark_or_or: 0,
        ctmark_and_or: 0,
        ctmark_set_and: 0,
        ctmark_clear_and: 0,
        ctmark_xor_and: 0,
        ctmark_or_and: 0,
        ctmark_and_and: 0,
    });

    Box::into_raw(nfct_broadcast)
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_broadcast_destroy(nfct_broadcast: *mut nf_conntrack_broadcast) {
    if !nfct_broadcast.is_null() {
        let _ = Box::from_raw(nfct_broadcast);
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_broadcast_set_mark(
    nfct_broadcast: *mut nf_conntrack_broadcast,
    ctmark: u32,
    ctmask: u32,
) {
    if nfct_broadcast.is_null() {
        return;
    }

    (*nfct_broadcast).ctmark = ctmark;
    (*nfct_broadcast).ctmask = ctmask;
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_broadcast_get_mark(
    nfct_broadcast: *const nf_conntrack_broadcast,
    ctmark: *mut u32,
    ctmask: *mut u32,
) {
    if nfct_broadcast.is_null() || ctmark.is_null() || ctmask.is_null() {
        return;
    }

    *ctmark = (*nfct_broadcast).ctmark;
    *ctmask = (*nfct_broadcast).ctmask;
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_broadcast_set_zone(
    nfct_broadcast: *mut nf_conntrack_broadcast,
    ctzone: u16,
) {
    if nfct_broadcast.is_null() {
        return;
    }

    (*nfct_broadcast).ctzone = ctzone;
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_broadcast_get_zone(
    nfct_broadcast: *const nf_conntrack_broadcast,
    ctzone: *mut u16,
) {
    if nfct_broadcast.is_null() || ctzone.is_null() {
        return;
    }

    *ctzone = (*nfct_broadcast).ctzone;
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_broadcast_set_proto(
    nfct_broadcast: *mut nf_conntrack_broadcast,
    ctproto: u8,
) {
    if nfct_broadcast.is_null() {
        return;
    }

    (*nfct_broadcast).ctproto = ctproto;
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_broadcast_get_proto(
    nfct_broadcast: *const nf_conntrack_broadcast,
    ctproto: *mut u8,
) {
    if nfct_broadcast.is_null() || ctproto.is_null() {
        return;
    }

    *ctproto = (*nfct_broadcast).ctproto;
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_broadcast_set_info(
    nfct_broadcast: *mut nf_conntrack_broadcast,
    ctinfo: u8,
) {
    if nfct_broadcast.is_null() {
        return;
    }

    (*nfct_broadcast).ctinfo = ctinfo;
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_broadcast_get_info(
    nfct_broadcast: *const nf_conntrack_broadcast,
    ctinfo: *mut u8,
) {
    if nfct_broadcast.is_null() || ctinfo.is_null() {
        return;
    }

    *ctinfo = (*nfct_broadcast).ctinfo;
}

#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
