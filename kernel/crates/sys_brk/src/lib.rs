#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! brk syscall
//!
//! This module implements sys_brk functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel syscalls

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sys_brk_init() -> c_int {
    // Implementation deferred.
    -38 // ENOSYS: not yet implemented
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sys_brk_exit() {
}

#[no_mangle]
pub static SYS_BRK_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_sys_brk_init_stub() {
        unsafe { assert_eq!(sys_brk_init(), -38); }
    }
}
