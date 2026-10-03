#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! /sys file operations
//!
//! This module implements sysfs_file functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel fs/sysfs

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sysfs_file_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sysfs_file_exit() {
}

#[no_mangle]
pub static SYSFS_FILE_INITIALIZED: bool = false;
