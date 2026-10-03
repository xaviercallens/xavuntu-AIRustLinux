#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Reverse mapping
//!
//! This module implements rmap functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel mm/rmap.c

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn rmap_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn rmap_exit() {
}

// Implementation deferred.
#[no_mangle]
pub static RMAP_INITIALIZED: bool = false;
