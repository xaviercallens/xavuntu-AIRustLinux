#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Signal arch code
//!
//! This module implements arch_signal functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel arch/x86/kernel

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn arch_signal_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn arch_signal_exit() {
}

#[no_mangle]
pub static ARCH_SIGNAL_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_arch_signal_init_stub() {
        unsafe { assert_eq!(arch_signal_init(), -38); }
    }
}
