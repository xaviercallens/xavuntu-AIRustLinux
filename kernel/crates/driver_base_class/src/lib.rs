#![allow(clippy::all, clippy::pedantic)]
#![no_std]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
//! Device classes
//!
//! This module implements driver_base_class functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel drivers/base

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn driver_base_class_init() -> c_int {
    // Implementation deferred.
    -19 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn driver_base_class_exit() {
}

#[no_mangle]
pub static DRIVER_BASE_CLASS_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_driver_base_class_init_stub() {
        unsafe { assert_eq!(driver_base_class_init(), -19); }
    }
}
