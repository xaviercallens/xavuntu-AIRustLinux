#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

extern crate alloc;

use alloc::boxed::Box;
use core::{ptr, alloc::{GlobalAlloc, Layout}, ffi::{c_int, c_void}, panic::PanicInfo, sync::atomic::AtomicI32};
use kernel_types::*;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENETUNREACH: c_int = -101;
pub const EACCES: c_int = -13;
pub const ENOSYS: c_int = -38;

struct KernelAlloc;

// SAFETY: This allocator forwards to external C allocator functions.
unsafe impl GlobalAlloc for KernelAlloc {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        unsafe extern "C" {
            fn malloc(size: size_t) -> *mut c_void;
        }
        unsafe { malloc(layout.size() as size_t) as *mut u8 }
    }

    unsafe fn dealloc(&self, ptr: *mut u8, _layout: Layout) {
        unsafe extern "C" {
            fn free(ptr: *mut c_void);
        }
        unsafe { free(ptr as *mut c_void) }
    }
}

#[global_allocator]
static GLOBAL_ALLOCATOR: KernelAlloc = KernelAlloc;

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}

#[repr(C)]
pub struct net_device { pub flags: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct list_head { next: *mut list_head, prev: *mut list_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct uncached_list { lock: *mut c_void, head: list_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct dst_ops {
    family: c_int,
    gc: Option<extern "C" fn(*mut c_void) -> c_int>,
    gc_thresh: c_int,
    check: Option<extern "C" fn(*mut c_void, u32) -> *mut c_void>,
    default_advmss: Option<extern "C" fn(*const c_void) -> c_int>,
    mtu: Option<extern "C" fn(*const c_void) -> c_int>,
    destroy: Option<extern "C" fn(*mut c_void)>,
    ifdown: Option<extern "C" fn(*mut c_void, *mut net_device, c_int)>,
    negative_advice: Option<extern "C" fn(*mut c_void) -> *mut c_void>,
    link_failure: Option<extern "C" fn(*mut c_void)>,
    update_pmtu: Option<extern "C" fn(*mut c_void, *mut c_void, *mut c_void, u32, c_int)>,
    redirect: Option<extern "C" fn(*mut c_void, *mut c_void, *mut c_void)>,
    local_out: Option<extern "C" fn(*mut c_void) -> *mut c_void>,
    neigh_lookup:
        Option<extern "C" fn(*mut c_void, *mut c_void, *mut c_void, *const c_void) -> *mut c_void>,
    confirm_neigh: Option<extern "C" fn(*mut c_void, *const c_void)>,
}

#[repr(C)]
pub struct fib6_info {
    fib6_flags: c_int,
    fib6_protocol: c_int,
    fib6_metric: u32,
    fib6_ref: AtomicI32,
    fib6_type: c_int,
    fib6_metrics: *mut c_void,
}

#[repr(C)]
pub struct inet6_dev { dev: *mut net_device }

#[repr(C)]
struct per_cpu_data { list: uncached_list }

// Function implementations
#[unsafe(no_mangle)]
pub unsafe extern "C" fn ip6_dst_alloc(
    _net: *mut c_void,
    dev: *mut net_device,
    _flags: c_int,
) -> *mut rt6_info {
    let rt = Box::into_raw(Box::new(rt6_info {
        dst: dst_entry {
            dev: dev as *mut c_void,
            ops: ptr::null_mut(),
            rcuhead: ptr::null_mut(),
            metrics: [0; 17],
            mtu: 0,
            flags: 0,
            obsolete: 1,
            header_len: 0,
            trailer_len: 0,
            error: ptr::null_mut(),
            xfrm: ptr::null_mut(),
        },
        rt6_next: ptr::null_mut(),
        rt6i_idev: ptr::null_mut(),
        rt6i_flags: 0,
        rt6i_uncached: ListHead {
            next: ptr::null_mut(),
            prev: ptr::null_mut(),
        },
        rt6i_src: ptr::null_mut(),
        rt6i_gateway: ptr::null_mut(),
        rt6i_dst: ptr::null_mut(),
    }));

    // Initialize uncached list - ListHead is kernel_types::ListHead
    // Initialized inline in struct
    rt
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ip6_dst_check(dst: *mut dst_entry, _cookie: u32) -> *mut dst_entry {
    if dst.is_null() {
        ptr::null_mut()
    } else {
        dst
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ip6_default_advmss(_dst: *const dst_entry) -> c_int {
    1232
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ip6_mtu(_dst: *const dst_entry) -> c_int {
    1500
}

#[unsafe(no_mangle)]
pub extern "C" fn ip6_pkt_discard(skb: *mut c_void) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }
    -ENETUNREACH
}

#[unsafe(no_mangle)]
pub extern "C" fn ip6_pkt_discard_out(
    _net: *mut c_void,
    _sk: *mut c_void,
    skb: *mut c_void,
) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }
    -ENETUNREACH
}

#[unsafe(no_mangle)]
pub extern "C" fn ip6_pkt_prohibit(skb: *mut c_void) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }
    -EACCES
}

#[unsafe(no_mangle)]
pub extern "C" fn ip6_pkt_prohibit_out(
    _net: *mut c_void,
    _sk: *mut c_void,
    skb: *mut c_void,
) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }
    -EACCES
}

#[unsafe(no_mangle)]
pub extern "C" fn ip6_link_failure(_skb: *mut c_void) {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ip6_discard_and_prohibit() {
        assert_eq!(ip6_pkt_discard(ptr::null_mut()), EINVAL);
        assert_eq!(ip6_pkt_discard(1 as *mut c_void), -ENETUNREACH);
        assert_eq!(ip6_pkt_discard_out(ptr::null_mut(), ptr::null_mut(), ptr::null_mut()), EINVAL);
        assert_eq!(ip6_pkt_discard_out(ptr::null_mut(), ptr::null_mut(), 1 as *mut c_void), -ENETUNREACH);
        assert_eq!(ip6_pkt_prohibit(ptr::null_mut()), EINVAL);
        assert_eq!(ip6_pkt_prohibit(1 as *mut c_void), -EACCES);
        assert_eq!(ip6_pkt_prohibit_out(ptr::null_mut(), ptr::null_mut(), ptr::null_mut()), EINVAL);
        assert_eq!(ip6_pkt_prohibit_out(ptr::null_mut(), ptr::null_mut(), 1 as *mut c_void), -EACCES);
    }
}
