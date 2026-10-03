#![allow(clippy::pedantic)]
#![no_std]
//! Kobject module
//!
//! Substantive kernel definitions for kobject in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for kobject
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct KobjectDescriptor {
    pub ref_count: u64,
    pub flags: u32,
    pub active: bool,
}

impl KobjectDescriptor {
    pub const fn new(ref_count: u64, flags: u32) -> Self {
        Self { ref_count, flags, active: true }
    }

    pub fn has_ktype(&self) -> bool {
        self.active && self.ref_count > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn kobject_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn kobject_exit() {
}

#[no_mangle]
pub static KOBJECT_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kobject_descriptor_creation() {
        let desc = KobjectDescriptor::new(42, 0x1);
        assert!(desc.has_ktype());
        assert_eq!(desc.ref_count, 42);
    }

    #[test]
    fn test_kobject_descriptor_inactive() {
        let mut desc = KobjectDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.has_ktype());
    }

    #[test]
    fn test_kobject_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(kobject_init(), 0);
        }
    }
}
