#![allow(clippy::all, clippy::pedantic)]
#![no_std]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]
//! String operations
//!
//! This module implements string functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel lib

extern crate alloc;
use alloc::boxed::Box;
use alloc::vec::Vec;
use alloc::string::String;

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn string_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn string_exit() {
}

#[no_mangle]
pub static STRING_INITIALIZED: bool = false;
