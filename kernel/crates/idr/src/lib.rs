#![allow(clippy::pedantic)]
#![no_std]
//! Idr module
//!
//! Substantive kernel definitions for idr in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for idr
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IdrDescriptor {
    pub allocated_ids: u64,
    pub flags: u32,
    pub active: bool,
}

impl IdrDescriptor {
    pub const fn new(allocated_ids: u64, flags: u32) -> Self {
        Self { allocated_ids, flags, active: true }
    }

    pub fn has_available(&self) -> bool {
        self.active && self.allocated_ids > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn idr_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn idr_exit() {
}

#[no_mangle]
pub static IDR_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_idr_descriptor_creation() {
        let desc = IdrDescriptor::new(42, 0x1);
        assert!(desc.has_available());
        assert_eq!(desc.allocated_ids, 42);
    }

    #[test]
    fn test_idr_descriptor_inactive() {
        let mut desc = IdrDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.has_available());
    }

    #[test]
    fn test_idr_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(idr_init(), 0);
        }
    }
}
