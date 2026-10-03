#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! open syscall
//!
//! This module implements sys_open functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel syscalls

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sys_open_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sys_open_exit() {
}

#[no_mangle]
pub static SYS_OPEN_INITIALIZED: bool = false;
