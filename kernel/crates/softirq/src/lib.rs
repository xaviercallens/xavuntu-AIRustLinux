#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Soft IRQs
//!
//! This module implements softirq functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel kernel

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn softirq_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn softirq_exit() {
}

#[no_mangle]
pub static SOFTIRQ_INITIALIZED: bool = false;
