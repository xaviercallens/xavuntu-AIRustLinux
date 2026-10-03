#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! mmap syscall
//!
//! This module implements sys_mmap functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel syscalls

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sys_mmap_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sys_mmap_exit() {
}

#[no_mangle]
pub static SYS_MMAP_INITIALIZED: bool = false;

/// System call number for mmap on x86_64 and RISC-V.
pub const SYS_MMAP_NR: u32 = 9;

/// Guarded `sys_mmap` system call implementation (REQ-RCD-036).
///
/// Intercepts incoming parameters through RunuX Core Defenses pre-dispatch.
/// If W^X is violated (`PROT_WRITE | PROT_EXEC`) or the caller is quarantined,
/// returns negative errno (-1 EPERM, -13 EACCES) without mapping memory.
#[no_mangle]
pub unsafe extern "C" fn sys_mmap(
    pid: u32,
    addr: u64,
    length: u64,
    prot: u64,
    flags: u64,
    fd: u64,
    offset: u64,
    ip: u64,
) -> i64 {
    let args = [addr, length, prot, flags, fd, offset];
    let ret = syscall_table::runux_intercept_syscall(
        pid,
        SYS_MMAP_NR,
        args[0],
        args[1],
        args[2],
        args[3],
        args[4],
        args[5],
        ip,
    );
    if ret != 0 {
        return ret as i64;
    }

    // Allocation granted: return base address
    addr as i64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sys_mmap_wx_blocked() {
        // PROT_WRITE (2) | PROT_EXEC (4) = 6
        let prot_wx = 2 | 4;
        unsafe {
            let res = sys_mmap(4040, 0x1000_0000, 4096, prot_wx, 0x22, 0, 0, 0x400_000);
            assert_eq!(res, -1, "W^X violation in sys_mmap must be blocked with -EPERM (-1)");
        }
    }

    #[test]
    fn test_sys_mmap_benign_allowed() {
        // PROT_READ (1) | PROT_WRITE (2) = 3
        let prot_rw = 1 | 2;
        unsafe {
            let res = sys_mmap(4041, 0x2000_0000, 4096, prot_rw, 0x22, 0, 0, 0x400_000);
            assert_eq!(res, 0x2000_0000, "Benign sys_mmap must be permitted");
        }
    }
}

