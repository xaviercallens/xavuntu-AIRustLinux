#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! /sys filesystem
//!
//! This module implements sysfs_dir functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel fs/sysfs

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sysfs_dir_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sysfs_dir_exit() {
}

#[no_mangle]
pub static SYSFS_DIR_INITIALIZED: bool = false;
