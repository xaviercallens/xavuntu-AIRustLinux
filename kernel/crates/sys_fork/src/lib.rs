#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! fork syscall
//!
//! This module implements sys_fork functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel syscalls

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sys_fork_init() -> c_int {
    // Implementation deferred.
    -38 // ENOSYS: not yet implemented
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sys_fork_exit() {
}

#[no_mangle]
pub static SYS_FORK_INITIALIZED: bool = false;

/// System call number for fork on x86_64 and RISC-V.
pub const SYS_FORK_NR: u32 = 57;

/// Guarded `sys_fork` system call implementation (REQ-RCD-036).
///
/// Intercepts incoming parameters through RunuX Core Defenses pre-dispatch.
/// If the caller is quarantined, returns -13 (-EACCES) without creating child process.
#[no_mangle]
pub unsafe extern "C" fn sys_fork(
    pid: u32,
    ip: u64,
) -> i64 {
    let args = [0; 6];
    let ret = syscall_table::runux_intercept_syscall(
        pid,
        SYS_FORK_NR,
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

    // Fork granted: simulated child PID
    (pid + 1) as i64
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_sys_fork_init_stub() {
        unsafe { assert_eq!(sys_fork_init(), -38); }
    }
    use super::*;
    use ebpf_firewall::{quarantine_pid, PROCESS_QUARANTINE};

    #[test]
    fn test_sys_fork_quarantined_blocked() {
        let pid = 8080;
        assert!(quarantine_pid(pid));
        unsafe {
            let res = sys_fork(pid, 0x400_000);
            assert_eq!(res, -13, "Quarantined process must be blocked from fork (-EACCES)");
        }
        let _ = PROCESS_QUARANTINE.lift_quarantine(pid, true);
    }

    #[test]
    fn test_sys_fork_benign_allowed() {
        let pid = 8081;
        unsafe {
            let res = sys_fork(pid, 0x400_000);
            assert_eq!(res, (pid + 1) as i64, "Benign sys_fork must succeed");
        }
    }
}

