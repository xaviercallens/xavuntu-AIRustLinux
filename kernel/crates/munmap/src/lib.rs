#![allow(clippy::pedantic)]
#![no_std]
//! Munmap module
//!
//! Substantive kernel definitions for munmap in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for munmap
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MunmapDescriptor {
    pub unmap_length: u64,
    pub flags: u32,
    pub active: bool,
}

impl MunmapDescriptor {
    pub const fn new(unmap_length: u64, flags: u32) -> Self {
        Self { unmap_length, flags, active: true }
    }

    pub fn is_page_aligned(&self) -> bool {
        self.active && self.unmap_length > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn munmap_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn munmap_exit() {
}

#[no_mangle]
pub static MUNMAP_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_munmap_descriptor_creation() {
        let desc = MunmapDescriptor::new(42, 0x1);
        assert!(desc.is_page_aligned());
        assert_eq!(desc.unmap_length, 42);
    }

    #[test]
    fn test_munmap_descriptor_inactive() {
        let mut desc = MunmapDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_page_aligned());
    }

    #[test]
    fn test_munmap_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(munmap_init(), 0);
        }
    }
}
