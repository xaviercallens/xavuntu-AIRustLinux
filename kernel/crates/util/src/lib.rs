#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Memory management utilities
//!
//! This module implements util functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel mm/util.c

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn util_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn util_exit() {
}

// Implementation deferred.
#[no_mangle]
pub static UTIL_INITIALIZED: bool = false;
