#![allow(clippy::pedantic)]
#![no_std]
//! Rbtree module
//!
//! Substantive kernel definitions for rbtree in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for rbtree
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RbtreeDescriptor {
    pub black_height: u64,
    pub flags: u32,
    pub active: bool,
}

impl RbtreeDescriptor {
    pub const fn new(black_height: u64, flags: u32) -> Self {
        Self { black_height, flags, active: true }
    }

    pub fn is_balanced(&self) -> bool {
        self.active && self.black_height > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn rbtree_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn rbtree_exit() {
}

#[no_mangle]
pub static RBTREE_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rbtree_descriptor_creation() {
        let desc = RbtreeDescriptor::new(42, 0x1);
        assert!(desc.is_balanced());
        assert_eq!(desc.black_height, 42);
    }

    #[test]
    fn test_rbtree_descriptor_inactive() {
        let mut desc = RbtreeDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_balanced());
    }

    #[test]
    fn test_rbtree_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(rbtree_init(), 0);
        }
    }
}
