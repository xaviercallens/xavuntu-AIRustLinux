#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

use core::{ffi::{c_int, c_uint, c_void}, ptr};

// Constants from C
pub const AF_INET: c_int = 2; pub const EINVAL: c_int = -22;

// Type definitions
#[repr(C)]
pub struct NotifierBlock { _private: [u8; 0] }

#[repr(C)]
pub struct FIBNotifierInfo { family: c_int }

#[repr(C)]
pub struct Net { ipv4: *mut NetIPv4 }

#[repr(C)]
pub struct NetIPv4 { fib_seq: c_uint, notifier_ops: *mut FIBNotifierOps }

#[repr(C)]
pub struct FIBNotifierOps {
    family: c_int,
    fib_seq_read: Option<unsafe extern "C" fn(net: *mut Net) -> c_uint>,
    fib_dump: Option<
        unsafe extern "C" fn(net: *mut Net, nb: *mut NotifierBlock, extack: *mut c_void) -> c_int,
    >,
    owner: *mut c_void,
}

unsafe impl Sync for FIBNotifierOps {}

#[repr(C)]
pub struct NetlinkExtAck { _private: [u8; 0] }

// External function declarations
unsafe extern "C" {
    fn call_fib_notifier(
        nb: *mut NotifierBlock,
        event_type: c_int,
        info: *mut FIBNotifierInfo,
    ) -> c_int;
    fn call_fib_notifiers(net: *mut Net, event_type: c_int, info: *mut FIBNotifierInfo) -> c_int;
    fn fib4_rules_seq_read(net: *mut Net) -> c_uint;
    fn fib4_rules_dump(net: *mut Net, nb: *mut NotifierBlock, extack: *mut c_void) -> c_int;
    fn fib_notify(net: *mut Net, nb: *mut NotifierBlock, extack: *mut c_void) -> c_int;
    fn fib_notifier_ops_register(ops: *const FIBNotifierOps, net: *mut Net) -> *mut FIBNotifierOps;
    fn fib_notifier_ops_unregister(ops: *mut FIBNotifierOps);
}

// Static data
static FIB4_NOTIFIER_OPS_TEMPLATE: FIBNotifierOps = FIBNotifierOps {
    family: AF_INET,
    fib_seq_read: Some(fib4_seq_read),
    fib_dump: Some(fib4_dump),
    owner: ptr::null_mut(),
};

// Function implementations
#[no_mangle]
pub unsafe extern "C" fn call_fib4_notifier(
    nb: *mut NotifierBlock,
    event_type: c_int,
    info: *mut FIBNotifierInfo,
) -> c_int {
    if info.is_null() {
        return EINVAL;
    }

    (*info).family = AF_INET;
    call_fib_notifier(nb, event_type, info)
}

#[no_mangle]
pub unsafe extern "C" fn call_fib4_notifiers(
    net: *mut Net,
    event_type: c_int,
    info: *mut FIBNotifierInfo,
) -> c_int {
    if net.is_null() || info.is_null() {
        return EINVAL;
    }

    let ipv4 = (*net).ipv4;
    if ipv4.is_null() {
        return EINVAL;
    }

    (*info).family = AF_INET;
    (*ipv4).fib_seq = (*ipv4).fib_seq.wrapping_add(1);
    call_fib_notifiers(net, event_type, info)
}

#[no_mangle]
pub unsafe extern "C" fn fib4_seq_read(net: *mut Net) -> c_uint {
    if net.is_null() {
        return 0;
    }

    let ipv4 = (*net).ipv4;
    if ipv4.is_null() {
        return 0;
    }

    (*ipv4).fib_seq.wrapping_add(fib4_rules_seq_read(net))
}

#[no_mangle]
pub unsafe extern "C" fn fib4_dump(
    net: *mut Net,
    nb: *mut NotifierBlock,
    extack: *mut c_void,
) -> c_int {
    if net.is_null() || nb.is_null() {
        return EINVAL;
    }

    let err = fib4_rules_dump(net, nb, extack);
    if err != 0 {
        return err;
    }
    fib_notify(net, nb, extack)
}

#[no_mangle]
pub unsafe extern "C" fn fib4_notifier_init(net: *mut Net) -> c_int {
    if net.is_null() {
        return EINVAL;
    }

    let ipv4 = (*net).ipv4;
    if ipv4.is_null() {
        return EINVAL;
    }

    (*ipv4).fib_seq = 0;

    let ops = fib_notifier_ops_register(&FIB4_NOTIFIER_OPS_TEMPLATE as *const FIBNotifierOps, net);
    if ops.is_null() {
        return EINVAL;
    }

    (*ipv4).notifier_ops = ops;
    0
}

#[no_mangle]
pub unsafe extern "C" fn fib4_notifier_exit(net: *mut Net) {
    if net.is_null() {
        return;
    }

    let ipv4 = (*net).ipv4;
    if ipv4.is_null() {
        return;
    }

    let ops = (*ipv4).notifier_ops;
    if !ops.is_null() {
        fib_notifier_ops_unregister(ops);
        (*ipv4).notifier_ops = ptr::null_mut();
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
