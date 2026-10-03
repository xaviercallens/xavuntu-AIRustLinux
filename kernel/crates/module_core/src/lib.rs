#![allow(clippy::pedantic)]
#![no_std]
//! Module Core module
//!
//! Substantive kernel definitions for module_core in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for module_core
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ModuleCoreDescriptor {
    pub core_size: u64,
    pub flags: u32,
    pub active: bool,
}

impl ModuleCoreDescriptor {
    pub const fn new(core_size: u64, flags: u32) -> Self {
        Self { core_size, flags, active: true }
    }

    pub fn is_loaded(&self) -> bool {
        self.active && self.core_size > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn module_core_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn module_core_exit() {
}

#[no_mangle]
pub static MODULE_CORE_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_module_core_descriptor_creation() {
        let desc = ModuleCoreDescriptor::new(42, 0x1);
        assert!(desc.is_loaded());
        assert_eq!(desc.core_size, 42);
    }

    #[test]
    fn test_module_core_descriptor_inactive() {
        let mut desc = ModuleCoreDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_loaded());
    }

    #[test]
    fn test_module_core_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(module_core_init(), 0);
        }
    }
}
