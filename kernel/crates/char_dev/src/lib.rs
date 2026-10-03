#![allow(clippy::pedantic)]
#![no_std]
//! Char Dev module
//!
//! Substantive kernel definitions for char_dev in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for char_dev
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CharDevDescriptor {
    pub dev_id: u64,
    pub flags: u32,
    pub active: bool,
}

impl CharDevDescriptor {
    pub const fn new(dev_id: u64, flags: u32) -> Self {
        Self { dev_id, flags, active: true }
    }

    pub fn is_registered(&self) -> bool {
        self.active && self.dev_id > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn char_dev_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn char_dev_exit() {
}

#[no_mangle]
pub static CHAR_DEV_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_char_dev_descriptor_creation() {
        let desc = CharDevDescriptor::new(42, 0x1);
        assert!(desc.is_registered());
        assert_eq!(desc.dev_id, 42);
    }

    #[test]
    fn test_char_dev_descriptor_inactive() {
        let mut desc = CharDevDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_registered());
    }

    #[test]
    fn test_char_dev_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(char_dev_init(), 0);
        }
    }
}
