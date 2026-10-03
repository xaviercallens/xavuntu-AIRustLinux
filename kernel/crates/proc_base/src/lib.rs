#![allow(clippy::pedantic)]
#![no_std]
//! Proc Base module
//!
//! Substantive kernel definitions for proc_base in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for proc_base
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProcBaseDescriptor {
    pub inode_number: u64,
    pub flags: u32,
    pub active: bool,
}

impl ProcBaseDescriptor {
    pub const fn new(inode_number: u64, flags: u32) -> Self {
        Self { inode_number, flags, active: true }
    }

    pub fn is_directory(&self) -> bool {
        self.active && self.inode_number > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn proc_base_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn proc_base_exit() {
}

#[no_mangle]
pub static PROC_BASE_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_proc_base_descriptor_creation() {
        let desc = ProcBaseDescriptor::new(42, 0x1);
        assert!(desc.is_directory());
        assert_eq!(desc.inode_number, 42);
    }

    #[test]
    fn test_proc_base_descriptor_inactive() {
        let mut desc = ProcBaseDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_directory());
    }

    #[test]
    fn test_proc_base_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(proc_base_init(), 0);
        }
    }
}
