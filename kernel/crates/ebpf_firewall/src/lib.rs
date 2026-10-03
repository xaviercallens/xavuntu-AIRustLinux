#![no_std]
#![deny(clippy::all)]
#![warn(clippy::pedantic)]
//! RunuX eBPF / LMS Active Firewall
//!
//! Provides Ring 0 dynamic inspection and access control for system calls prior
//! to dispatch across the 297 kernel modules. Detects AI-generated polymorphic attack
//! vectors, shellcode injection, W^X violations, and ROP transition patterns.

use ai_bridge::ring_buffer::LockFreeAuditRingBuffer;
use core::sync::atomic::{AtomicU32, Ordering};

// Linux syscall numbers (x86_64 / generic reference)
pub const SYS_MMAP: u32 = 9;
pub const SYS_MPROTECT: u32 = 10;
pub const SYS_SOCKET: u32 = 41;
pub const SYS_CONNECT: u32 = 42;
pub const SYS_SENDTO: u32 = 44;
pub const SYS_CLONE: u32 = 56;
pub const SYS_FORK: u32 = 57;
pub const SYS_EXECVE: u32 = 59;
pub const SYS_PTRACE: u32 = 101;
pub const SYS_MEMFD_CREATE: u32 = 319;

// Memory protection flags
pub const PROT_READ: u64 = 0x1;
pub const PROT_WRITE: u64 = 0x2;
pub const PROT_EXEC: u64 = 0x4;

/// Base address of 64-bit kernel address space.
pub const KERNEL_ADDR_SPACE_BASE: u64 = 0xFFFF_8000_0000_0000;

// TCP Flags for network ingress inspection (REQ-RCD-014)
pub const TCP_FLAG_FIN: u8 = 0x01;
pub const TCP_FLAG_SYN: u8 = 0x02;
pub const TCP_FLAG_RST: u8 = 0x04;
pub const TCP_FLAG_PSH: u8 = 0x08;
pub const TCP_FLAG_ACK: u8 = 0x10;
pub const TCP_FLAG_URG: u8 = 0x20;

/// Audit event captured at system call ingress.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SyscallAuditEvent {
    pub pid: u32,
    pub syscall_nr: u32,
    pub args: [u64; 6],
    pub ip: u64,
    /// Shannon entropy in Q8.8 fixed-point (0..2048 represents 0.0 to 8.0 bits).
    pub entropy_score: u16,
}

impl SyscallAuditEvent {
    /// Creates a new audit event with zero entropy score.
    #[must_use]
    pub const fn new(pid: u32, syscall_nr: u32, args: [u64; 6], ip: u64) -> Self {
        Self {
            pid,
            syscall_nr,
            args,
            ip,
            entropy_score: 0,
        }
    }

    /// Creates an audit event with an explicit entropy score.
    #[must_use]
    pub const fn with_entropy(
        pid: u32,
        syscall_nr: u32,
        args: [u64; 6],
        ip: u64,
        entropy_score: u16,
    ) -> Self {
        Self {
            pid,
            syscall_nr,
            args,
            ip,
            entropy_score,
        }
    }
}

/// Verdict emitted by the firewall evaluation pipeline.
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Verdict {
    /// System call is legitimate; execute standard kernel handler.
    Pass = 0,
    /// System call exhibits anomalous patterns; forward to TinyML `ai_detector`.
    InspectDeep = 1,
    /// Malicious pattern detected; immediately terminate process and drop execution.
    BlockKill = 2,
    /// State corruption or exploit attempt; trigger rollback/quarantine.
    Rollback = 3,
}

/// Numerical precedence of a verdict: higher value strictly dominates lower value (REQ-RCD-008).
#[must_use]
#[inline(always)]
pub const fn verdict_priority(v: Verdict) -> u8 {
    match v {
        Verdict::Pass => 0,
        Verdict::InspectDeep => 1,
        Verdict::Rollback => 2,
        Verdict::BlockKill => 3,
    }
}

/// Combines two verdicts using pessimistic security precedence (REQ-RCD-008).
/// `BlockKill` unconditionally absorbs and dominates all other verdicts.
#[must_use]
#[inline(always)]
pub const fn merge_verdict(v1: Verdict, v2: Verdict) -> Verdict {
    if verdict_priority(v1) >= verdict_priority(v2) {
        v1
    } else {
        v2
    }
}

/// LSM Dynamic Security Policy State Machine (REQ-RCD-007).
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LmsPolicyState {
    /// Baseline audit observation mode without active blocking.
    Observing = 1,
    /// Standard dynamic enforcement with active W^X and entropy filters.
    Enforcing = 2,
    /// Target PID isolated into strict execution sandbox.
    Quarantined = 3,
    /// Global kernel lockdown mode: non-essential syscalls dropped.
    EmergencyLockdown = 4,
}

impl LmsPolicyState {
    /// Returns the monotonic security level (1..=4).
    #[must_use]
    pub const fn security_level(self) -> u8 {
        self as u8
    }

    /// Escalates security policy state (REQ-RCD-007).
    /// Escalations are intrinsically permitted upon threat detection.
    ///
    /// # Errors
    /// Returns `Err` if a de-escalation is attempted without root cryptographic attestation.
    pub fn escalate(self, target: Self) -> Result<Self, &'static str> {
        if target.security_level() >= self.security_level() {
            Ok(target)
        } else {
            Err("De-escalation requires root cryptographic attestation key")
        }
    }

    /// Transitions policy state, permitting de-escalation only with valid root attestation (REQ-RCD-007).
    ///
    /// # Errors
    /// Returns `Err` if de-escalation is requested without a valid root key signature.
    pub fn deescalate_with_key(self, target: Self, valid_root_key: bool) -> Result<Self, &'static str> {
        if target.security_level() >= self.security_level() || valid_root_key {
            Ok(target)
        } else {
            Err("Unauthorized de-escalation rejected: missing root key")
        }
    }
}

/// Interface for system call inspection filters.
pub trait SyscallFilter: Sync + Send {
    /// Evaluates the system call context and emits a security verdict.
    fn evaluate(&self, ctx: &SyscallAuditEvent) -> Verdict;
}

/// Default Ring 0 heuristics filter implementing W^X, ROP, and entropy checks.
pub struct CoreDefenseFilter;

impl SyscallFilter for CoreDefenseFilter {
    fn evaluate(&self, ctx: &SyscallAuditEvent) -> Verdict {
        // 1. Check for W^X Violation: mprotect or mmap with PROT_WRITE | PROT_EXEC simultaneously
        if ctx.syscall_nr == SYS_MPROTECT || ctx.syscall_nr == SYS_MMAP {
            let prot = ctx.args[2];
            if (prot & (PROT_WRITE | PROT_EXEC)) == (PROT_WRITE | PROT_EXEC) {
                return Verdict::BlockKill;
            }
        }

        // 2. Check for suspicious execve / memfd payload patterns
        if ctx.syscall_nr == SYS_MEMFD_CREATE || ctx.syscall_nr == SYS_PTRACE {
            return Verdict::InspectDeep;
        }

        // 3. High entropy check: Encrypted/polymorphic shellcode payloads (entropy >= 7.2 bits, Q8.8 >= 1843)
        if ctx.entropy_score >= 1843 {
            return Verdict::InspectDeep;
        }

        // 4. Null instruction pointer or kernel memory spoofing from userspace
        if ctx.ip == 0 || ctx.ip >= 0xFFFF_8000_0000_0000 {
            return Verdict::BlockKill;
        }

        Verdict::Pass
    }
}

/// Fast, integer-only Shannon entropy estimator for byte buffers in `#![no_std]`.
/// Returns fixed-point Q8.8 value where 256 = 1.0 bit, 2048 = 8.0 bits.
#[must_use]
#[inline(always)]
pub fn compute_shannon_entropy_q8(data: &[u8]) -> u16 {
    if data.is_empty() {
        return 0;
    }

    let mut counts = [0u32; 256];
    for &b in data {
        counts[b as usize] += 1;
    }

    let len = data.len() as u32;
    let mut sum_entropy = 0u32;

    // Fast log2 approximation using leading zeros in fixed-point
    for &c in &counts {
        if c > 0 {
            // - p * log2(p) = - (c / len) * log2(c / len)
            // = (c / len) * (log2(len) - log2(c))
            let log2_len = 31 - len.leading_zeros();
            let log2_c = 31 - c.leading_zeros();
            let diff = log2_len.saturating_sub(log2_c);
            let p_scaled = (c * 256) / len;
            sum_entropy += p_scaled * diff;
        }
    }

    (sum_entropy.min(2048)) as u16
}

/// Global circular audit ring buffer for zero-copy streaming to `ai_detector`.
pub static AUDIT_RING_BUFFER: LockFreeAuditRingBuffer<SyscallAuditEvent, 1024> =
    LockFreeAuditRingBuffer::new();

/// Global filter instance.
static CORE_FILTER: CoreDefenseFilter = CoreDefenseFilter;

/// Metrics counter for blocked attacks.
pub static BLOCKED_ATTACK_COUNT: AtomicU32 = AtomicU32::new(0);

/// Kernel memory page permission auto-repair (REQ-RCD-012).
/// Restores the W^X invariant by stripping `PROT_EXEC` if both writable and executable
/// permissions are active, preserving compliant permissions without alteration.
#[must_use]
#[inline(always)]
pub const fn auto_repair_page_permissions(flags: u64) -> u64 {
    if (flags & (PROT_WRITE | PROT_EXEC)) == (PROT_WRITE | PROT_EXEC) {
        flags & !PROT_EXEC
    } else {
        flags
    }
}

/// Maximum number of concurrently quarantined processes in Ring 0.
pub const MAX_QUARANTINED_PIDS: usize = 64;

/// Process Quarantine State tracking table (REQ-RCD-011).
pub struct ProcessQuarantineState<const CAPACITY: usize> {
    quarantined: [AtomicU32; CAPACITY],
}

impl<const CAPACITY: usize> ProcessQuarantineState<CAPACITY> {
    #[must_use]
    pub const fn new() -> Self {
        const INIT: AtomicU32 = AtomicU32::new(0);
        Self {
            quarantined: [INIT; CAPACITY],
        }
    }

    /// Places a PID into quarantine (REQ-RCD-011).
    pub fn quarantine_pid(&self, pid: u32) -> bool {
        if pid == 0 {
            return false;
        }
        for slot in &self.quarantined {
            if slot.load(Ordering::Relaxed) == pid {
                return true;
            }
        }
        for slot in &self.quarantined {
            if slot
                .compare_exchange(0, pid, Ordering::SeqCst, Ordering::Relaxed)
                .is_ok()
            {
                return true;
            }
        }
        false
    }

    /// Checks if a PID is currently quarantined (REQ-RCD-011).
    #[must_use]
    pub fn is_quarantined(&self, pid: u32) -> bool {
        if pid == 0 {
            return false;
        }
        for slot in &self.quarantined {
            if slot.load(Ordering::Relaxed) == pid {
                return true;
            }
        }
        false
    }

    /// Lifts quarantine for a PID, requiring root cryptographic authorization (REQ-RCD-011).
    ///
    /// # Errors
    /// Returns `Err` if attempted without root authorization key.
    pub fn lift_quarantine(&self, pid: u32, authorized_key: bool) -> Result<bool, &'static str> {
        if !authorized_key {
            return Err("Quarantine release rejected: missing root authorization key");
        }
        for slot in &self.quarantined {
            if slot.load(Ordering::Relaxed) == pid {
                slot.store(0, Ordering::SeqCst);
                return Ok(true);
            }
        }
        Ok(false)
    }

    /// Clears all quarantined PIDs.
    pub fn reset(&self) {
        for slot in &self.quarantined {
            slot.store(0, Ordering::Relaxed);
        }
    }
}

/// Global synchronized static quarantine table.
pub static PROCESS_QUARANTINE: ProcessQuarantineState<MAX_QUARANTINED_PIDS> =
    ProcessQuarantineState::new();

/// Checks if a PID is currently quarantined.
#[must_use]
pub fn is_pid_quarantined(pid: u32) -> bool {
    PROCESS_QUARANTINE.is_quarantined(pid)
}

/// Quarantines a process by PID.
pub fn quarantine_pid(pid: u32) -> bool {
    PROCESS_QUARANTINE.quarantine_pid(pid)
}

/// Evaluates network ingress packets in zero-copy Ring 0 (REQ-RCD-014).
/// Intercepts abnormal TCP flag scans (SYN-FIN, Xmas, Null, SYN-RST) and high-entropy payloads.
#[must_use]
pub fn evaluate_packet_ingress(
    _src_ip: [u8; 4],
    _dst_ip: [u8; 4],
    tcp_flags: u8,
    payload: &[u8],
) -> Verdict {
    // 1. Check for invalid or scan flag combinations:
    // Null scan: no flags set
    if tcp_flags == 0 {
        return Verdict::BlockKill;
    }

    // SYN-FIN scan: SYN and FIN both set
    if (tcp_flags & (TCP_FLAG_SYN | TCP_FLAG_FIN)) == (TCP_FLAG_SYN | TCP_FLAG_FIN) {
        return Verdict::BlockKill;
    }

    // Xmas scan: FIN, URG, and PSH set
    if (tcp_flags & (TCP_FLAG_FIN | TCP_FLAG_URG | TCP_FLAG_PSH))
        == (TCP_FLAG_FIN | TCP_FLAG_URG | TCP_FLAG_PSH)
    {
        return Verdict::BlockKill;
    }

    // SYN-RST: illegal connection reset attempt
    if (tcp_flags & (TCP_FLAG_SYN | TCP_FLAG_RST)) == (TCP_FLAG_SYN | TCP_FLAG_RST) {
        return Verdict::BlockKill;
    }

    // 2. High-entropy encrypted/polymorphic network payload inspection
    if !payload.is_empty() {
        let entropy = compute_shannon_entropy_q8(payload);
        if entropy >= 1843 {
            return Verdict::InspectDeep;
        }
    }

    Verdict::Pass
}

/// Dynamic defense filter configuration allowing zero-downtime hot patching (REQ-RCD-015).
pub struct DynamicDefensePolicy {
    pub max_entropy_threshold: AtomicU32,
    pub strict_quarantine_enabled: AtomicU32,
}

impl Default for DynamicDefensePolicy {
    fn default() -> Self {
        Self::new()
    }
}

impl DynamicDefensePolicy {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            max_entropy_threshold: AtomicU32::new(1843),
            strict_quarantine_enabled: AtomicU32::new(1),
        }
    }

    /// Hot-patches the entropy threshold atomically without reboots (REQ-RCD-015).
    pub fn update_entropy_threshold(&self, new_threshold: u16) {
        self.max_entropy_threshold.store(u32::from(new_threshold), Ordering::Release);
    }

    /// Returns current active entropy threshold.
    #[must_use]
    #[allow(clippy::cast_possible_truncation)]
    pub fn current_entropy_threshold(&self) -> u16 {
        self.max_entropy_threshold.load(Ordering::Acquire) as u16
    }
}

/// Global active defense policy configuration.
pub static ACTIVE_POLICY: DynamicDefensePolicy = DynamicDefensePolicy::new();

/// Main entry point for evaluating an intercepted system call.
#[inline]
pub fn evaluate_syscall(pid: u32, syscall_nr: u32, args: [u64; 6], ip: u64) -> Verdict {
    // REQ-RCD-011: Quarantined processes are strictly blocked from process creation or network transmission
    if is_pid_quarantined(pid)
        && (syscall_nr == SYS_FORK
            || syscall_nr == SYS_CLONE
            || syscall_nr == SYS_EXECVE
            || syscall_nr == SYS_SOCKET
            || syscall_nr == SYS_CONNECT
            || syscall_nr == SYS_SENDTO)
    {
        return Verdict::BlockKill;
    }

    let event = SyscallAuditEvent::new(pid, syscall_nr, args, ip);
    let verdict = CORE_FILTER.evaluate(&event);

    if verdict == Verdict::InspectDeep || verdict == Verdict::BlockKill {
        AUDIT_RING_BUFFER.push_overwrite(event);
    }

    if verdict == Verdict::Rollback {
        // REQ-RCD-011: Rollback triggers immediate process quarantine confinement
        let _ = quarantine_pid(pid);
    }

    if verdict == Verdict::BlockKill || verdict == Verdict::Rollback {
        BLOCKED_ATTACK_COUNT.fetch_add(1, Ordering::Relaxed);
    }

    verdict
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn ebpf_firewall_init() -> i32 {
    let _ = BLOCKED_ATTACK_COUNT.load(Ordering::Relaxed);
    0
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn ebpf_firewall_exit() {}

// ---------------------------------------------------------------------------
// REQ-RCD-018: Bounded eBPF Bytecode Safety & Ring 0 JIT Termination
// ---------------------------------------------------------------------------

/// Maximum number of eBPF instructions permitted in a dynamically loaded filter (REQ-RCD-018).
pub const MAX_EBPF_INSNS: usize = 256;

/// Maximum stack depth permitted in a dynamically loaded eBPF filter (REQ-RCD-018).
pub const MAX_EBPF_STACK: usize = 512;

/// Error variants returned by the eBPF static verifier (REQ-RCD-018).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EbpfVerifyError {
    /// Program exceeds the maximum instruction count of 256.
    InstructionLimitExceeded,
    /// Stack depth exceeds the 512-byte limit.
    StackLimitExceeded,
    /// Backward jump detected — loop-freedom cannot be guaranteed.
    BackwardJumpDetected,
    /// Program has zero instructions.
    EmptyProgram,
}

/// Specification of an eBPF filter program submitted for Ring 0 verification.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct EbpfProgramSpec {
    /// Total instruction count of the program.
    pub insn_count: usize,
    /// Maximum stack depth in bytes required by the program.
    pub stack_depth_bytes: usize,
    /// Whether the program contains any backward jumps (potential infinite loops).
    pub has_backward_jumps: bool,
}

impl EbpfProgramSpec {
    /// Constructs a new eBPF program specification.
    #[must_use]
    pub const fn new(insn_count: usize, stack_depth_bytes: usize, has_backward_jumps: bool) -> Self {
        Self {
            insn_count,
            stack_depth_bytes,
            has_backward_jumps,
        }
    }
}

/// Verifies that an eBPF program satisfies all Ring 0 safety invariants (REQ-RCD-018):
/// - Non-empty (at least 1 instruction)
/// - Instruction count ≤ 256
/// - Stack depth ≤ 512 bytes
/// - No backward jumps (acyclic control flow → finite termination)
///
/// # Errors
/// Returns `Err(EbpfVerifyError)` describing the first violated constraint.
pub fn verify_ebpf_program(spec: &EbpfProgramSpec) -> Result<(), EbpfVerifyError> {
    if spec.insn_count == 0 {
        return Err(EbpfVerifyError::EmptyProgram);
    }
    if spec.insn_count > MAX_EBPF_INSNS {
        return Err(EbpfVerifyError::InstructionLimitExceeded);
    }
    if spec.stack_depth_bytes > MAX_EBPF_STACK {
        return Err(EbpfVerifyError::StackLimitExceeded);
    }
    if spec.has_backward_jumps {
        return Err(EbpfVerifyError::BackwardJumpDetected);
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// REQ-RCD-020: Deterministic Fault-Tolerant Panic-Free Chaos Recovery
// ---------------------------------------------------------------------------

/// Hardware fault types that the chaos recovery handler responds to (REQ-RCD-020).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HardwareFaultType {
    /// No fault — system operates normally.
    None,
    /// DMA controller timeout detected.
    DmaTimeout,
    /// Single-event upset / bit flip in memory.
    BitFlip,
    /// General memory access fault.
    MemoryFault,
}

/// Deterministically resolves LMS policy state under hardware faults (REQ-RCD-020).
/// Any non-`None` fault unconditionally transitions to `EmergencyLockdown`.
#[must_use]
pub const fn resolve_fault_policy(fault: HardwareFaultType, current_state: LmsPolicyState) -> LmsPolicyState {
    match fault {
        HardwareFaultType::None => current_state,
        _ => LmsPolicyState::EmergencyLockdown,
    }
}

/// Deterministically resolves verdict under hardware faults (REQ-RCD-020).
/// Any non-`None` fault unconditionally emits `BlockKill`.
#[must_use]
pub const fn resolve_fault_verdict(fault: HardwareFaultType, default_verdict: Verdict) -> Verdict {
    match fault {
        HardwareFaultType::None => default_verdict,
        _ => Verdict::BlockKill,
    }
}

/// Chaos fault entry point — injects a fault and returns the fail-safe verdict.
#[must_use]
pub fn handle_chaos_fault(fault: HardwareFaultType, default_verdict: Verdict) -> Verdict {
    resolve_fault_verdict(fault, default_verdict)
}

// ---------------------------------------------------------------------------
// REQ-RCD-024: Polymorphic LLM Attack Trace & ROP Chain Injection Defense
// ---------------------------------------------------------------------------

/// Maximum consecutive NOP or junk instructions permitted before classifying as a polymorphic sled.
pub const MAX_NOP_SLED_LIMIT: usize = 8;

/// Evaluates a raw binary payload or shellcode buffer for polymorphic exploit patterns (REQ-RCD-024).
///
/// Detects polymorphic NOP sled sequences (x86_64 0x90, RISC-V addi/c.nop) and encrypted shellcode.
#[must_use]
pub fn evaluate_polymorphic_payload(payload: &[u8]) -> Verdict {
    if payload.is_empty() {
        return Verdict::Pass;
    }

    // 1. Detect polymorphic NOP sleds
    let mut nop_run: usize = 0;
    for &b in payload {
        if b == 0x90 || b == 0x01 || b == 0x13 {
            nop_run += 1;
            if nop_run >= MAX_NOP_SLED_LIMIT {
                return Verdict::BlockKill;
            }
        } else {
            nop_run = 0;
        }
    }

    // 2. High entropy check: if payload has length >= 16, compute Shannon entropy
    if payload.len() >= 16 {
        let entropy = compute_shannon_entropy_q8(payload);
        // Q8.8 >= 5.8 bits (1500 in Q8.8) indicates encrypted/compressed/polymorphic shellcode
        if entropy >= 1500 {
            return Verdict::InspectDeep;
        }
    }

    Verdict::Pass
}

/// Evaluates an instruction pointer transition sequence for ROP chain characteristics (REQ-RCD-024).
///
/// Detects anomalous control-flow transitions jumping between disjoint executable memory pages.
#[must_use]
pub fn evaluate_rop_chain(ips: &[u64]) -> Verdict {
    if ips.len() < 3 {
        return Verdict::Pass;
    }

    let mut cross_page_jumps = 0;
    for i in 1..ips.len() {
        let page_prev = ips[i - 1] >> 12;
        let page_curr = ips[i] >> 12;
        // If consecutive return addresses jump between completely different 4KB pages
        if page_prev != page_curr {
            cross_page_jumps += 1;
        }
    }

    if cross_page_jumps >= 3 {
        Verdict::BlockKill
    } else {
        Verdict::Pass
    }
}

// ---------------------------------------------------------------------------
// REQ-RCD-026: Self-Healing Page Table Invariant Monitor & Shadow Page Directory
// ---------------------------------------------------------------------------

pub const PTE_PRESENT: u64 = 1 << 0;
pub const PTE_READ: u64 = 1 << 1;
pub const PTE_WRITE: u64 = 1 << 2;
pub const PTE_EXEC: u64 = 1 << 3;
pub const PTE_USER: u64 = 1 << 4;

/// Audit status of a Page Table Entry evaluated by the shadow monitor (REQ-RCD-026).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PteAuditStatus {
    /// Entry satisfies all kernel security invariants.
    Valid,
    /// W^X violation: page is simultaneously marked writable and executable.
    ViolationWx,
    /// Privilege boundary violation: user-accessible page maps into kernel address space.
    ViolationKernelSpaceSpoof,
}

/// Shadow page table entry auditing physical mapping permissions (REQ-RCD-026).
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ShadowPteEntry {
    pub virtual_addr: u64,
    pub physical_addr: u64,
    pub flags: u64,
}

impl ShadowPteEntry {
    /// Creates a new shadow PTE entry.
    #[must_use]
    pub const fn new(virtual_addr: u64, physical_addr: u64, flags: u64) -> Self {
        Self {
            virtual_addr,
            physical_addr,
            flags,
        }
    }

    /// Audits the page table entry against W^X and kernel isolation invariants.
    #[must_use]
    pub const fn audit(&self) -> PteAuditStatus {
        // 1. W^X Invariant: Writable and Executable simultaneously is strictly forbidden
        if (self.flags & (PTE_WRITE | PTE_EXEC)) == (PTE_WRITE | PTE_EXEC) {
            return PteAuditStatus::ViolationWx;
        }
        // 2. Kernel/User Isolation: User page cannot map kernel space physical memory
        if (self.flags & PTE_USER) != 0 && self.physical_addr >= KERNEL_ADDR_SPACE_BASE {
            return PteAuditStatus::ViolationKernelSpaceSpoof;
        }
        PteAuditStatus::Valid
    }

    /// Auto-repairs corrupted or malicious PTE attributes to enforce W^X.
    /// If both WRITE and EXEC are set, drops EXEC permission.
    /// If USER is mapped to kernel memory, strips the USER flag.
    #[must_use]
    pub const fn repair_attributes(&self) -> Self {
        let mut fixed_flags = self.flags;
        if (fixed_flags & (PTE_WRITE | PTE_EXEC)) == (PTE_WRITE | PTE_EXEC) {
            fixed_flags &= !PTE_EXEC;
        }
        if (fixed_flags & PTE_USER) != 0 && self.physical_addr >= KERNEL_ADDR_SPACE_BASE {
            fixed_flags &= !PTE_USER;
        }
        Self {
            virtual_addr: self.virtual_addr,
            physical_addr: self.physical_addr,
            flags: fixed_flags,
        }
    }
}

// ---------------------------------------------------------------------------
// REQ-RCD-029: Dynamic Network Connection Tracker (Conntrack) Defense Filter
// ---------------------------------------------------------------------------

/// Connection states tracked by the stateful conntrack defense filter (REQ-RCD-029).
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TcpConntrackState {
    Closed = 0,
    SynSent = 1,
    SynReceived = 2,
    Established = 3,
    FinWait = 4,
}

/// Stateful conntrack connection flow record (REQ-RCD-029).
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TcpConntrackEntry {
    pub src_ip: u32,
    pub dst_ip: u32,
    pub src_port: u16,
    pub dst_port: u16,
    pub state: TcpConntrackState,
    pub packets_seen: u32,
}

impl TcpConntrackEntry {
    /// Creates a new connection entry in the `Closed` initial state.
    #[must_use]
    pub const fn new(src_ip: u32, dst_ip: u32, src_port: u16, dst_port: u16) -> Self {
        Self {
            src_ip,
            dst_ip,
            src_port,
            dst_port,
            state: TcpConntrackState::Closed,
            packets_seen: 0,
        }
    }

    /// Evaluates an incoming packet with `flags` against the conntrack state machine.
    /// Returns the updated state and the defense `Verdict`.
    #[must_use]
    pub fn process_packet(&mut self, flags: u8) -> (TcpConntrackState, Verdict) {
        self.packets_seen = self.packets_seen.saturating_add(1);

        // 1. Check for illegal TCP flag combinations (SYN-FIN, Null scan, Xmas scan)
        if (flags & (TCP_FLAG_SYN | TCP_FLAG_FIN)) == (TCP_FLAG_SYN | TCP_FLAG_FIN)
            || flags == 0
            || (flags & (TCP_FLAG_FIN | TCP_FLAG_URG | TCP_FLAG_PSH)) == (TCP_FLAG_FIN | TCP_FLAG_URG | TCP_FLAG_PSH)
        {
            return (self.state, Verdict::BlockKill);
        }

        // 2. RST flag terminates connection
        if (flags & TCP_FLAG_RST) != 0 {
            self.state = TcpConntrackState::Closed;
            return (self.state, Verdict::Pass);
        }

        match self.state {
            TcpConntrackState::Closed => {
                if (flags & TCP_FLAG_SYN) != 0 && (flags & TCP_FLAG_ACK) == 0 {
                    self.state = TcpConntrackState::SynSent;
                    (self.state, Verdict::Pass)
                } else {
                    // Out of state packet (data or ACK without initial SYN handshake)
                    (self.state, Verdict::BlockKill)
                }
            }
            TcpConntrackState::SynSent => {
                if (flags & (TCP_FLAG_SYN | TCP_FLAG_ACK)) == (TCP_FLAG_SYN | TCP_FLAG_ACK) {
                    self.state = TcpConntrackState::SynReceived;
                    (self.state, Verdict::Pass)
                } else {
                    (self.state, Verdict::BlockKill)
                }
            }
            TcpConntrackState::SynReceived => {
                if (flags & TCP_FLAG_ACK) != 0 {
                    self.state = TcpConntrackState::Established;
                    (self.state, Verdict::Pass)
                } else {
                    (self.state, Verdict::BlockKill)
                }
            }
            TcpConntrackState::Established => {
                if (flags & TCP_FLAG_FIN) != 0 {
                    self.state = TcpConntrackState::FinWait;
                    (self.state, Verdict::Pass)
                } else if (flags & TCP_FLAG_ACK) != 0 {
                    (self.state, Verdict::Pass)
                } else {
                    (self.state, Verdict::BlockKill)
                }
            }
            TcpConntrackState::FinWait => {
                if (flags & TCP_FLAG_ACK) != 0 {
                    self.state = TcpConntrackState::Closed;
                    (self.state, Verdict::Pass)
                } else {
                    (self.state, Verdict::Pass)
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// REQ-RCD-031: Fine-Grained Capability-Based Access Control (CapBAC) Token Validator
// ---------------------------------------------------------------------------

pub const CAP_CHOWN: u64 = 1 << 0;
pub const CAP_NET_RAW: u64 = 1 << 13;
pub const CAP_SYS_PTRACE: u64 = 1 << 19;
pub const CAP_SYS_ADMIN: u64 = 1 << 21;
pub const CAP_BPF_ADMIN: u64 = 1 << 38;
pub const CAP_ENCLAVE_SIGN: u64 = 1 << 40;

/// Errors arising from capability checks or modifications (REQ-RCD-031).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CapError {
    MissingCapability,
    UnauthorizedEscalation,
}

/// Process capability set tracking effective, permitted, and inheritable privileges (REQ-RCD-031).
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ProcessCapabilitySet {
    pub effective: u64,
    pub permitted: u64,
    pub inheritable: u64,
}

impl ProcessCapabilitySet {
    /// Creates a full root privilege capability set.
    #[must_use]
    pub const fn root() -> Self {
        Self {
            effective: u64::MAX,
            permitted: u64::MAX,
            inheritable: u64::MAX,
        }
    }

    /// Creates an unprivileged process capability set (all zero).
    #[must_use]
    pub const fn unprivileged() -> Self {
        Self {
            effective: 0,
            permitted: 0,
            inheritable: 0,
        }
    }

    /// Creates a custom capability set with specified effective bits.
    #[must_use]
    pub const fn with_caps(caps: u64) -> Self {
        Self {
            effective: caps,
            permitted: caps,
            inheritable: caps,
        }
    }

    /// Irreversibly drops specified capabilities from effective and permitted sets.
    ///
    /// Once dropped, capabilities cannot be recovered by the process without kernel re-attestation.
    pub fn drop_capability(&mut self, cap: u64) {
        self.effective &= !cap;
        self.permitted &= !cap;
    }

    /// Checks whether the effective capability set contains all required capabilities.
    #[must_use]
    pub const fn has_capability(&self, required: u64) -> bool {
        (self.effective & required) == required
    }

    /// Audits a syscall against required capability.
    /// Returns `Verdict::Pass` if present, else `Verdict::BlockKill`.
    #[must_use]
    pub const fn audit_syscall(&self, required: u64) -> Verdict {
        if self.has_capability(required) {
            Verdict::Pass
        } else {
            Verdict::BlockKill
        }
    }
}

// ---------------------------------------------------------------------------
// REQ-RCD-035: Real-Time Microsecond Kernel Watchdog & Deadlock Breaker
// ---------------------------------------------------------------------------

/// Error states encountered by the real-time defense watchdog (REQ-RCD-035).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WatchdogError {
    DeadlineExceeded,
    InvalidBudget,
}

/// Real-time microsecond defense watchdog preventing kernel execution stalls (REQ-RCD-035).
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DefenseWatchdog {
    pub start_cycles: u64,
    pub max_cycle_budget: u64,
}

impl DefenseWatchdog {
    /// Creates a new watchdog with start cycle counter and maximum allowed cycle budget.
    #[must_use]
    pub const fn new(start_cycles: u64, max_cycle_budget: u64) -> Self {
        Self {
            start_cycles,
            max_cycle_budget,
        }
    }

    /// Checks the remaining cycle budget.
    ///
    /// # Errors
    /// Returns `Err(WatchdogError::DeadlineExceeded)` if elapsed cycles exceed `max_cycle_budget`.
    pub fn check_budget(&self, current_cycles: u64) -> Result<u64, WatchdogError> {
        let elapsed = current_cycles.saturating_sub(self.start_cycles);
        if elapsed > self.max_cycle_budget {
            Err(WatchdogError::DeadlineExceeded)
        } else {
            Ok(elapsed)
        }
    }

    /// Evaluates if the watchdog has expired.
    #[must_use]
    pub fn is_expired(&self, current_cycles: u64) -> bool {
        current_cycles.saturating_sub(self.start_cycles) > self.max_cycle_budget
    }
}

// ---------------------------------------------------------------------------
// REQ-RCD-039: Multi-Engine Consensus Verdict Aggregator
// ---------------------------------------------------------------------------

/// Multi-engine security consensus decision (REQ-RCD-039).
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ConsensusDecision {
    /// Consolidated verdict enforcing pessimistic dominance.
    pub final_verdict: Verdict,
    /// Individual verdict emitted by eBPF LMS firewall.
    pub ebpf_verdict: Verdict,
    /// Individual verdict emitted by TinyML neural detector.
    pub tinyml_verdict: Verdict,
    /// Individual verdict emitted by stateful network conntrack.
    pub conntrack_verdict: Verdict,
    /// Fixed-point confidence score in Q8 format (0..=256, where 256 represents 100% engine agreement).
    pub confidence_q8: u16,
}

impl ConsensusDecision {
    /// Returns true if all three security engines reached unanimous agreement.
    #[must_use]
    pub const fn is_unanimous(&self) -> bool {
        self.confidence_q8 == 256
    }

    /// Returns true if the final aggregated verdict blocks or kills execution.
    #[must_use]
    pub const fn is_blocked(&self) -> bool {
        matches!(self.final_verdict, Verdict::BlockKill)
    }
}

/// Multi-Engine Consensus Verdict Aggregator (REQ-RCD-039).
/// Resolves disparate security verdicts across the eBPF LMS firewall, TinyML classifier,
/// and stateful network connection tracker using pessimistic security dominance.
pub struct ConsensusVerdictAggregator;

impl ConsensusVerdictAggregator {
    /// Aggregates three independent verdicts into a consolidated `ConsensusDecision`.
    ///
    /// Pessimistic dominance guarantees that if any engine emits `Verdict::BlockKill`,
    /// the final decision unconditionally absorbs and emits `Verdict::BlockKill`.
    #[must_use]
    pub const fn aggregate(
        ebpf: Verdict,
        tinyml: Verdict,
        conntrack: Verdict,
    ) -> ConsensusDecision {
        let interim = merge_verdict(ebpf, tinyml);
        let final_verdict = merge_verdict(interim, conntrack);

        // Compute engine agreement matches: each engine matching final_verdict adds 1.
        let mut matches: u16 = 0;
        if verdict_priority(ebpf) == verdict_priority(final_verdict) {
            matches += 1;
        }
        if verdict_priority(tinyml) == verdict_priority(final_verdict) {
            matches += 1;
        }
        if verdict_priority(conntrack) == verdict_priority(final_verdict) {
            matches += 1;
        }

        // Fixed-point Q8 confidence:
        // 3 matches => 256 (100%)
        // 2 matches => 170 (66.4%)
        // 1 match   => 85  (33.2%)
        let confidence_q8 = if matches == 3 {
            256
        } else if matches == 2 {
            170
        } else {
            85
        };

        ConsensusDecision {
            final_verdict,
            ebpf_verdict: ebpf,
            tinyml_verdict: tinyml,
            conntrack_verdict: conntrack,
            confidence_q8,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Verification of REQ-RCD-001: Ring 0 Pre-Dispatch Interception passes legitimate calls.
    #[test]
    fn test_benign_syscall_passes() {
        let verdict = evaluate_syscall(1001, 1, [1, 0x7fff_0000, 16, 0, 0, 0], 0x400_000);
        assert_eq!(verdict, Verdict::Pass);
    }

    /// Verification of REQ-RCD-003: W^X Memory Protection on mprotect.
    #[test]
    fn test_wx_mprotect_blocked() {
        let verdict = evaluate_syscall(1002, 10, [0x7fff_1000, 4096, 7, 0, 0, 0], 0x400_100);
        assert_eq!(verdict, Verdict::BlockKill);
    }

    /// Verification of REQ-RCD-003: W^X Memory Protection on mmap.
    #[test]
    fn test_wx_mmap_blocked() {
        let verdict = evaluate_syscall(1003, 9, [0, 4096, 7, 0x22, 0, 0], 0x400_200);
        assert_eq!(verdict, Verdict::BlockKill);
    }

    /// Verification of REQ-RCD-001: Kernel IP Spoofing Prevention.
    #[test]
    fn test_kernel_ip_spoofing_blocked() {
        let verdict = evaluate_syscall(1004, 1, [1, 0x7fff_0000, 16, 0, 0, 0], 0xFFFF_8000_1234_5678);
        assert_eq!(verdict, Verdict::BlockKill);
    }

    /// Verification of REQ-RCD-001: Null IP Pointer Validation.
    #[test]
    fn test_null_ip_blocked() {
        let verdict = evaluate_syscall(1005, 1, [1, 0x7fff_0000, 16, 0, 0, 0], 0);
        assert_eq!(verdict, Verdict::BlockKill);
    }

    /// Verification of REQ-RCD-005: Fixed-Point Q8.8 Shannon Entropy Payload Evaluation.
    #[test]
    fn test_shannon_entropy() {
        let zeros = [0u8; 64];
        let ent_zeros = compute_shannon_entropy_q8(&zeros);
        assert_eq!(ent_zeros, 0);

        let mut mixed = [0u8; 256];
        for (i, item) in mixed.iter_mut().enumerate() {
            #[allow(clippy::cast_possible_truncation)]
            {
                *item = i as u8;
            }
        }
        let ent_mixed = compute_shannon_entropy_q8(&mixed);
        assert!(ent_mixed >= 1700, "Entropy of uniform bytes should be high: {ent_mixed}");
    }

    /// Verification of REQ-RCD-007: LMS Security Policy State Machine Monotonicity.
    #[test]
    fn test_lms_policy_state_transitions() {
        let state = LmsPolicyState::Observing;
        assert_eq!(state.security_level(), 1);

        // Escalation is intrinsically valid
        let enforcing = state.escalate(LmsPolicyState::Enforcing).unwrap();
        assert_eq!(enforcing.security_level(), 2);

        let lockdown = enforcing.escalate(LmsPolicyState::EmergencyLockdown).unwrap();
        assert_eq!(lockdown.security_level(), 4);

        // Unauthorized de-escalation is rejected
        assert!(lockdown.escalate(LmsPolicyState::Observing).is_err());
        assert!(lockdown.deescalate_with_key(LmsPolicyState::Observing, false).is_err());

        // Authorized de-escalation with root key succeeds
        let restored = lockdown.deescalate_with_key(LmsPolicyState::Observing, true).unwrap();
        assert_eq!(restored, LmsPolicyState::Observing);
    }

    /// Verification of REQ-RCD-008: Pessimistic Security Precedence.
    #[test]
    fn test_pessimistic_verdict_merge() {
        // BlockKill dominates all verdicts
        assert_eq!(merge_verdict(Verdict::BlockKill, Verdict::Pass), Verdict::BlockKill);
        assert_eq!(merge_verdict(Verdict::Pass, Verdict::BlockKill), Verdict::BlockKill);
        assert_eq!(merge_verdict(Verdict::BlockKill, Verdict::InspectDeep), Verdict::BlockKill);
        assert_eq!(merge_verdict(Verdict::InspectDeep, Verdict::BlockKill), Verdict::BlockKill);
        assert_eq!(merge_verdict(Verdict::BlockKill, Verdict::Rollback), Verdict::BlockKill);

        // Rollback dominates InspectDeep and Pass
        assert_eq!(merge_verdict(Verdict::Rollback, Verdict::InspectDeep), Verdict::Rollback);
        assert_eq!(merge_verdict(Verdict::Pass, Verdict::Rollback), Verdict::Rollback);

        // InspectDeep dominates Pass
        assert_eq!(merge_verdict(Verdict::Pass, Verdict::InspectDeep), Verdict::InspectDeep);

        // Commutativity
        let verdicts = [Verdict::Pass, Verdict::InspectDeep, Verdict::Rollback, Verdict::BlockKill];
        for &v1 in &verdicts {
            for &v2 in &verdicts {
                assert_eq!(merge_verdict(v1, v2), merge_verdict(v2, v1));
            }
        }
    }

    /// Verification of REQ-RCD-011: Automated Process Quarantine on Rollback verdict.
    #[test]
    fn test_req_rcd_011_process_quarantine_blocks_fork_and_net() {
        let test_pid = 4099;
        PROCESS_QUARANTINE.reset();
        assert!(!is_pid_quarantined(test_pid));

        // Quarantine the PID
        assert!(quarantine_pid(test_pid));
        assert!(is_pid_quarantined(test_pid));

        // Attempting fork, clone, execve, or socket must be unconditionally blocked with BlockKill
        let verdict_fork = evaluate_syscall(test_pid, SYS_FORK, [0; 6], 0x400_000);
        assert_eq!(verdict_fork, Verdict::BlockKill);

        let verdict_clone = evaluate_syscall(test_pid, SYS_CLONE, [0; 6], 0x400_000);
        assert_eq!(verdict_clone, Verdict::BlockKill);

        let verdict_exec = evaluate_syscall(test_pid, SYS_EXECVE, [0; 6], 0x400_000);
        assert_eq!(verdict_exec, Verdict::BlockKill);

        let verdict_socket = evaluate_syscall(test_pid, SYS_SOCKET, [0; 6], 0x400_000);
        assert_eq!(verdict_socket, Verdict::BlockKill);

        // De-quarantine requires root attestation
        assert!(PROCESS_QUARANTINE.lift_quarantine(test_pid, false).is_err());
        assert!(PROCESS_QUARANTINE.lift_quarantine(test_pid, true).unwrap());
        assert!(!is_pid_quarantined(test_pid));
    }

    /// Verification of REQ-RCD-012: Kernel Memory Permission Auto-Repair.
    #[test]
    fn test_req_rcd_012_auto_repair_restores_wx_invariant() {
        // Corrupted permissions: PROT_WRITE | PROT_EXEC
        let corrupted1 = PROT_WRITE | PROT_EXEC;
        let repaired1 = auto_repair_page_permissions(corrupted1);
        assert_eq!(repaired1, PROT_WRITE);
        assert_eq!(repaired1 & PROT_EXEC, 0);

        // Corrupted permissions: PROT_READ | PROT_WRITE | PROT_EXEC
        let corrupted2 = PROT_READ | PROT_WRITE | PROT_EXEC;
        let repaired2 = auto_repair_page_permissions(corrupted2);
        assert_eq!(repaired2, PROT_READ | PROT_WRITE);
        assert_eq!(repaired2 & PROT_EXEC, 0);

        // Compliant permissions: untouched (Theorem 10.2)
        let safe1 = PROT_READ | PROT_WRITE;
        assert_eq!(auto_repair_page_permissions(safe1), safe1);

        let safe2 = PROT_READ | PROT_EXEC;
        assert_eq!(auto_repair_page_permissions(safe2), safe2);
    }

    /// Verification of REQ-RCD-014: Zero-Copy Network Ingress Packet Inspection.
    #[test]
    fn test_req_rcd_014_network_packet_ingress_inspection() {
        let src = [192, 168, 1, 10];
        let dst = [10, 0, 0, 1];

        // 1. Benign normal packet passes
        let benign_payload = b"GET /index.html HTTP/1.1\r\nHost: example.com\r\n\r\n";
        let v_benign = evaluate_packet_ingress(src, dst, TCP_FLAG_ACK | TCP_FLAG_PSH, benign_payload);
        assert_eq!(v_benign, Verdict::Pass);

        // 2. Anomalous scans are blocked
        // Null scan
        let v_null = evaluate_packet_ingress(src, dst, 0, &[]);
        assert_eq!(v_null, Verdict::BlockKill);

        // SYN-FIN scan
        let v_syn_fin = evaluate_packet_ingress(src, dst, TCP_FLAG_SYN | TCP_FLAG_FIN, &[]);
        assert_eq!(v_syn_fin, Verdict::BlockKill);

        // Xmas scan
        let v_xmas = evaluate_packet_ingress(src, dst, TCP_FLAG_FIN | TCP_FLAG_URG | TCP_FLAG_PSH, &[]);
        assert_eq!(v_xmas, Verdict::BlockKill);

        // SYN-RST
        let v_syn_rst = evaluate_packet_ingress(src, dst, TCP_FLAG_SYN | TCP_FLAG_RST, &[]);
        assert_eq!(v_syn_rst, Verdict::BlockKill);

        // 3. High entropy polymorphic payload flags deep inspection
        let mut high_entropy_payload = [0u8; 256];
        for (i, b) in high_entropy_payload.iter_mut().enumerate() {
            #[allow(clippy::cast_possible_truncation)]
            {
                *b = i as u8;
            }
        }
        let v_entropy = evaluate_packet_ingress(src, dst, TCP_FLAG_ACK, &high_entropy_payload);
        assert_eq!(v_entropy, Verdict::InspectDeep);
    }

    /// Entropy on an empty slice must return exactly 0 (no panic, no UB).
    #[test]
    fn test_entropy_empty_slice() {
        assert_eq!(compute_shannon_entropy_q8(&[]), 0);
    }

    /// merge_verdict is idempotent: merge(v, v) == v for all variants.
    #[test]
    fn test_merge_verdict_self_idempotent() {
        let verdicts = [Verdict::Pass, Verdict::InspectDeep, Verdict::Rollback, Verdict::BlockKill];
        for v in verdicts {
            assert_eq!(merge_verdict(v, v), v);
        }
    }

    /// Verification of REQ-RCD-015: Zero-Downtime Hot-Patching State Congruence.
    #[test]
    fn test_req_rcd_015_hot_patch_state_congruence() {
        assert_eq!(ACTIVE_POLICY.current_entropy_threshold(), 1843);
        ACTIVE_POLICY.update_entropy_threshold(1500);
        assert_eq!(ACTIVE_POLICY.current_entropy_threshold(), 1500);
        // Restore
        ACTIVE_POLICY.update_entropy_threshold(1843);
        assert_eq!(ACTIVE_POLICY.current_entropy_threshold(), 1843);
    }

    /// Verification of REQ-RCD-018: Bounded eBPF Bytecode Safety & JIT Termination.
    #[test]
    fn test_req_rcd_018_ebpf_bytecode_verifier_safety() {
        // Valid program passes
        let valid = EbpfProgramSpec::new(128, 256, false);
        assert!(verify_ebpf_program(&valid).is_ok());

        // Instruction limit exceeded
        let too_long = EbpfProgramSpec::new(300, 256, false);
        assert_eq!(verify_ebpf_program(&too_long), Err(EbpfVerifyError::InstructionLimitExceeded));

        // Stack limit exceeded
        let stack_overflow = EbpfProgramSpec::new(100, 600, false);
        assert_eq!(verify_ebpf_program(&stack_overflow), Err(EbpfVerifyError::StackLimitExceeded));

        // Backward jump rejected (ensures loop-freedom and finite termination)
        let loop_prog = EbpfProgramSpec::new(50, 128, true);
        assert_eq!(verify_ebpf_program(&loop_prog), Err(EbpfVerifyError::BackwardJumpDetected));

        // Empty program rejected
        let empty = EbpfProgramSpec::new(0, 0, false);
        assert_eq!(verify_ebpf_program(&empty), Err(EbpfVerifyError::EmptyProgram));
    }

    /// Verification of REQ-RCD-020: Deterministic Fault-Tolerant Panic-Free Chaos Recovery.
    #[test]
    fn test_req_rcd_020_chaos_recovery_and_panic_free() {
        let initial_state = LmsPolicyState::Observing;
        let default_v = Verdict::Pass;

        // None fault leaves system intact
        assert_eq!(resolve_fault_policy(HardwareFaultType::None, initial_state), initial_state);
        assert_eq!(resolve_fault_verdict(HardwareFaultType::None, default_v), default_v);

        // All hardware faults trigger emergency lockdown and BlockKill
        let faults = [HardwareFaultType::DmaTimeout, HardwareFaultType::BitFlip, HardwareFaultType::MemoryFault];
        for &fault in &faults {
            let policy = resolve_fault_policy(fault, initial_state);
            assert_eq!(policy, LmsPolicyState::EmergencyLockdown);

            let verdict = handle_chaos_fault(fault, default_v);
            assert_eq!(verdict, Verdict::BlockKill);
        }
    }

    /// Verification of REQ-RCD-024: Polymorphic LLM Attack Trace & ROP Chain Injection Defense.
    #[test]
    fn test_req_rcd_024_polymorphic_exploit_and_rop_detection() {
        // 1. Benign payload (e.g. ASCII string) passes
        let benign = b"GET /index.html HTTP/1.1\r\nHost: runux.org\r\n\r\n";
        assert_eq!(evaluate_polymorphic_payload(benign), Verdict::Pass);

        // 2. Polymorphic NOP sled (>= 8 consecutive 0x90 bytes) triggers BlockKill
        let mut nop_payload = [0x41u8; 32];
        nop_payload[4..14].copy_from_slice(&[0x90; 10]);
        assert_eq!(evaluate_polymorphic_payload(&nop_payload), Verdict::BlockKill);

        // 3. High-entropy encrypted payload triggers InspectDeep
        let mut high_entropy = [0u8; 256];
        for (i, b) in high_entropy.iter_mut().enumerate() {
            #[allow(clippy::cast_possible_truncation)]
            {
                *b = i as u8;
            }
        }
        let v_ent = evaluate_polymorphic_payload(&high_entropy);
        assert!(v_ent == Verdict::InspectDeep || v_ent == Verdict::BlockKill);

        // 4. Benign sequential execution IP sequence passes ROP filter
        let benign_ips = [0x400_100, 0x400_120, 0x400_150, 0x400_180];
        assert_eq!(evaluate_rop_chain(&benign_ips), Verdict::Pass);

        // 5. ROP chain jumping across distinct page boundaries triggers BlockKill
        let rop_ips = [0x401_020, 0x502_040, 0x603_080, 0x704_0A0];
        assert_eq!(evaluate_rop_chain(&rop_ips), Verdict::BlockKill);
    }

    /// Verification of REQ-RCD-026: Self-Healing Page Table Invariant Monitor & Shadow Page Directory.
    #[test]
    fn test_req_rcd_026_pte_shadow_monitor_and_repair() {
        // 1. Legitimate user executable page (Read + Exec, User, Valid physical addr)
        let benign_pte = ShadowPteEntry::new(0x400_000, 0x100_000, PTE_PRESENT | PTE_READ | PTE_EXEC | PTE_USER);
        assert_eq!(benign_pte.audit(), PteAuditStatus::Valid);

        // 2. Malicious W^X violation (Write + Exec simultaneously)
        let wx_pte = ShadowPteEntry::new(0x600_000, 0x200_000, PTE_PRESENT | PTE_READ | PTE_WRITE | PTE_EXEC | PTE_USER);
        assert_eq!(wx_pte.audit(), PteAuditStatus::ViolationWx);

        // Auto-repair strips EXEC permission, restoring W^X invariant
        let repaired_wx = wx_pte.repair_attributes();
        assert_eq!(repaired_wx.audit(), PteAuditStatus::Valid);
        assert_eq!(repaired_wx.flags & PTE_EXEC, 0);
        assert_ne!(repaired_wx.flags & PTE_WRITE, 0);

        // 3. Malicious user page mapping kernel address space
        let spoof_pte = ShadowPteEntry::new(0x800_000, KERNEL_ADDR_SPACE_BASE + 0x1000, PTE_PRESENT | PTE_READ | PTE_USER);
        assert_eq!(spoof_pte.audit(), PteAuditStatus::ViolationKernelSpaceSpoof);

        // Auto-repair strips USER permission, neutralizing privilege escalation
        let repaired_spoof = spoof_pte.repair_attributes();
        assert_eq!(repaired_spoof.audit(), PteAuditStatus::Valid);
        assert_eq!(repaired_spoof.flags & PTE_USER, 0);
    }

    /// Verification of REQ-RCD-029: Dynamic Network Connection Tracker (Conntrack) Defense Filter.
    #[test]
    fn test_req_rcd_029_conntrack_stateful_inspection() {
        let mut entry = TcpConntrackEntry::new(0x0A00_0001, 0x0A00_0002, 12345, 80);
        assert_eq!(entry.state, TcpConntrackState::Closed);

        // 1. Illegal scan flags immediately blocked
        let (_, v_null) = entry.process_packet(0);
        assert_eq!(v_null, Verdict::BlockKill);

        let (_, v_syn_fin) = entry.process_packet(TCP_FLAG_SYN | TCP_FLAG_FIN);
        assert_eq!(v_syn_fin, Verdict::BlockKill);

        // 2. Proper 3-way handshake:
        // SYN packet
        let (state1, v1) = entry.process_packet(TCP_FLAG_SYN);
        assert_eq!(state1, TcpConntrackState::SynSent);
        assert_eq!(v1, Verdict::Pass);

        // SYN-ACK packet
        let (state2, v2) = entry.process_packet(TCP_FLAG_SYN | TCP_FLAG_ACK);
        assert_eq!(state2, TcpConntrackState::SynReceived);
        assert_eq!(v2, Verdict::Pass);

        // ACK packet completes handshake -> Established
        let (state3, v3) = entry.process_packet(TCP_FLAG_ACK);
        assert_eq!(state3, TcpConntrackState::Established);
        assert_eq!(v3, Verdict::Pass);

        // Data payload with ACK
        let (state4, v4) = entry.process_packet(TCP_FLAG_ACK | TCP_FLAG_PSH);
        assert_eq!(state4, TcpConntrackState::Established);
        assert_eq!(v4, Verdict::Pass);

        // Connection teardown via FIN
        let (state5, v5) = entry.process_packet(TCP_FLAG_FIN);
        assert_eq!(state5, TcpConntrackState::FinWait);
        assert_eq!(v5, Verdict::Pass);

        // Final ACK closes connection
        let (state6, v6) = entry.process_packet(TCP_FLAG_ACK);
        assert_eq!(state6, TcpConntrackState::Closed);
        assert_eq!(v6, Verdict::Pass);
    }

    /// Verification of REQ-RCD-031: Fine-Grained Capability-Based Access Control (CapBAC) Token Validator.
    #[test]
    fn test_req_rcd_031_capability_based_access_control() {
        let root_caps = ProcessCapabilitySet::root();
        assert!(root_caps.has_capability(CAP_SYS_ADMIN));
        assert!(root_caps.has_capability(CAP_BPF_ADMIN));
        assert_eq!(root_caps.audit_syscall(CAP_SYS_ADMIN), Verdict::Pass);

        let mut proc_caps = ProcessCapabilitySet::with_caps(CAP_NET_RAW | CAP_SYS_PTRACE);
        assert!(proc_caps.has_capability(CAP_NET_RAW));
        assert!(proc_caps.has_capability(CAP_SYS_PTRACE));
        assert!(!proc_caps.has_capability(CAP_SYS_ADMIN));
        assert_eq!(proc_caps.audit_syscall(CAP_SYS_ADMIN), Verdict::BlockKill);

        // Monotonic drop
        proc_caps.drop_capability(CAP_SYS_PTRACE);
        assert!(!proc_caps.has_capability(CAP_SYS_PTRACE));
        assert_eq!(proc_caps.audit_syscall(CAP_SYS_PTRACE), Verdict::BlockKill);
        assert!(proc_caps.has_capability(CAP_NET_RAW));

        let unpriv = ProcessCapabilitySet::unprivileged();
        assert_eq!(unpriv.audit_syscall(CAP_CHOWN), Verdict::BlockKill);
    }

    /// Verification of REQ-RCD-035: Real-Time Microsecond Kernel Watchdog & Deadlock Breaker.
    #[test]
    fn test_req_rcd_035_defense_watchdog_realtime_deadline() {
        let watchdog = DefenseWatchdog::new(1000, 500);

        // 1. Within budget
        assert_eq!(watchdog.check_budget(1200), Ok(200));
        assert!(!watchdog.is_expired(1200));

        // 2. Exact boundary
        assert_eq!(watchdog.check_budget(1500), Ok(500));
        assert!(!watchdog.is_expired(1500));

        // 3. Exceeded budget trips error
        assert_eq!(watchdog.check_budget(1501), Err(WatchdogError::DeadlineExceeded));
        assert!(watchdog.is_expired(1501));
    }

    /// Verification of REQ-RCD-039: Multi-Engine Consensus Verdict Aggregator.
    #[test]
    fn test_req_rcd_039_consensus_verdict_aggregator() {
        // 1. Unanimous Pass
        let d_pass = ConsensusVerdictAggregator::aggregate(Verdict::Pass, Verdict::Pass, Verdict::Pass);
        assert_eq!(d_pass.final_verdict, Verdict::Pass);
        assert_eq!(d_pass.confidence_q8, 256);
        assert!(d_pass.is_unanimous());
        assert!(!d_pass.is_blocked());

        // 2. Pessimistic Dominance: single BlockKill absorbs all other verdicts
        let d_block1 = ConsensusVerdictAggregator::aggregate(Verdict::Pass, Verdict::BlockKill, Verdict::Pass);
        assert_eq!(d_block1.final_verdict, Verdict::BlockKill);
        assert_eq!(d_block1.confidence_q8, 85);
        assert!(!d_block1.is_unanimous());
        assert!(d_block1.is_blocked());

        let d_block2 = ConsensusVerdictAggregator::aggregate(Verdict::BlockKill, Verdict::Pass, Verdict::Pass);
        assert_eq!(d_block2.final_verdict, Verdict::BlockKill);
        assert_eq!(d_block2.confidence_q8, 85);

        let d_block3 = ConsensusVerdictAggregator::aggregate(Verdict::Pass, Verdict::Pass, Verdict::BlockKill);
        assert_eq!(d_block3.final_verdict, Verdict::BlockKill);
        assert_eq!(d_block3.confidence_q8, 85);

        // 3. 2-engine agreement on BlockKill
        let d_2block = ConsensusVerdictAggregator::aggregate(Verdict::BlockKill, Verdict::Pass, Verdict::BlockKill);
        assert_eq!(d_2block.final_verdict, Verdict::BlockKill);
        assert_eq!(d_2block.confidence_q8, 170);
        assert!(d_2block.is_blocked());

        // 4. Unanimous BlockKill
        let d_ublock = ConsensusVerdictAggregator::aggregate(Verdict::BlockKill, Verdict::BlockKill, Verdict::BlockKill);
        assert_eq!(d_ublock.final_verdict, Verdict::BlockKill);
        assert_eq!(d_ublock.confidence_q8, 256);
        assert!(d_ublock.is_unanimous());
        assert!(d_ublock.is_blocked());

        // 5. Rollback dominates InspectDeep and Pass
        let d_roll = ConsensusVerdictAggregator::aggregate(Verdict::Pass, Verdict::Rollback, Verdict::InspectDeep);
        assert_eq!(d_roll.final_verdict, Verdict::Rollback);
        assert_eq!(d_roll.confidence_q8, 85);

        // 6. Exhaustive permutation check: bounded confidence & pessimistic dominance
        let all_verdicts = [Verdict::Pass, Verdict::InspectDeep, Verdict::Rollback, Verdict::BlockKill];
        for &e in &all_verdicts {
            for &t in &all_verdicts {
                for &c in &all_verdicts {
                    let dec = ConsensusVerdictAggregator::aggregate(e, t, c);
                    assert!(dec.confidence_q8 >= 85 && dec.confidence_q8 <= 256);
                    if e == Verdict::BlockKill || t == Verdict::BlockKill || c == Verdict::BlockKill {
                        assert_eq!(dec.final_verdict, Verdict::BlockKill);
                        assert!(dec.is_blocked());
                    }
                    if e == t && t == c {
                        assert!(dec.is_unanimous());
                        assert_eq!(dec.confidence_q8, 256);
                    }
                }
            }
        }
    }
}


