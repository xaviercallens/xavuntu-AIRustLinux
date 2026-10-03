#![allow(clippy::all, clippy::pedantic)]
#![no_std]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs)]
//! CPU sets
//!
//! This module implements cpuset functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel kernel/cpuset.c

use core::ffi::{c_int, c_uint};
type pid_t = i32;

// Implementation deferred.
#[repr(C)]
pub struct task_struct {
    pub pid: pid_t,
    pub state: c_int,
    pub flags: c_uint,
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn cpuset_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn cpuset_exit() {
}

#[no_mangle]
pub static CPUSET_INITIALIZED: bool = false;
