#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Decompression
//!
//! This module implements arch_boot_compressed functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel arch/x86/boot

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn arch_boot_compressed_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn arch_boot_compressed_exit() {
}

#[no_mangle]
pub static ARCH_BOOT_COMPRESSED_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_arch_boot_compressed_init_stub() {
        unsafe { assert_eq!(arch_boot_compressed_init(), -38); }
    }
}
