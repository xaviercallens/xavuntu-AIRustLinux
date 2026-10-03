#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! I/O memory mapping
//!
//! This module implements arch_ioremap functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel arch/x86/mm

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn arch_ioremap_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn arch_ioremap_exit() {
}

#[no_mangle]
pub static ARCH_IOREMAP_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_arch_ioremap_init_stub() {
        unsafe { assert_eq!(arch_ioremap_init(), -38); }
    }
}
