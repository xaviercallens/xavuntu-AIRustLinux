#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Key management
//!
//! This module implements security_keys functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel security/keys

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn security_keys_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn security_keys_exit() {
}

#[no_mangle]
pub static SECURITY_KEYS_INITIALIZED: bool = false;
