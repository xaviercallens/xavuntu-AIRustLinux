#![allow(clippy::pedantic)]
#![no_std]
//! Klist module
//!
//! Substantive kernel definitions for klist in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for klist
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct KlistDescriptor {
    pub node_count: u64,
    pub flags: u32,
    pub active: bool,
}

impl KlistDescriptor {
    pub const fn new(node_count: u64, flags: u32) -> Self {
        Self { node_count, flags, active: true }
    }

    pub fn is_iterating(&self) -> bool {
        self.active && self.node_count > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn klist_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn klist_exit() {
}

#[no_mangle]
pub static KLIST_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_klist_descriptor_creation() {
        let desc = KlistDescriptor::new(42, 0x1);
        assert!(desc.is_iterating());
        assert_eq!(desc.node_count, 42);
    }

    #[test]
    fn test_klist_descriptor_inactive() {
        let mut desc = KlistDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_iterating());
    }

    #[test]
    fn test_klist_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(klist_init(), 0);
        }
    }
}
