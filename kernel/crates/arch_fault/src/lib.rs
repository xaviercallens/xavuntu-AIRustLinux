#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Page fault handler
//!
//! This module implements arch_fault functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel arch/x86/mm

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn arch_fault_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn arch_fault_exit() {
}

#[no_mangle]
pub static ARCH_FAULT_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_arch_fault_init_stub() {
        unsafe { assert_eq!(arch_fault_init(), -38); }
    }
}
