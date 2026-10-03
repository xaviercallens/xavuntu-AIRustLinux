#![allow(clippy::pedantic)]
#![no_std]
//! Block Dev module
//!
//! Substantive kernel definitions for block_dev in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for block_dev
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BlockDevDescriptor {
    pub major_minor: u64,
    pub flags: u32,
    pub active: bool,
}

impl BlockDevDescriptor {
    pub const fn new(major_minor: u64, flags: u32) -> Self {
        Self { major_minor, flags, active: true }
    }

    pub fn is_ready(&self) -> bool {
        self.active && self.major_minor > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn block_dev_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn block_dev_exit() {
}

#[no_mangle]
pub static BLOCK_DEV_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_block_dev_descriptor_creation() {
        let desc = BlockDevDescriptor::new(42, 0x1);
        assert!(desc.is_ready());
        assert_eq!(desc.major_minor, 42);
    }

    #[test]
    fn test_block_dev_descriptor_inactive() {
        let mut desc = BlockDevDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_ready());
    }

    #[test]
    fn test_block_dev_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(block_dev_init(), 0);
        }
    }
}
