#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Capability handling
//!
//! This module implements security_commoncap functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel security

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn security_commoncap_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn security_commoncap_exit() {
}

#[no_mangle]
pub static SECURITY_COMMONCAP_INITIALIZED: bool = false;
