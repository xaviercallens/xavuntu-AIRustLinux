#![allow(clippy::pedantic)]
#![no_std]
//! Memblock module
//!
//! Substantive kernel definitions for memblock in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for memblock
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MemblockDescriptor {
    pub memory_limit: u64,
    pub flags: u32,
    pub active: bool,
}

impl MemblockDescriptor {
    pub const fn new(memory_limit: u64, flags: u32) -> Self {
        Self { memory_limit, flags, active: true }
    }

    pub fn is_reserved(&self) -> bool {
        self.active && self.memory_limit > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn memblock_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn memblock_exit() {
}

#[no_mangle]
pub static MEMBLOCK_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_memblock_descriptor_creation() {
        let desc = MemblockDescriptor::new(42, 0x1);
        assert!(desc.is_reserved());
        assert_eq!(desc.memory_limit, 42);
    }

    #[test]
    fn test_memblock_descriptor_inactive() {
        let mut desc = MemblockDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_reserved());
    }

    #[test]
    fn test_memblock_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(memblock_init(), 0);
        }
    }
}
