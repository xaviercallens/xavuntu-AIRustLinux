#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Signal syscalls
//!
//! This module implements sys_signal functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel syscalls

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sys_signal_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sys_signal_exit() {
}

#[no_mangle]
pub static SYS_SIGNAL_INITIALIZED: bool = false;
