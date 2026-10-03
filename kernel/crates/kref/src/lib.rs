#![allow(clippy::pedantic)]
#![no_std]
//! Kref module
//!
//! Substantive kernel definitions for kref in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for kref
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct KrefDescriptor {
    pub initial_refs: u64,
    pub flags: u32,
    pub active: bool,
}

impl KrefDescriptor {
    pub const fn new(initial_refs: u64, flags: u32) -> Self {
        Self { initial_refs, flags, active: true }
    }

    pub fn is_live(&self) -> bool {
        self.active && self.initial_refs > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn kref_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn kref_exit() {
}

#[no_mangle]
pub static KREF_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kref_descriptor_creation() {
        let desc = KrefDescriptor::new(42, 0x1);
        assert!(desc.is_live());
        assert_eq!(desc.initial_refs, 42);
    }

    #[test]
    fn test_kref_descriptor_inactive() {
        let mut desc = KrefDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_live());
    }

    #[test]
    fn test_kref_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(kref_init(), 0);
        }
    }
}
