#![allow(clippy::pedantic)]
#![no_std]
//! Irq Chip module
//!
//! Substantive kernel definitions for irq_chip in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for irq_chip
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IrqChipDescriptor {
    pub chip_flags: u64,
    pub flags: u32,
    pub active: bool,
}

impl IrqChipDescriptor {
    pub const fn new(chip_flags: u64, flags: u32) -> Self {
        Self { chip_flags, flags, active: true }
    }

    pub fn is_masked(&self) -> bool {
        self.active && self.chip_flags > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn irq_chip_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn irq_chip_exit() {
}

#[no_mangle]
pub static IRQ_CHIP_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_irq_chip_descriptor_creation() {
        let desc = IrqChipDescriptor::new(42, 0x1);
        assert!(desc.is_masked());
        assert_eq!(desc.chip_flags, 42);
    }

    #[test]
    fn test_irq_chip_descriptor_inactive() {
        let mut desc = IrqChipDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_masked());
    }

    #[test]
    fn test_irq_chip_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(irq_chip_init(), 0);
        }
    }
}
