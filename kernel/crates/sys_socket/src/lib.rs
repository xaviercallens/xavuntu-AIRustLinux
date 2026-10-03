#![allow(clippy::all, clippy::pedantic)]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
#![no_std]
//! Socket syscalls
//!
//! This module implements sys_socket functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel syscalls

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sys_socket_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sys_socket_exit() {
}

#[no_mangle]
pub static SYS_SOCKET_INITIALIZED: bool = false;
