#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Signal file descriptor
//!
//! This module implements signalfd functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel fs

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn signalfd_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn signalfd_exit() {
}

#[no_mangle]
pub static SIGNALFD_INITIALIZED: bool = false;
