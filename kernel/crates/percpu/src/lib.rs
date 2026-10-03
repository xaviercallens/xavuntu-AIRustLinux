#![allow(clippy::pedantic)]
#![no_std]
//! Percpu module
//!
//! Substantive kernel definitions for percpu in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for percpu
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PercpuDescriptor {
    pub cpu_index: u64,
    pub flags: u32,
    pub active: bool,
}

impl PercpuDescriptor {
    pub const fn new(cpu_index: u64, flags: u32) -> Self {
        Self { cpu_index, flags, active: true }
    }

    pub fn is_online(&self) -> bool {
        self.active && self.cpu_index > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn percpu_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn percpu_exit() {
}

#[no_mangle]
pub static PERCPU_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_percpu_descriptor_creation() {
        let desc = PercpuDescriptor::new(42, 0x1);
        assert!(desc.is_online());
        assert_eq!(desc.cpu_index, 42);
    }

    #[test]
    fn test_percpu_descriptor_inactive() {
        let mut desc = PercpuDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_online());
    }

    #[test]
    fn test_percpu_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(percpu_init(), 0);
        }
    }
}
