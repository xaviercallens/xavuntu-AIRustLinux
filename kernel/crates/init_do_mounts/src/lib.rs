#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Root filesystem mounting
//!
//! This module implements init_do_mounts functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel init

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn init_do_mounts_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn init_do_mounts_exit() {
}

#[no_mangle]
pub static INIT_DO_MOUNTS_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_init_do_mounts_init_stub() {
        unsafe { assert_eq!(init_do_mounts_init(), -38); }
    }
}
