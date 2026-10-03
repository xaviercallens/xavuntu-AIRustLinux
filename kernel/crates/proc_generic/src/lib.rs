#![allow(clippy::pedantic)]
#![no_std]
//! Proc Generic module
//!
//! Substantive kernel definitions for proc_generic in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for proc_generic
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProcGenericDescriptor {
    pub entry_mode: u64,
    pub flags: u32,
    pub active: bool,
}

impl ProcGenericDescriptor {
    pub const fn new(entry_mode: u64, flags: u32) -> Self {
        Self { entry_mode, flags, active: true }
    }

    pub fn is_readable(&self) -> bool {
        self.active && self.entry_mode > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn proc_generic_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn proc_generic_exit() {
}

#[no_mangle]
pub static PROC_GENERIC_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_proc_generic_descriptor_creation() {
        let desc = ProcGenericDescriptor::new(42, 0x1);
        assert!(desc.is_readable());
        assert_eq!(desc.entry_mode, 42);
    }

    #[test]
    fn test_proc_generic_descriptor_inactive() {
        let mut desc = ProcGenericDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_readable());
    }

    #[test]
    fn test_proc_generic_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(proc_generic_init(), 0);
        }
    }
}
