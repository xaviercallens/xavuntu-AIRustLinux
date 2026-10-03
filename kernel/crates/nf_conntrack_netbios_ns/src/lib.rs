#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! NetBIOS name service broadcast connection tracking helper
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(unused_variables)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::ffi::c_void;
use core::ptr;

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

use kernel_types::*;

const NMBD_PORT: u16 = 137; const IPPROTO_UDP: u8 = 17; const NFPROTO_IPV4: u8 = 2;
const HELPER_NAME: &[u8] = b"netbios-ns\0";

#[repr(C)]
#[derive(Copy, Clone)]
struct nfct_tuple_src_udp { port: u16 }

#[repr(C)]
union nfct_tuple_src_u {
    udp: nfct_tuple_src_udp,
}

#[repr(C)]
struct nfct_tuple_src {
    u3: [u32; 4],
    u: nfct_tuple_src_u,
    l3num: u16,
}

#[repr(C)]
struct nfct_tuple_dst {
    u3: [u32; 4],
    protonum: u8,
    dir: u8,
}

#[repr(C)]
struct nfct_tuple { src: nfct_tuple_src, dst: nfct_tuple_dst }

#[repr(C)]
struct nf_conntrack_expect_policy { max_expected: u32, timeout: u32 }

#[repr(C)]
struct nf_conntrack_helper {
    name: *const c_char,
    tuple: nfct_tuple,
    expect_policy: *mut nf_conntrack_expect_policy,
    me: *mut c_void,
    help: extern "C" fn(*mut c_void, u32, *mut c_void, u32) -> c_int,
}

// Module parameters
static TIMEOUT: SyncWrapper<u32> = SyncWrapper::new(3);

// Expect policy
static EXP_POLICY: SyncWrapper<nf_conntrack_expect_policy> = SyncWrapper::new(nf_conntrack_expect_policy {
    max_expected: 1,
    timeout: 3,
});

// Function implementations
#[no_mangle]
extern "C" fn netbios_ns_help(skb: *mut c_void, protoff: u32, ct: *mut c_void, ctinfo: u32) -> i32 {
    unsafe { nf_conntrack_broadcast_help(skb, ct, ctinfo, *TIMEOUT.get_mut()) }
}

static HELPER: SyncWrapper<nf_conntrack_helper> = SyncWrapper::new(nf_conntrack_helper {
    name: HELPER_NAME.as_ptr() as *const c_char,
    tuple: nfct_tuple {
        src: nfct_tuple_src {
            u3: [0; 4],
            u: nfct_tuple_src_u {
                udp: nfct_tuple_src_udp {
                    port: NMBD_PORT.to_be(),
                },
            },
            l3num: NFPROTO_IPV4 as u16,
        },
        dst: nfct_tuple_dst {
            u3: [0; 4],
            protonum: IPPROTO_UDP,
            dir: 0,
        },
    },
    expect_policy: ptr::null_mut(),
    me: ptr::null_mut(),
    help: netbios_ns_help,
});

unsafe extern "C" {
    fn nf_conntrack_helper_register(helper: *mut nf_conntrack_helper) -> c_int;
    fn nf_conntrack_helper_unregister(helper: *mut nf_conntrack_helper);
    fn nf_conntrack_broadcast_help(
        skb: *mut c_void,
        ct: *mut c_void,
        ctinfo: u32,
        timeout: u32,
    ) -> c_int;
}

#[unsafe(no_mangle)]
pub extern "C" fn nf_conntrack_netbios_ns_init() -> c_int {
    unsafe {
        // SAFETY: EXP_POLICY is valid and properly initialized
        (*EXP_POLICY.get_mut()).timeout = *TIMEOUT.get_mut();

        // Register the helper
        nf_conntrack_helper_register(HELPER.get_mut())
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn nf_conntrack_netbios_ns_fini() {
    unsafe {
        nf_conntrack_helper_unregister(HELPER.get_mut());
    }
}

// Implementation deferred.
#[no_mangle]
pub static module_param_timeout: SyncWrapper<u32> = SyncWrapper::new(3);
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
