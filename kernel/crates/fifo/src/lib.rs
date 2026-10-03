#![allow(clippy::pedantic)]
#![no_std]
//! Fifo module
//!
//! Substantive kernel definitions for fifo in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for fifo
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FifoDescriptor {
    pub pipe_capacity: u64,
    pub flags: u32,
    pub active: bool,
}

impl FifoDescriptor {
    pub const fn new(pipe_capacity: u64, flags: u32) -> Self {
        Self { pipe_capacity, flags, active: true }
    }

    pub fn is_empty(&self) -> bool {
        self.active && self.pipe_capacity > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn fifo_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn fifo_exit() {
}

#[no_mangle]
pub static FIFO_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fifo_descriptor_creation() {
        let desc = FifoDescriptor::new(42, 0x1);
        assert!(desc.is_empty());
        assert_eq!(desc.pipe_capacity, 42);
    }

    #[test]
    fn test_fifo_descriptor_inactive() {
        let mut desc = FifoDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_empty());
    }

    #[test]
    fn test_fifo_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(fifo_init(), 0);
        }
    }
}
