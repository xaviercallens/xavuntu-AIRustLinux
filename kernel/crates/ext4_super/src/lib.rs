#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! ext4 superblock
//!
//! This module implements ext4_super functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel fs/ext4

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn ext4_super_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn ext4_super_exit() {
}

#[no_mangle]
pub static EXT4_SUPER_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_ext4_super_init_stub() {
        unsafe { assert_eq!(ext4_super_init(), -38); }
    }
}
