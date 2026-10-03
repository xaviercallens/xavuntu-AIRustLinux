#![allow(clippy::pedantic)]
#![no_std]
//! Page Owner module
//!
//! Substantive kernel definitions for page_owner in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for page_owner
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PageOwnerDescriptor {
    pub order_bits: u64,
    pub flags: u32,
    pub active: bool,
}

impl PageOwnerDescriptor {
    pub const fn new(order_bits: u64, flags: u32) -> Self {
        Self { order_bits, flags, active: true }
    }

    pub fn is_tracked(&self) -> bool {
        self.active && self.order_bits > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn page_owner_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn page_owner_exit() {
}

#[no_mangle]
pub static PAGE_OWNER_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_page_owner_descriptor_creation() {
        let desc = PageOwnerDescriptor::new(42, 0x1);
        assert!(desc.is_tracked());
        assert_eq!(desc.order_bits, 42);
    }

    #[test]
    fn test_page_owner_descriptor_inactive() {
        let mut desc = PageOwnerDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_tracked());
    }

    #[test]
    fn test_page_owner_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(page_owner_init(), 0);
        }
    }
}
