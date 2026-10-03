#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Keyring support
//!
//! This module implements security_keyring functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel security/keys

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn security_keyring_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn security_keyring_exit() {
}

#[no_mangle]
pub static SECURITY_KEYRING_INITIALIZED: bool = false;
