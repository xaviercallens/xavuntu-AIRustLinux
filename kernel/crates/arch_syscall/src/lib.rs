#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Syscall entry
//!
//! This module implements arch_syscall functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel arch/x86/entry

use core::ffi::c_int;
use syscall_table::runux_intercept_syscall;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn arch_syscall_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn arch_syscall_exit() {}

#[no_mangle]
pub static ARCH_SYSCALL_INITIALIZED: bool = false;

/// Architecture-specific entry point that invokes RunuX Core Defenses interception.
#[no_mangle]
pub unsafe extern "C" fn arch_syscall_dispatch(
    pid: u32,
    nr: u32,
    args: *const u64,
    ip: u64,
) -> c_int {
    if args.is_null() {
        return -1;
    }
    let a0 = *args;
    let a1 = *args.add(1);
    let a2 = *args.add(2);
    let a3 = *args.add(3);
    let a4 = *args.add(4);
    let a5 = *args.add(5);
    runux_intercept_syscall(pid, nr, a0, a1, a2, a3, a4, a5, ip)
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_arch_syscall_init_stub() {
        unsafe { assert_eq!(arch_syscall_init(), -38); }
    }
    use super::*;

    #[test]
    fn test_arch_dispatch_benign() {
        let args = [1u64, 0x7fff_0000, 16, 0, 0, 0];
        unsafe {
            let res = arch_syscall_dispatch(1001, 1, args.as_ptr(), 0x400_000);
            assert_eq!(res, 0);
        }
    }

    #[test]
    fn test_arch_dispatch_null_args() {
        unsafe {
            let res = arch_syscall_dispatch(1001, 1, core::ptr::null(), 0x400_000);
            assert_eq!(res, -1);
        }
    }
}
