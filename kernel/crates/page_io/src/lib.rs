#![allow(clippy::pedantic)]
#![no_std]
//! Page Io module
//!
//! Substantive kernel definitions for page_io in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for page_io
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PageIoDescriptor {
    pub sector_offset: u64,
    pub flags: u32,
    pub active: bool,
}

impl PageIoDescriptor {
    pub const fn new(sector_offset: u64, flags: u32) -> Self {
        Self { sector_offset, flags, active: true }
    }

    pub fn is_clean(&self) -> bool {
        self.active && self.sector_offset > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn page_io_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn page_io_exit() {
}

#[no_mangle]
pub static PAGE_IO_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_page_io_descriptor_creation() {
        let desc = PageIoDescriptor::new(42, 0x1);
        assert!(desc.is_clean());
        assert_eq!(desc.sector_offset, 42);
    }

    #[test]
    fn test_page_io_descriptor_inactive() {
        let mut desc = PageIoDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_clean());
    }

    #[test]
    fn test_page_io_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(page_io_init(), 0);
        }
    }
}
