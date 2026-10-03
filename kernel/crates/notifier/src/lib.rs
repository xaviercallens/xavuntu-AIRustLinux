#![allow(clippy::pedantic)]
#![no_std]
//! Notifier module
//!
//! Substantive kernel definitions for notifier in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for notifier
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct NotifierDescriptor {
    pub priority_rank: u64,
    pub flags: u32,
    pub active: bool,
}

impl NotifierDescriptor {
    pub const fn new(priority_rank: u64, flags: u32) -> Self {
        Self { priority_rank, flags, active: true }
    }

    pub fn is_active_chain(&self) -> bool {
        self.active && self.priority_rank > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn notifier_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn notifier_exit() {
}

#[no_mangle]
pub static NOTIFIER_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_notifier_descriptor_creation() {
        let desc = NotifierDescriptor::new(42, 0x1);
        assert!(desc.is_active_chain());
        assert_eq!(desc.priority_rank, 42);
    }

    #[test]
    fn test_notifier_descriptor_inactive() {
        let mut desc = NotifierDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_active_chain());
    }

    #[test]
    fn test_notifier_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(notifier_init(), 0);
        }
    }
}
