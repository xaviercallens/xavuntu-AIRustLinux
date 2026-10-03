#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Boot header
//!
//! This module implements arch_boot_header functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel arch/x86/boot

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn arch_boot_header_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn arch_boot_header_exit() {
}

#[no_mangle]
pub static ARCH_BOOT_HEADER_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_arch_boot_header_init_stub() {
        unsafe { assert_eq!(arch_boot_header_init(), -38); }
    }
}
