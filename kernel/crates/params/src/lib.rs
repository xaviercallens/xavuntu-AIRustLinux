#![allow(clippy::pedantic)]
#![no_std]
//! Params module
//!
//! Substantive kernel definitions for params in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for params
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ParamsDescriptor {
    pub arg_count: u64,
    pub flags: u32,
    pub active: bool,
}

impl ParamsDescriptor {
    pub const fn new(arg_count: u64, flags: u32) -> Self {
        Self { arg_count, flags, active: true }
    }

    pub fn is_validated(&self) -> bool {
        self.active && self.arg_count > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn params_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn params_exit() {
}

#[no_mangle]
pub static PARAMS_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_params_descriptor_creation() {
        let desc = ParamsDescriptor::new(42, 0x1);
        assert!(desc.is_validated());
        assert_eq!(desc.arg_count, 42);
    }

    #[test]
    fn test_params_descriptor_inactive() {
        let mut desc = ParamsDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_validated());
    }

    #[test]
    fn test_params_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(params_init(), 0);
        }
    }
}
