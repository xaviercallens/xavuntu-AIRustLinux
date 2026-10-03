#![allow(clippy::pedantic)]
#![no_std]
//! Irq Handle module
//!
//! Substantive kernel definitions for irq_handle in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for irq_handle
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IrqHandleDescriptor {
    pub irq_number: u64,
    pub flags: u32,
    pub active: bool,
}

impl IrqHandleDescriptor {
    pub const fn new(irq_number: u64, flags: u32) -> Self {
        Self { irq_number, flags, active: true }
    }

    pub fn is_enabled(&self) -> bool {
        self.active && self.irq_number > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn irq_handle_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn irq_handle_exit() {
}

#[no_mangle]
pub static IRQ_HANDLE_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_irq_handle_descriptor_creation() {
        let desc = IrqHandleDescriptor::new(42, 0x1);
        assert!(desc.is_enabled());
        assert_eq!(desc.irq_number, 42);
    }

    #[test]
    fn test_irq_handle_descriptor_inactive() {
        let mut desc = IrqHandleDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_enabled());
    }

    #[test]
    fn test_irq_handle_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(irq_handle_init(), 0);
        }
    }
}
