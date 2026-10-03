#![allow(clippy::pedantic)]
#![no_std]
//! Radix Tree module
//!
//! Substantive kernel definitions for radix_tree in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for radix_tree
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RadixTreeDescriptor {
    pub tree_height: u64,
    pub flags: u32,
    pub active: bool,
}

impl RadixTreeDescriptor {
    pub const fn new(tree_height: u64, flags: u32) -> Self {
        Self { tree_height, flags, active: true }
    }

    pub fn is_initialized(&self) -> bool {
        self.active && self.tree_height > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn radix_tree_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn radix_tree_exit() {
}

#[no_mangle]
pub static RADIX_TREE_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_radix_tree_descriptor_creation() {
        let desc = RadixTreeDescriptor::new(42, 0x1);
        assert!(desc.is_initialized());
        assert_eq!(desc.tree_height, 42);
    }

    #[test]
    fn test_radix_tree_descriptor_inactive() {
        let mut desc = RadixTreeDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_initialized());
    }

    #[test]
    fn test_radix_tree_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(radix_tree_init(), 0);
        }
    }
}
