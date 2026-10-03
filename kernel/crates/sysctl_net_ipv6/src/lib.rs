#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::ffi::c_void;
use kernel_types::*;

/// C-compatible alias used at FFI boundaries.
pub type socklen_t = u32;
pub type c_size_t = usize;

#[repr(C)]
pub struct ctl_table {
    pub procname: *const c_char,
    pub data: *mut c_void,
    pub maxlen: c_int,
    pub mode: c_ushort,
    pub child: *mut ctl_table,
    pub proc_handler: Option<
        unsafe extern "C" fn(
            table: *mut ctl_table,
            write: c_int,
            buffer: *mut c_void,
            lenp: *mut c_size_t,
            ppos: *mut i64,
        ) -> c_int,
    >,
    pub extra1: *mut c_void,
    pub extra2: *mut c_void,
}

#[repr(C)]
pub struct ctl_table_header { _private: [u8; 0] }

unsafe extern "C" {
    pub fn register_net_sysctl_sz(
        net: *mut c_void,
        path: *const c_char,
        table: *mut ctl_table,
        table_size: c_size_t,
    ) -> *mut ctl_table_header;

    pub fn unregister_net_sysctl_table(header: *mut ctl_table_header);
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn sysctl_net_ipv6_register(
    net: *mut c_void,
    path: *const c_char,
    table: *mut ctl_table,
    table_size: c_size_t,
) -> *mut ctl_table_header {
    register_net_sysctl_sz(net, path, table, table_size)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn sysctl_net_ipv6_unregister(header: *mut ctl_table_header) {
    if !header.is_null() {
        unregister_net_sysctl_table(header);
    }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {
        core::hint::spin_loop();
    }
}
