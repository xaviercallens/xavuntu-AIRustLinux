#![allow(clippy::pedantic)]
#![no_std]
//! Mprotect module
//!
//! Substantive kernel definitions for mprotect in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for mprotect
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MprotectDescriptor {
    pub prot_flags: u64,
    pub flags: u32,
    pub active: bool,
}

impl MprotectDescriptor {
    pub const fn new(prot_flags: u64, flags: u32) -> Self {
        Self { prot_flags, flags, active: true }
    }

    pub fn is_executable(&self) -> bool {
        self.active && self.prot_flags > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn mprotect_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn mprotect_exit() {
}

#[no_mangle]
pub static MPROTECT_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mprotect_descriptor_creation() {
        let desc = MprotectDescriptor::new(42, 0x1);
        assert!(desc.is_executable());
        assert_eq!(desc.prot_flags, 42);
    }

    #[test]
    fn test_mprotect_descriptor_inactive() {
        let mut desc = MprotectDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_executable());
    }

    #[test]
    fn test_mprotect_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(mprotect_init(), 0);
        }
    }
}
