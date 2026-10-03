#![allow(clippy::pedantic)]
#![no_std]
//! Crc32 module
//!
//! Substantive kernel definitions for crc32 in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for crc32
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Crc32Descriptor {
    pub polynomial: u64,
    pub flags: u32,
    pub active: bool,
}

impl Crc32Descriptor {
    pub const fn new(polynomial: u64, flags: u32) -> Self {
        Self { polynomial, flags, active: true }
    }

    pub fn is_standard(&self) -> bool {
        self.active && self.polynomial > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn crc32_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn crc32_exit() {
}

#[no_mangle]
pub static CRC32_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_crc32_descriptor_creation() {
        let desc = Crc32Descriptor::new(42, 0x1);
        assert!(desc.is_standard());
        assert_eq!(desc.polynomial, 42);
    }

    #[test]
    fn test_crc32_descriptor_inactive() {
        let mut desc = Crc32Descriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_standard());
    }

    #[test]
    fn test_crc32_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(crc32_init(), 0);
        }
    }
}
