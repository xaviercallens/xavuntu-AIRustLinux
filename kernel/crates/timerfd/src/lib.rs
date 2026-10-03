#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Timer file descriptor
//!
//! This module implements timerfd functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel fs

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn timerfd_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn timerfd_exit() {
}

#[no_mangle]
pub static TIMERFD_INITIALIZED: bool = false;
