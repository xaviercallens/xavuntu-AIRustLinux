#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! munmap syscall
//!
//! This module implements sys_munmap functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel syscalls

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sys_munmap_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sys_munmap_exit() {
}

#[no_mangle]
pub static SYS_MUNMAP_INITIALIZED: bool = false;
