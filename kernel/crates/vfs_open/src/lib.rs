#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! File opening
//!
//! This module implements vfs_open functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel fs/vfs

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn vfs_open_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn vfs_open_exit() {
}

#[no_mangle]
pub static VFS_OPEN_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_vfs_open_init_stub() {
        unsafe { assert_eq!(vfs_open_init(), -38); }
    }
}
