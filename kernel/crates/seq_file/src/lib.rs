#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Sequential file
//!
//! This module implements seq_file functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel fs

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn seq_file_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn seq_file_exit() {
}

#[no_mangle]
pub static SEQ_FILE_INITIALIZED: bool = false;
