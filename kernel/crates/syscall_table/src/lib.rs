#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! System Call Table with Pre-Dispatch Active Defense Hook
//!
//! Implements syscall table dispatch for the RunuX Kernel.
//! Every incoming system call from user-space / VMs passes through the
//! `ebpf_firewall` pre-dispatch hook before reaching the 297 standard modules.

use core::ffi::c_int;
use ebpf_firewall::{
    evaluate_syscall, is_pid_quarantined, quarantine_pid, DefenseWatchdog, SyscallAuditEvent,
    Verdict, SYS_CLONE, SYS_CONNECT, SYS_EXECVE, SYS_FORK, SYS_SENDTO, SYS_SOCKET,
};
use immutable_logs::AUDIT_LOG;
use ai_detector::evaluate_pid_event;

/// Pre-dispatch status code returned to the kernel syscall dispatcher (REQ-RCD-023).
#[repr(i32)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PreDispatchStatus {
    /// Permitted: continue execution to standard kernel handler.
    Allowed = 0,
    /// Denied with -EPERM: security violation detected.
    DeniedEperm = -1,
    /// Retry after rollback with -EAGAIN: state auto-repaired.
    RetryRollback = -11,
    /// Denied with -EACCES: process is quarantined.
    DeniedQuarantined = -13,
}

/// Comprehensive outcome of the Ring 0 pre-dispatch evaluation pipeline (REQ-RCD-023).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PreDispatchResult {
    pub status: PreDispatchStatus,
    pub final_verdict: Verdict,
    pub quarantined: bool,
    pub audit_logged: bool,
}

/// Evaluates an incoming system call through the full defense pipeline (REQ-RCD-023).
///
/// Automatically enforces process quarantine and records violations to the append-only Merkle tree.
pub fn runux_pre_dispatch_pipeline(
    pid: u32,
    nr: u32,
    args: [u64; 6],
    ip: u64,
) -> PreDispatchResult {
    // 1. Quarantined PIDs are unconditionally blocked from process spawning and network access (REQ-RCD-011)
    if is_pid_quarantined(pid)
        && (nr == SYS_FORK
            || nr == SYS_CLONE
            || nr == SYS_EXECVE
            || nr == SYS_SOCKET
            || nr == SYS_CONNECT
            || nr == SYS_SENDTO)
    {
        return PreDispatchResult {
            status: PreDispatchStatus::DeniedQuarantined,
            final_verdict: Verdict::BlockKill,
            quarantined: true,
            audit_logged: false,
        };
    }

    // 2. Primary evaluation: eBPF / LMS firewall rules
    let mut verdict = evaluate_syscall(pid, nr, args, ip);

    // 3. Deep inspection via TinyML ai_detector if requested
    if verdict == Verdict::InspectDeep {
        let ev = SyscallAuditEvent::new(pid, nr, args, ip);
        let ai_verdict = evaluate_pid_event(pid, ev);
        if ai_verdict == Verdict::BlockKill || ai_verdict == Verdict::Rollback {
            verdict = ai_verdict;
        }
    }

    // 4. Action disposition based on final verdict
    match verdict {
        Verdict::Pass | Verdict::InspectDeep => PreDispatchResult {
            status: PreDispatchStatus::Allowed,
            final_verdict: verdict,
            quarantined: false,
            audit_logged: false,
        },
        Verdict::BlockKill => {
            // Automatically quarantine the malicious process
            let _ = quarantine_pid(pid);
            // Append violation to immutable Merkle log
            let ev = SyscallAuditEvent::new(pid, nr, args, ip);
            AUDIT_LOG.record(&ev, Verdict::BlockKill);

            PreDispatchResult {
                status: PreDispatchStatus::DeniedEperm,
                final_verdict: Verdict::BlockKill,
                quarantined: true,
                audit_logged: true,
            }
        }
        Verdict::Rollback => {
            let ev = SyscallAuditEvent::new(pid, nr, args, ip);
            AUDIT_LOG.record(&ev, Verdict::Rollback);

            PreDispatchResult {
                status: PreDispatchStatus::RetryRollback,
                final_verdict: Verdict::Rollback,
                quarantined: false,
                audit_logged: true,
            }
        }
    }
}

/// Evaluates incoming syscall guarded by a microsecond defense watchdog (REQ-RCD-035).
///
/// If defense evaluation exceeds cycle budget, triggers graceful rollback without crashing.
pub fn runux_pre_dispatch_pipeline_with_watchdog(
    pid: u32,
    nr: u32,
    args: [u64; 6],
    ip: u64,
    watchdog: &DefenseWatchdog,
    current_cycles: u64,
) -> PreDispatchResult {
    if watchdog.is_expired(current_cycles) {
        let ev = SyscallAuditEvent::new(pid, nr, args, ip);
        AUDIT_LOG.record(&ev, Verdict::Rollback);

        PreDispatchResult {
            status: PreDispatchStatus::RetryRollback,
            final_verdict: Verdict::Rollback,
            quarantined: false,
            audit_logged: true,
        }
    } else {
        runux_pre_dispatch_pipeline(pid, nr, args, ip)
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn syscall_table_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn syscall_table_exit() {}

#[no_mangle]
pub static SYSCALL_TABLE_INITIALIZED: core::sync::atomic::AtomicBool = core::sync::atomic::AtomicBool::new(false);

/// Pre-dispatch active defense interception hook.
///
/// Evaluates incoming syscall arguments against eBPF/LMS security rules.
/// Returns 0 if permitted (`Verdict::Pass` or `Verdict::InspectDeep`),
/// or a negative Linux errno (`-1` EPERM, `-13` EACCES) if blocked.
#[no_mangle]
pub unsafe extern "C" fn runux_intercept_syscall(
    pid: u32,
    nr: u32,
    arg0: u64,
    arg1: u64,
    arg2: u64,
    arg3: u64,
    arg4: u64,
    arg5: u64,
    ip: u64,
) -> c_int {
    let args = [arg0, arg1, arg2, arg3, arg4, arg5];
    let result = runux_pre_dispatch_pipeline(pid, nr, args, ip);
    result.status as c_int
}

// ---------------------------------------------------------------------------
// REQ-RCD-036: Unified System Call Table Dispatcher with Defense Guard
// ---------------------------------------------------------------------------

/// Maximum number of system call numbers supported in the kernel dispatch table (REQ-RCD-036).
pub const MAX_SYSCALL_HANDLERS: usize = 512;

/// Standard kernel system call handler function pointer signature.
pub type SyscallHandler = fn(pid: u32, args: [u64; 6], ip: u64) -> i32;

/// System call table entry mapping a system call number to its handler and human-readable name.
#[derive(Clone, Copy)]
pub struct SyscallDispatchEntry {
    pub nr: u32,
    pub handler: Option<SyscallHandler>,
    pub name: &'static str,
}

impl SyscallDispatchEntry {
    #[must_use]
    pub const fn empty() -> Self {
        Self {
            nr: 0,
            handler: None,
            name: "sys_unknown",
        }
    }

    #[must_use]
    pub const fn new(nr: u32, handler: SyscallHandler, name: &'static str) -> Self {
        Self {
            nr,
            handler: Some(handler),
            name,
        }
    }
}

/// Static, zero-allocation dispatch table mapping system call numbers to kernel handlers (REQ-RCD-036).
pub struct SyscallDispatchTable<const MAX: usize = MAX_SYSCALL_HANDLERS> {
    pub entries: [SyscallDispatchEntry; MAX],
}

impl SyscallDispatchTable<MAX_SYSCALL_HANDLERS> {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            entries: [SyscallDispatchEntry::empty(); MAX_SYSCALL_HANDLERS],
        }
    }
}

impl<const MAX: usize> SyscallDispatchTable<MAX> {
    #[must_use]
    pub const fn with_capacity() -> Self {
        Self {
            entries: [SyscallDispatchEntry::empty(); MAX],
        }
    }

    /// Registers a handler for a given system call number.
    pub fn register(&mut self, nr: u32, handler: SyscallHandler, name: &'static str) -> bool {
        let idx = nr as usize;
        if idx < MAX {
            self.entries[idx] = SyscallDispatchEntry::new(nr, handler, name);
            true
        } else {
            false
        }
    }

    /// Dispatches an incoming system call through the RunuX Core Defenses guard (REQ-RCD-036).
    ///
    /// Evaluates `runux_pre_dispatch_pipeline` first.
    /// If `PreDispatchStatus::Allowed`, invokes the registered handler.
    /// If denied or rollback, short-circuits execution and returns the negative errno without
    /// invoking the underlying handler.
    pub fn dispatch_guarded(
        &self,
        pid: u32,
        nr: u32,
        args: [u64; 6],
        ip: u64,
    ) -> i32 {
        let pre_res = runux_pre_dispatch_pipeline(pid, nr, args, ip);
        match pre_res.status {
            PreDispatchStatus::Allowed => {
                let idx = nr as usize;
                if idx < MAX {
                    if let Some(handler) = self.entries[idx].handler {
                        handler(pid, args, ip)
                    } else {
                        -38 // -ENOSYS: Function unmapped
                    }
                } else {
                    -38
                }
            }
            status => status as i32,
        }
    }
}

impl Default for SyscallDispatchTable<MAX_SYSCALL_HANDLERS> {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ebpf_firewall::{PROCESS_QUARANTINE, SYS_MPROTECT, PROT_WRITE, PROT_EXEC};

    #[test]
    fn test_quarantined_syscall_interception() {
        let pid = 9999;
        let _ = PROCESS_QUARANTINE.lift_quarantine(pid, true);
        assert!(quarantine_pid(pid));

        // SAFETY: Calling runux_intercept_syscall with these constant arguments is safe.
        // The function accepts only by-value scalar parameters (u32, u64) and performs no
        // pointer dereferences on the arguments. The function body safely constructs an array
        // and passes the values to runux_pre_dispatch_pipeline, which performs only value operations.
        unsafe {
            // Fork should be blocked with -13 (-EACCES) or -1 (-EPERM)
            let res_fork = runux_intercept_syscall(pid, SYS_FORK, 0, 0, 0, 0, 0, 0, 0x400_000);
            assert_eq!(res_fork, -13);

            // Benign syscall from unquarantined pid should pass (0)
            let res_benign = runux_intercept_syscall(10000, 1, 0, 0, 0, 0, 0, 0, 0x400_000);
            assert_eq!(res_benign, 0);
        }

        let _ = PROCESS_QUARANTINE.lift_quarantine(pid, true);
    }

    /// Verification of REQ-RCD-023: Kernel Syscall Table Pre-Dispatch Hook & Short-Circuit Dispatcher.
    #[test]
    fn test_req_rcd_023_pre_dispatch_short_circuit_and_quarantine() {
        let pid = 7777;
        let _ = PROCESS_QUARANTINE.lift_quarantine(pid, true);

        // 1. Attack syscall: W^X violation via mprotect(PROT_WRITE | PROT_EXEC)
        let attack_args = [0x1000_0000, 4096, PROT_WRITE | PROT_EXEC, 0, 0, 0];
        let res = runux_pre_dispatch_pipeline(pid, SYS_MPROTECT, attack_args, 0x400_100);

        // 2. Pre-dispatch short-circuits with DeniedEperm
        assert_eq!(res.status, PreDispatchStatus::DeniedEperm);
        assert_eq!(res.final_verdict, Verdict::BlockKill);
        assert!(res.quarantined, "PID must be quarantined upon BlockKill");
        assert!(res.audit_logged, "Violation must be logged to Merkle tree");

        // 3. Confirm PID is recorded in PROCESS_QUARANTINE
        assert!(is_pid_quarantined(pid));

        // 4. Subsequent process creation or network calls from this PID are immediately denied
        let fork_res = runux_pre_dispatch_pipeline(pid, SYS_FORK, [0; 6], 0x400_100);
        assert_eq!(fork_res.status, PreDispatchStatus::DeniedQuarantined);

        // 5. Clean up quarantine state
        let _ = PROCESS_QUARANTINE.lift_quarantine(pid, true);
    }

    /// Verification of REQ-RCD-035: Real-Time Microsecond Kernel Watchdog & Deadlock Breaker in Pre-Dispatch.
    #[test]
    fn test_req_rcd_035_pre_dispatch_watchdog_deadline() {
        let watchdog = DefenseWatchdog::new(1000, 200);

        // 1. Within budget: normal pass
        let res_ok = runux_pre_dispatch_pipeline_with_watchdog(
            5555,
            1, // sys_write
            [1, 0x7fff_0000, 16, 0, 0, 0],
            0x400_000,
            &watchdog,
            1100, // elapsed 100 <= 200
        );
        assert_eq!(res_ok.status, PreDispatchStatus::Allowed);

        // 2. Deadline exceeded: watchdog trips, triggering RetryRollback without panic
        let res_timeout = runux_pre_dispatch_pipeline_with_watchdog(
            5555,
            1,
            [1, 0x7fff_0000, 16, 0, 0, 0],
            0x400_000,
            &watchdog,
            1250, // elapsed 250 > 200
        );
        assert_eq!(res_timeout.status, PreDispatchStatus::RetryRollback);
        assert_eq!(res_timeout.final_verdict, Verdict::Rollback);
        assert!(res_timeout.audit_logged);
    }

    /// Verification of REQ-RCD-036: Unified System Call Table Dispatcher with Defense Guard.
    #[test]
    fn test_req_rcd_036_syscall_dispatch_table_guarded() {
        let mut table = SyscallDispatchTable::new();

        fn mock_sys_write(_pid: u32, args: [u64; 6], _ip: u64) -> i32 {
            args[2] as i32 // return bytes written
        }

        fn mock_sys_mprotect(_pid: u32, _args: [u64; 6], _ip: u64) -> i32 {
            0
        }

        assert!(table.register(1, mock_sys_write, "sys_write"));
        assert!(table.register(SYS_MPROTECT, mock_sys_mprotect, "sys_mprotect"));

        // 1. Benign sys_write call passes guard and executes handler
        let benign_args = [1, 0x7fff_0000, 42, 0, 0, 0];
        let res_write = table.dispatch_guarded(1234, 1, benign_args, 0x400_000);
        assert_eq!(res_write, 42, "Registered handler must be invoked on benign call");

        // 2. Malicious W^X violation via mprotect is intercepted by pre-dispatch guard
        let attack_args = [0x1000_0000, 4096, PROT_WRITE | PROT_EXEC, 0, 0, 0];
        let res_attack = table.dispatch_guarded(1234, SYS_MPROTECT, attack_args, 0x400_000);
        assert_eq!(res_attack, PreDispatchStatus::DeniedEperm as i32, "Guard must abort execution without invoking handler");

        // 3. Unimplemented syscall returns -ENOSYS (-38)
        let res_enosys = table.dispatch_guarded(1234, 999, [0; 6], 0x400_000);
        assert_eq!(res_enosys, -38);
    }
}

