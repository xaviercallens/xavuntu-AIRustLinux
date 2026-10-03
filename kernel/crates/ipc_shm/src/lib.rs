#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Shared memory
//!
//! This module implements ipc_shm functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel ipc

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn ipc_shm_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn ipc_shm_exit() {
}

#[no_mangle]
pub static IPC_SHM_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_ipc_shm_init_stub() {
        unsafe { assert_eq!(ipc_shm_init(), -38); }
    }
}
