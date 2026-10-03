#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! exec syscall
//!
//! This module implements sys_exec functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel syscalls

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn sys_exec_init() -> c_int {
    // Implementation deferred.
    -38 // ENOSYS: not yet implemented
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn sys_exec_exit() {
}

#[no_mangle]
pub static SYS_EXEC_INITIALIZED: bool = false;

/// System call number for execve on x86_64 and RISC-V.
pub const SYS_EXECVE_NR: u32 = 59;

/// Guarded `sys_execve` system call implementation (REQ-RCD-036).
///
/// Intercepts incoming parameters through RunuX Core Defenses pre-dispatch.
/// If the caller is quarantined or executes from spoofed kernel IP,
/// returns negative errno (-1 EPERM, -13 EACCES) without spawning or replacing image.
#[no_mangle]
pub unsafe extern "C" fn sys_execve(
    pid: u32,
    filename_ptr: u64,
    argv_ptr: u64,
    envp_ptr: u64,
    ip: u64,
) -> i64 {
    let args = [filename_ptr, argv_ptr, envp_ptr, 0, 0, 0];
    let ret = syscall_table::runux_intercept_syscall(
        pid,
        SYS_EXECVE_NR,
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

    // Execution allowed
    0
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_sys_exec_init_stub() {
        unsafe { assert_eq!(sys_exec_init(), -38); }
    }
    use super::*;
    use ebpf_firewall::{quarantine_pid, PROCESS_QUARANTINE};

    #[test]
    fn test_sys_execve_quarantined_blocked() {
        let pid = 6060;
        assert!(quarantine_pid(pid));
        unsafe {
            let res = sys_execve(pid, 0x1000_0000, 0, 0, 0x400_000);
            assert_eq!(res, -13, "Quarantined process must be blocked from execve (-EACCES)");
        }
        let _ = PROCESS_QUARANTINE.lift_quarantine(pid, true);
    }

    #[test]
    fn test_sys_execve_kernel_ip_spoofing_blocked() {
        let pid = 6061;
        unsafe {
            // Spoofed kernel instruction pointer
            let res = sys_execve(pid, 0x1000_0000, 0, 0, 0xFFFF_8000_0000_1234);
            assert_eq!(res, -1, "Kernel IP spoofing must be blocked with -EPERM (-1)");
        }
    }

    #[test]
    fn test_sys_execve_benign_allowed() {
        let pid = 6062;
        unsafe {
            let res = sys_execve(pid, 0x1000_0000, 0, 0, 0x400_000);
            assert_eq!(res, 0, "Benign sys_execve must succeed");
        }
    }
}

