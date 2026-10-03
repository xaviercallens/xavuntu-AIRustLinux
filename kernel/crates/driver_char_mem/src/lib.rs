#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! /dev/mem, /dev/null
//!
//! This module implements driver_char_mem functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel drivers/char

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn driver_char_mem_init() -> c_int {
    // Implementation deferred.
    -19 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn driver_char_mem_exit() {
}

#[no_mangle]
pub static DRIVER_CHAR_MEM_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_driver_char_mem_init_stub() {
        unsafe { assert_eq!(driver_char_mem_init(), -19); }
    }
}
