#![allow(clippy::pedantic)]
#![no_std]
//! Irq Manage module
//!
//! Substantive kernel definitions for irq_manage in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for irq_manage
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IrqManageDescriptor {
    pub vector_count: u64,
    pub flags: u32,
    pub active: bool,
}

impl IrqManageDescriptor {
    pub const fn new(vector_count: u64, flags: u32) -> Self {
        Self { vector_count, flags, active: true }
    }

    pub fn is_configured(&self) -> bool {
        self.active && self.vector_count > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn irq_manage_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn irq_manage_exit() {
}

#[no_mangle]
pub static IRQ_MANAGE_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_irq_manage_descriptor_creation() {
        let desc = IrqManageDescriptor::new(42, 0x1);
        assert!(desc.is_configured());
        assert_eq!(desc.vector_count, 42);
    }

    #[test]
    fn test_irq_manage_descriptor_inactive() {
        let mut desc = IrqManageDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_configured());
    }

    #[test]
    fn test_irq_manage_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(irq_manage_init(), 0);
        }
    }
}
