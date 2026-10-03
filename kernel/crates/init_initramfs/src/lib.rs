#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Initial RAM filesystem
//!
//! This module implements init_initramfs functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel init

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn init_initramfs_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn init_initramfs_exit() {
}

#[no_mangle]
pub static INIT_INITRAMFS_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_init_initramfs_init_stub() {
        unsafe { assert_eq!(init_initramfs_init(), -38); }
    }
}
