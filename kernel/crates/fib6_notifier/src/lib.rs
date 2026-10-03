#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs)]

use core::ffi::{c_int, c_uint, c_void};
use core::ptr;
use kernel_types::*;

pub const AF_INET6: c_int = 10;

#[repr(C)]
struct ipv6_net { notifier_ops: *mut fib_notifier_ops }

#[repr(C)]
struct notifier_block { _private: [u8; 0] }

#[repr(C)]
struct fib_notifier_info { family: c_int }

#[repr(C)]
struct fib_notifier_ops {
    family: c_int,
    fib_seq_read: unsafe extern "C" fn(*mut c_void) -> c_uint,
    fib_dump: unsafe extern "C" fn(*mut c_void, *mut notifier_block, *mut c_void) -> c_int,
    owner: *const c_void,
}

// SAFETY: Immutable static containing only function pointers and opaque pointer.
unsafe impl Sync for fib_notifier_ops {}

unsafe extern "C" {
    fn call_fib_notifier(
        nb: *mut notifier_block,
        event_type: c_int,
        info: *mut fib_notifier_info,
    ) -> c_int;
    fn call_fib_notifiers(
        net: *mut c_void,
        event_type: c_int,
        info: *mut fib_notifier_info,
    ) -> c_int;
    fn fib_notifier_ops_register(
        ops: *const fib_notifier_ops,
        net: *mut c_void,
    ) -> *mut fib_notifier_ops;
    fn fib_notifier_ops_unregister(ops: *mut fib_notifier_ops);
    fn fib6_tables_seq_read(net: *mut c_void) -> c_uint;
    fn fib6_rules_seq_read(net: *mut c_void) -> c_uint;
    fn fib6_rules_dump(net: *mut c_void, nb: *mut notifier_block, extack: *mut c_void) -> c_int;
    fn fib6_tables_dump(net: *mut c_void, nb: *mut notifier_block, extack: *mut c_void) -> c_int;
    fn IS_ERR(ptr: *mut fib_notifier_ops) -> bool;
    fn PTR_ERR(ptr: *mut fib_notifier_ops) -> c_int;
}

#[used]
static FIB6_NOTIFIER_OPS_TEMPLATE: fib_notifier_ops = fib_notifier_ops {
    family: AF_INET6,
    fib_seq_read: fib6_seq_read,
    fib_dump: fib6_dump,
    owner: ptr::null(),
};

#[no_mangle]
pub unsafe extern "C" fn call_fib6_notifier(
    nb: *mut notifier_block,
    event_type: c_int,
    info: *mut fib_notifier_info,
) -> c_int {
    if info.is_null() {
        return EINVAL;
    }
    (*info).family = AF_INET6;
    call_fib_notifier(nb, event_type, info)
}

#[no_mangle]
pub unsafe extern "C" fn call_fib6_notifiers(
    net: *mut c_void,
    event_type: c_int,
    info: *mut fib_notifier_info,
) -> c_int {
    if info.is_null() {
        return EINVAL;
    }
    (*info).family = AF_INET6;
    call_fib_notifiers(net, event_type, info)
}

#[no_mangle]
pub unsafe extern "C" fn fib6_seq_read(net: *mut c_void) -> c_uint {
    fib6_tables_seq_read(net).wrapping_add(fib6_rules_seq_read(net))
}

#[no_mangle]
pub unsafe extern "C" fn fib6_dump(
    net: *mut c_void,
    nb: *mut notifier_block,
    extack: *mut c_void,
) -> c_int {
    let err = fib6_rules_dump(net, nb, extack);
    if err != 0 {
        return err;
    }
    fib6_tables_dump(net, nb, extack)
}

#[no_mangle]
pub unsafe extern "C" fn fib6_notifier_init(net: *mut c_void) -> c_int {
    if net.is_null() {
        return EINVAL;
    }

    let ops = fib_notifier_ops_register(&FIB6_NOTIFIER_OPS_TEMPLATE, net);
    if IS_ERR(ops) {
        return PTR_ERR(ops);
    }

    let ipv6_net_ptr = net as *mut ipv6_net;
    if ipv6_net_ptr.is_null() {
        fib_notifier_ops_unregister(ops);
        return EINVAL;
    }

    (*ipv6_net_ptr).notifier_ops = ops;
    0
}

#[no_mangle]
pub unsafe extern "C" fn fib6_notifier_exit(net: *mut c_void) {
    if net.is_null() {
        return;
    }

    let ipv6_net_ptr = net as *mut ipv6_net;
    if ipv6_net_ptr.is_null() {
        return;
    }

    let ops = (*ipv6_net_ptr).notifier_ops;
    if !ops.is_null() {
        fib_notifier_ops_unregister(ops);
    }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
