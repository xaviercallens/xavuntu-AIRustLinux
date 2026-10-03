#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Entry point assembly
//!
//! This module implements arch_entry functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel arch/x86/entry

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn arch_entry_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn arch_entry_exit() {
}

#[no_mangle]
pub static ARCH_ENTRY_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_arch_entry_init_stub() {
        unsafe { assert_eq!(arch_entry_init(), -38); }
    }
}
