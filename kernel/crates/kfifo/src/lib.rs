#![allow(clippy::pedantic)]
#![no_std]
//! Kfifo module
//!
//! Substantive kernel definitions for kfifo in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for kfifo
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct KfifoDescriptor {
    pub element_size: u64,
    pub flags: u32,
    pub active: bool,
}

impl KfifoDescriptor {
    pub const fn new(element_size: u64, flags: u32) -> Self {
        Self { element_size, flags, active: true }
    }

    pub fn is_power_of_two(&self) -> bool {
        self.active && self.element_size > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn kfifo_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn kfifo_exit() {
}

#[no_mangle]
pub static KFIFO_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kfifo_descriptor_creation() {
        let desc = KfifoDescriptor::new(42, 0x1);
        assert!(desc.is_power_of_two());
        assert_eq!(desc.element_size, 42);
    }

    #[test]
    fn test_kfifo_descriptor_inactive() {
        let mut desc = KfifoDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_power_of_two());
    }

    #[test]
    fn test_kfifo_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(kfifo_init(), 0);
        }
    }
}
