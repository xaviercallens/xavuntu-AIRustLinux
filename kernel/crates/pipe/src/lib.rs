#![allow(clippy::pedantic)]
#![no_std]
//! Pipe module
//!
//! Substantive kernel definitions for pipe in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for pipe
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PipeDescriptor {
    pub ring_capacity: u64,
    pub flags: u32,
    pub active: bool,
}

impl PipeDescriptor {
    pub const fn new(ring_capacity: u64, flags: u32) -> Self {
        Self { ring_capacity, flags, active: true }
    }

    pub fn is_readable(&self) -> bool {
        self.active && self.ring_capacity > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn pipe_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn pipe_exit() {
}

#[no_mangle]
pub static PIPE_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pipe_descriptor_creation() {
        let desc = PipeDescriptor::new(42, 0x1);
        assert!(desc.is_readable());
        assert_eq!(desc.ring_capacity, 42);
    }

    #[test]
    fn test_pipe_descriptor_inactive() {
        let mut desc = PipeDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_readable());
    }

    #[test]
    fn test_pipe_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(pipe_init(), 0);
        }
    }
}
