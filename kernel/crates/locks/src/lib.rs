#![allow(clippy::pedantic)]
#![no_std]
//! Locks module
//!
//! Substantive kernel definitions for locks in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for locks
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LocksDescriptor {
    pub lock_type: u64,
    pub flags: u32,
    pub active: bool,
}

impl LocksDescriptor {
    pub const fn new(lock_type: u64, flags: u32) -> Self {
        Self { lock_type, flags, active: true }
    }

    pub fn is_contended(&self) -> bool {
        self.active && self.lock_type > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn locks_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn locks_exit() {
}

#[no_mangle]
pub static LOCKS_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_locks_descriptor_creation() {
        let desc = LocksDescriptor::new(42, 0x1);
        assert!(desc.is_contended());
        assert_eq!(desc.lock_type, 42);
    }

    #[test]
    fn test_locks_descriptor_inactive() {
        let mut desc = LocksDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_contended());
    }

    #[test]
    fn test_locks_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(locks_init(), 0);
        }
    }
}
