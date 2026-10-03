#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! read syscall
//!
//! This module implements sys_read functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel syscalls

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sys_read_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sys_read_exit() {
}

#[no_mangle]
pub static SYS_READ_INITIALIZED: bool = false;
