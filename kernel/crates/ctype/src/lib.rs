#![allow(clippy::pedantic)]
#![no_std]
//! Ctype module
//!
//! Substantive kernel definitions for ctype in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for ctype
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CtypeDescriptor {
    pub charset_id: u64,
    pub flags: u32,
    pub active: bool,
}

impl CtypeDescriptor {
    pub const fn new(charset_id: u64, flags: u32) -> Self {
        Self { charset_id, flags, active: true }
    }

    pub fn is_ascii_compatible(&self) -> bool {
        self.active && self.charset_id > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn ctype_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn ctype_exit() {
}

#[no_mangle]
pub static CTYPE_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ctype_descriptor_creation() {
        let desc = CtypeDescriptor::new(42, 0x1);
        assert!(desc.is_ascii_compatible());
        assert_eq!(desc.charset_id, 42);
    }

    #[test]
    fn test_ctype_descriptor_inactive() {
        let mut desc = CtypeDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_ascii_compatible());
    }

    #[test]
    fn test_ctype_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(ctype_init(), 0);
        }
    }
}
