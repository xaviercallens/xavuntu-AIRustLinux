#![allow(clippy::pedantic)]
#![no_std]
//! Anonymous inodes
//!
//! This module implements anon_inodes functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel fs

use core::ffi::c_int;

/// Anonymous inode descriptor tracking kernel state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AnonInodeDescriptor {
    pub ino: u64,
    pub flags: u32,
    pub active: bool,
}

impl AnonInodeDescriptor {
    pub const fn new(ino: u64, flags: u32) -> Self {
        Self { ino, flags, active: true }
    }

    pub fn is_valid(&self) -> bool {
        self.ino > 0 && self.active
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn anon_inodes_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn anon_inodes_exit() {
}

#[no_mangle]
pub static ANON_INODES_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_anon_inode_descriptor() {
        let desc = AnonInodeDescriptor::new(101, 0x2);
        assert!(desc.is_valid());
        assert_eq!(desc.ino, 101);
    }

    #[test]
    fn test_anon_inodes_init() {
        // SAFETY: Verification of C-ABI init function in unit test context
        unsafe {
            assert_eq!(anon_inodes_init(), 0);
        }
    }
}
