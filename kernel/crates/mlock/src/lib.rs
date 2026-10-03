#![allow(clippy::pedantic)]
#![no_std]
//! Mlock module
//!
//! Substantive kernel definitions for mlock in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for mlock
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MlockDescriptor {
    pub locked_pages: u64,
    pub flags: u32,
    pub active: bool,
}

impl MlockDescriptor {
    pub const fn new(locked_pages: u64, flags: u32) -> Self {
        Self { locked_pages, flags, active: true }
    }

    pub fn is_within_limit(&self) -> bool {
        self.active && self.locked_pages > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn mlock_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn mlock_exit() {
}

#[no_mangle]
pub static MLOCK_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mlock_descriptor_creation() {
        let desc = MlockDescriptor::new(42, 0x1);
        assert!(desc.is_within_limit());
        assert_eq!(desc.locked_pages, 42);
    }

    #[test]
    fn test_mlock_descriptor_inactive() {
        let mut desc = MlockDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_within_limit());
    }

    #[test]
    fn test_mlock_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(mlock_init(), 0);
        }
    }
}
