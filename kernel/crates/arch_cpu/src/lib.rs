#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! CPU initialization
//!
//! This module implements arch_cpu functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel arch/x86/kernel

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn arch_cpu_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn arch_cpu_exit() {
}

#[no_mangle]
pub static ARCH_CPU_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_arch_cpu_init_stub() {
        unsafe { assert_eq!(arch_cpu_init(), -38); }
    }
}
