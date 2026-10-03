#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! access syscall
//!
//! This module implements sys_access functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel syscalls

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sys_access_init() -> c_int {
    // Implementation deferred.
    -38 // ENOSYS: not yet implemented
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sys_access_exit() {
}

#[no_mangle]
pub static SYS_ACCESS_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_sys_access_init_stub() {
        unsafe { assert_eq!(sys_access_init(), -38); }
    }
}
