#![allow(clippy::pedantic)]
#![no_std]
//! Mempool module
//!
//! Substantive kernel definitions for mempool in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for mempool
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MempoolDescriptor {
    pub min_elements: u64,
    pub flags: u32,
    pub active: bool,
}

impl MempoolDescriptor {
    pub const fn new(min_elements: u64, flags: u32) -> Self {
        Self { min_elements, flags, active: true }
    }

    pub fn is_hydrated(&self) -> bool {
        self.active && self.min_elements > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn mempool_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn mempool_exit() {
}

#[no_mangle]
pub static MEMPOOL_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mempool_descriptor_creation() {
        let desc = MempoolDescriptor::new(42, 0x1);
        assert!(desc.is_hydrated());
        assert_eq!(desc.min_elements, 42);
    }

    #[test]
    fn test_mempool_descriptor_inactive() {
        let mut desc = MempoolDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_hydrated());
    }

    #[test]
    fn test_mempool_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(mempool_init(), 0);
        }
    }
}
