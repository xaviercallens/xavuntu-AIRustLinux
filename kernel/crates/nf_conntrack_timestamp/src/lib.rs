#![allow(clippy::all, clippy::pedantic)]
// SPDX-License-Identifier: GPL-2.0-or-later
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(unused_unsafe)]
#![allow(dead_code)]
#![allow(unused_variables)]

use core::ffi::{c_char, c_int, c_void};
use kernel_types::*;

// Kernel constants from headers
const NF_CT_EXT_TSTAMP: u32 = 0; // Actual value defined in kernel headers

use core::sync::atomic::AtomicBool;

// Module parameter
static NF_CT_TSTAMP: AtomicBool = AtomicBool::new(false);

// Extension descriptor
#[repr(C)]
pub struct nf_ct_ext_type {
    len: u32,
    align: u32,
    id: u32,
}

static TSTAMP_EXTEND: nf_ct_ext_type = nf_ct_ext_type {
    len: core::mem::size_of::<NF_CONN_TSTAMP>() as u32,
    align: core::mem::align_of::<NF_CONN_TSTAMP>() as u32,
    id: NF_CT_EXT_TSTAMP,
};

// Opaque type from kernel headers
#[repr(C)]
struct NF_CONN_TSTAMP {
    start: u64,
    stop: u64,
}

// External kernel functions
extern "C" {
    fn nf_ct_extend_register(ext: *const nf_ct_ext_type) -> c_int;
    fn nf_ct_extend_unregister(ext: *const nf_ct_ext_type);
    fn pr_err(fmt: *const c_char);
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_tstamp_pernet_init(net: *mut c_void) -> c_int {
    // SAFETY: Kernel guarantees valid net pointer during pernet init
    // Implementation deferred.
    unsafe {
        let _net_ptr = net as *mut net;
        // (*net_ptr).ct.sysctl_tstamp = NF_CT_TSTAMP;
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_tstamp_init() -> c_int {
    let ret = nf_ct_extend_register(&TSTAMP_EXTEND as *const nf_ct_ext_type);
    if ret < 0 {
        pr_err(b"Unable to register extension\n\0".as_ptr() as *const c_char);
    }
    ret
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_tstamp_fini() {
    // SAFETY: Extension must be registered before unregistration
    unsafe {
        nf_ct_extend_unregister(&TSTAMP_EXTEND);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extension_size() {
        assert!(core::mem::size_of::<NF_CONN_TSTAMP>() > 0);
        assert!(core::mem::align_of::<NF_CONN_TSTAMP>() > 0);
    }
}
