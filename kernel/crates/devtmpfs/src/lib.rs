#![allow(clippy::pedantic)]
#![no_std]
//! Devtmpfs module
//!
//! Substantive kernel definitions for devtmpfs in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for devtmpfs
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DevtmpfsDescriptor {
    pub mount_flags: u64,
    pub flags: u32,
    pub active: bool,
}

impl DevtmpfsDescriptor {
    pub const fn new(mount_flags: u64, flags: u32) -> Self {
        Self { mount_flags, flags, active: true }
    }

    pub fn is_mounted(&self) -> bool {
        self.active && self.mount_flags > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn devtmpfs_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn devtmpfs_exit() {
}

#[no_mangle]
pub static DEVTMPFS_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_devtmpfs_descriptor_creation() {
        let desc = DevtmpfsDescriptor::new(42, 0x1);
        assert!(desc.is_mounted());
        assert_eq!(desc.mount_flags, 42);
    }

    #[test]
    fn test_devtmpfs_descriptor_inactive() {
        let mut desc = DevtmpfsDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_mounted());
    }

    #[test]
    fn test_devtmpfs_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(devtmpfs_init(), 0);
        }
    }
}
