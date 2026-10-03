#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Filesystem syscalls
//!
//! This module implements sys_fs functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel syscalls

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sys_fs_init() -> c_int {
    // Implementation deferred.
    -38 // ENOSYS: not yet implemented
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sys_fs_exit() {
}

#[no_mangle]
pub static SYS_FS_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_sys_fs_init_stub() {
        unsafe { assert_eq!(sys_fs_init(), -38); }
    }
}
