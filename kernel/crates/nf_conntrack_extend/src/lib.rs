#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
#[cfg(not(target_arch = "x86_64"))]
extern crate alloc;
#[cfg(not(target_arch = "x86_64"))]
use alloc::boxed::Box;
use kernel_types::*;
use core::ffi::c_void;

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
pub struct nf_nat_ipv4 {
    pub min_addr: __be32,
    pub max_addr: __be32,
    pub min_proto: __be16,
    pub max_proto: __be16,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_nat_ipv6 {
    pub min_addr: in6_addr,
    pub max_addr: in6_addr,
    pub min_proto: __be16,
    pub max_proto: __be16,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_nat_extend { pub nat_ipv4: nf_nat_ipv4, pub nat_ipv6: nf_nat_ipv6 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_extend {
    pub ct: *mut c_void,
    pub timeout: u32,
    pub flags: u32,
    pub helper: *mut c_void,
    pub master: *mut c_void,
    pub tstamp: u64,
    pub status: u32,
    pub nat: nf_nat_extend,
    pub timeout_data: [u32; 4],
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_extend_init(ct: *mut c_void) -> *mut nf_conntrack_extend {
    Box::into_raw(Box::new(nf_conntrack_extend {
        ct,
        timeout: 0,
        flags: 0,
        helper: core::ptr::null_mut(),
        master: core::ptr::null_mut(),
        tstamp: 0,
        status: 0,
        nat: nf_nat_extend {
            nat_ipv4: nf_nat_ipv4 {
                min_addr: 0,
                max_addr: 0,
                min_proto: 0,
                max_proto: 0,
            },
            nat_ipv6: nf_nat_ipv6 {
                min_addr: in6_addr {
                    in6_u: in6_addr_union { u6_addr32: [0; 4] },
                },
                max_addr: in6_addr {
                    in6_u: in6_addr_union { u6_addr32: [0; 4] },
                },
                min_proto: 0,
                max_proto: 0,
            },
        },
        timeout_data: [0; 4],
    }))
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_extend_destroy(extend: *mut nf_conntrack_extend) {
    if !extend.is_null() {
        let _ = Box::from_raw(extend);
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_extend_set_timeout(
    extend: *mut nf_conntrack_extend,
    timeout: u32,
) {
    if !extend.is_null() {
        (*extend).timeout = timeout;
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_extend_set_flags(extend: *mut nf_conntrack_extend, flags: u32) {
    if !extend.is_null() {
        (*extend).flags = flags;
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_extend_set_helper(
    extend: *mut nf_conntrack_extend,
    helper: *mut c_void,
) {
    if !extend.is_null() {
        (*extend).helper = helper;
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_extend_set_master(
    extend: *mut nf_conntrack_extend,
    master: *mut c_void,
) {
    if !extend.is_null() {
        (*extend).master = master;
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_extend_set_tstamp(
    extend: *mut nf_conntrack_extend,
    tstamp: u64,
) {
    if !extend.is_null() {
        (*extend).tstamp = tstamp;
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_extend_set_status(
    extend: *mut nf_conntrack_extend,
    status: u32,
) {
    if !extend.is_null() {
        (*extend).status = status;
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_extend_set_nat_ipv4(
    extend: *mut nf_conntrack_extend,
    min_addr: __be32,
    max_addr: __be32,
    min_proto: __be16,
    max_proto: __be16,
) {
    if !extend.is_null() {
        (*extend).nat.nat_ipv4.min_addr = min_addr;
        (*extend).nat.nat_ipv4.max_addr = max_addr;
        (*extend).nat.nat_ipv4.min_proto = min_proto;
        (*extend).nat.nat_ipv4.max_proto = max_proto;
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_extend_set_nat_ipv6(
    extend: *mut nf_conntrack_extend,
    min_addr: in6_addr,
    max_addr: in6_addr,
    min_proto: __be16,
    max_proto: __be16,
) {
    if !extend.is_null() {
        (*extend).nat.nat_ipv6.min_addr = min_addr;
        (*extend).nat.nat_ipv6.max_addr = max_addr;
        (*extend).nat.nat_ipv6.min_proto = min_proto;
        (*extend).nat.nat_ipv6.max_proto = max_proto;
    }
}

#[allow(improper_ctypes_definitions)]
#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_extend_set_timeout_data(
    extend: *mut nf_conntrack_extend,
    data: [u32; 4],
) {
    if !extend.is_null() {
        (*extend).timeout_data = data;
    }
}

#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
