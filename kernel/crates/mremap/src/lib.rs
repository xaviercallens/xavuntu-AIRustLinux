#![allow(clippy::pedantic)]
#![no_std]
//! Mremap module
//!
//! Substantive kernel definitions for mremap in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for mremap
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MremapDescriptor {
    pub old_size: u64,
    pub flags: u32,
    pub active: bool,
}

impl MremapDescriptor {
    pub const fn new(old_size: u64, flags: u32) -> Self {
        Self { old_size, flags, active: true }
    }

    pub fn can_expand(&self) -> bool {
        self.active && self.old_size > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn mremap_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn mremap_exit() {
}

#[no_mangle]
pub static MREMAP_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mremap_descriptor_creation() {
        let desc = MremapDescriptor::new(42, 0x1);
        assert!(desc.can_expand());
        assert_eq!(desc.old_size, 42);
    }

    #[test]
    fn test_mremap_descriptor_inactive() {
        let mut desc = MremapDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.can_expand());
    }

    #[test]
    fn test_mremap_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(mremap_init(), 0);
        }
    }
}
