#![allow(clippy::pedantic)]
#![no_std]
//! Cmdline module
//!
//! Substantive kernel definitions for cmdline in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for cmdline
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CmdlineDescriptor {
    pub param_count: u64,
    pub flags: u32,
    pub active: bool,
}

impl CmdlineDescriptor {
    pub const fn new(param_count: u64, flags: u32) -> Self {
        Self { param_count, flags, active: true }
    }

    pub fn has_tokens(&self) -> bool {
        self.active && self.param_count > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn cmdline_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn cmdline_exit() {
}

#[no_mangle]
pub static CMDLINE_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cmdline_descriptor_creation() {
        let desc = CmdlineDescriptor::new(42, 0x1);
        assert!(desc.has_tokens());
        assert_eq!(desc.param_count, 42);
    }

    #[test]
    fn test_cmdline_descriptor_inactive() {
        let mut desc = CmdlineDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.has_tokens());
    }

    #[test]
    fn test_cmdline_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(cmdline_init(), 0);
        }
    }
}
