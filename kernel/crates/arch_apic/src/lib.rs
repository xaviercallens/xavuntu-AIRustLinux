#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! APIC management
//!
//! This module implements arch_apic functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel arch/x86/kernel

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn arch_apic_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn arch_apic_exit() {
}

#[no_mangle]
pub static ARCH_APIC_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_arch_apic_init_stub() {
        unsafe { assert_eq!(arch_apic_init(), -38); }
    }
}
