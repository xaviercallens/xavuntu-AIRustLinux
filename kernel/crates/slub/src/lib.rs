#![no_std]
#![deny(clippy::all)]
#![warn(clippy::pedantic)]

//! SLUB allocator
//!
//! This module implements slub functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel mm/slub.c

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
/// # Safety
/// Caller must ensure safety preconditions.
pub unsafe extern "C" fn slub_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
/// # Safety
/// Caller must ensure safety preconditions.
pub unsafe extern "C" fn slub_exit() {
}

// Implementation deferred.
#[no_mangle]
pub static SLUB_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_init_exit() {
        unsafe {
            assert_eq!(slub_init(), 0);
            slub_exit();
            kmalloc(1024);
            kfree(1 as *mut core::ffi::c_void);
        }
    }
}
