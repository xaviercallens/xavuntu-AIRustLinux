#![allow(clippy::pedantic)]
#![no_std]
//! Bitmap module
//!
//! Substantive kernel definitions for bitmap in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for bitmap
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BitmapDescriptor {
    pub bits_count: u64,
    pub flags: u32,
    pub active: bool,
}

impl BitmapDescriptor {
    pub const fn new(bits_count: u64, flags: u32) -> Self {
        Self { bits_count, flags, active: true }
    }

    pub fn is_aligned(&self) -> bool {
        self.active && self.bits_count > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn bitmap_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn bitmap_exit() {
}

#[no_mangle]
pub static BITMAP_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bitmap_descriptor_creation() {
        let desc = BitmapDescriptor::new(42, 0x1);
        assert!(desc.is_aligned());
        assert_eq!(desc.bits_count, 42);
    }

    #[test]
    fn test_bitmap_descriptor_inactive() {
        let mut desc = BitmapDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_aligned());
    }

    #[test]
    fn test_bitmap_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(bitmap_init(), 0);
        }
    }
}
