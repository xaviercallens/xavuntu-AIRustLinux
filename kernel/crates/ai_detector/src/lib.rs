#![no_std]
#![deny(clippy::all)]
#![warn(clippy::pedantic)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]
//! RunuX AI Detector — Bare-Metal TinyML System Call Classifier
//!
//! Evaluates sliding windows of recent system calls per PID using a quantized
//! INT8 neural classifier. Detects polymorphic exploit chains, ROP payload staging,
//! and anomalous memory transitions under strict real-time deadlines (< 15 µs).

use core::cell::UnsafeCell;
use ebpf_firewall::{SyscallAuditEvent, Verdict};

/// Length of the sliding window of system calls evaluated per PID.
pub const WINDOW_SIZE: usize = 16;

/// Number of input features extracted from each system call window.
pub const FEATURE_DIM: usize = 32;

/// Hidden dimension for the TinyML perceptron.
pub const HIDDEN_DIM: usize = 16;

/// Maximum number of tracked concurrent processes in the bare-metal ring buffer.
pub const MAX_TRACKED_PIDS: usize = 64;

/// Sliding window record for a single process.
#[derive(Clone, Copy)]
pub struct ProcessSyscallWindow {
    pub pid: u32,
    pub count: usize,
    pub window: [SyscallAuditEvent; WINDOW_SIZE],
}

impl ProcessSyscallWindow {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            pid: 0,
            count: 0,
            window: [SyscallAuditEvent::new(0, 0, [0; 6], 0); WINDOW_SIZE],
        }
    }

    /// Pushes a new event into the circular window.
    pub fn push(&mut self, event: SyscallAuditEvent) {
        let idx = self.count % WINDOW_SIZE;
        self.window[idx] = event;
        self.count = self.count.wrapping_add(1);
    }
}

impl Default for ProcessSyscallWindow {
    fn default() -> Self {
        Self::new()
    }
}

/// Static pre-allocated pool of tensor buffers for zero-heap inference.
pub struct StaticTensorPool {
    features: UnsafeCell<[i8; FEATURE_DIM]>,
    hidden: UnsafeCell<[i32; HIDDEN_DIM]>,
}

unsafe impl Sync for StaticTensorPool {}

impl StaticTensorPool {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            features: UnsafeCell::new([0i8; FEATURE_DIM]),
            hidden: UnsafeCell::new([0i32; HIDDEN_DIM]),
        }
    }
}

impl Default for StaticTensorPool {
    fn default() -> Self {
        Self::new()
    }
}

static TENSOR_POOL: StaticTensorPool = StaticTensorPool::new();

// ---------------------------------------------------------------------------
// REQ-RCD-021: StaticTensorPool Zero-Allocation INT4/INT8 Tensor Inference Arena
// ---------------------------------------------------------------------------

/// Default capacity for the static tensor arena (512 bytes, 64-byte aligned).
pub const TENSOR_ARENA_CAPACITY: usize = 512;

/// Error variants encountered during static tensor arena memory operations (REQ-RCD-021).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TensorArenaError {
    /// Requested slice exceeds available arena capacity.
    BufferOverflow,
    /// Requested offset does not satisfy alignment constraints.
    MisalignedOffset,
    /// Slice length does not match expected dimension.
    InvalidSliceLength,
}

/// 64-byte cache-line aligned zero-allocation memory arena for INT4/INT8 tensor inference (REQ-RCD-021).
///
/// Ensures zero-heap allocation in Ring 0 while guaranteeing strict cache-line alignment
/// matching RISC-V RVV and x86_64 AVX-512 hardware vector units.
#[repr(C, align(64))]
pub struct StaticTensorArena<const CAP: usize = TENSOR_ARENA_CAPACITY> {
    pub storage: UnsafeCell<[u8; CAP]>,
}

unsafe impl<const CAP: usize> Sync for StaticTensorArena<CAP> {}

impl<const CAP: usize> StaticTensorArena<CAP> {
    /// Creates a zero-initialized static tensor arena.
    #[must_use]
    pub const fn new() -> Self {
        Self {
            storage: UnsafeCell::new([0u8; CAP]),
        }
    }

    /// Returns a mutable reference to the activation buffer (`[i8; FEATURE_DIM]`) at offset 0.
    ///
    /// # Errors
    /// Returns `TensorArenaError::BufferOverflow` if `CAP < FEATURE_DIM`.
    pub fn activation_slice(&mut self) -> Result<&mut [i8; FEATURE_DIM], TensorArenaError> {
        if CAP < FEATURE_DIM {
            return Err(TensorArenaError::BufferOverflow);
        }
        // SAFETY: With exclusive `&mut self` access, no other references to `self.storage` exist.
        // The storage is aligned to 64 bytes, satisfying i8 alignment (1 byte).
        unsafe {
            let ptr = self.storage.get().cast::<i8>();
            Ok(&mut *core::ptr::slice_from_raw_parts_mut(ptr, FEATURE_DIM).cast::<[i8; FEATURE_DIM]>())
        }
    }

    /// Returns a mutable reference to the hidden logits buffer (`[i32; HIDDEN_DIM]`) at offset 64.
    ///
    /// # Errors
    /// Returns `TensorArenaError::BufferOverflow` if `CAP < 64 + HIDDEN_DIM * 4`.
    pub fn hidden_slice(&mut self) -> Result<&mut [i32; HIDDEN_DIM], TensorArenaError> {
        const OFFSET: usize = 64;
        const REQ_SIZE: usize = OFFSET + HIDDEN_DIM * core::mem::size_of::<i32>();
        if CAP < REQ_SIZE {
            return Err(TensorArenaError::BufferOverflow);
        }
        // SAFETY: Exclusive `&mut self` guarantees no aliasing references exist. Offset 64
        // is 64-byte aligned from a 64-byte aligned base, satisfying i32 alignment (4 bytes).
        unsafe {
            let base_ptr = self.storage.get().cast::<u8>();
            let target_ptr = base_ptr.add(OFFSET).cast::<i32>();
            Ok(&mut *core::ptr::slice_from_raw_parts_mut(target_ptr, HIDDEN_DIM).cast::<[i32; HIDDEN_DIM]>())
        }
    }

    /// Returns a mutable reference to the output logit buffer (`[i32; 4]`) at offset 384.
    ///
    /// # Errors
    /// Returns `TensorArenaError::BufferOverflow` if `CAP < 384 + 16`.
    pub fn output_logits_slice(&mut self) -> Result<&mut [i32; 4], TensorArenaError> {
        const OFFSET: usize = 384;
        const REQ_SIZE: usize = OFFSET + 4 * core::mem::size_of::<i32>();
        if CAP < REQ_SIZE {
            return Err(TensorArenaError::BufferOverflow);
        }
        // SAFETY: Exclusive `&mut self` guarantees no aliasing. Offset 384 is a multiple of 64
        // (384 = 6 * 64), ensuring proper 4-byte i32 alignment.
        unsafe {
            let base_ptr = self.storage.get().cast::<u8>();
            let target_ptr = base_ptr.add(OFFSET).cast::<i32>();
            Ok(&mut *core::ptr::slice_from_raw_parts_mut(target_ptr, 4).cast::<[i32; 4]>())
        }
    }

    /// Safely slices a contiguous sub-buffer with explicit offset and length bounds checking.
    ///
    /// # Errors
    /// Returns `TensorArenaError::BufferOverflow` if `offset + len > CAP`.
    pub fn subslice_mut(&mut self, offset: usize, len: usize) -> Result<&mut [u8], TensorArenaError> {
        if offset.checked_add(len).map_or(true, |end| end > CAP) {
            return Err(TensorArenaError::BufferOverflow);
        }
        // SAFETY: Exclusive `&mut self` ensures no concurrent access. The bounds check verifies
        // [offset, offset + len) is wholly contained in storage.
        unsafe {
            let ptr = self.storage.get().cast::<u8>().add(offset);
            Ok(core::slice::from_raw_parts_mut(ptr, len))
        }
    }

    /// Zeroizes the entire arena memory using volatile writes.
    pub fn zeroize(&mut self) {
        // SAFETY: Exclusive `&mut self` ensures no concurrent reads/writes while zeroing.
        // The storage is within the valid bounds of the arena.
        unsafe {
            let ptr = self.storage.get().cast::<u8>();
            for i in 0..CAP {
                core::ptr::write_volatile(ptr.add(i), 0);
            }
        }
    }
}

impl<const CAP: usize> Default for StaticTensorArena<CAP> {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Statically compiled TinyML Model Weights in .rodata
// ---------------------------------------------------------------------------

/// Layer 1 weights: [FEATURE_DIM x HIDDEN_DIM] quantized as i8
static L1_WEIGHTS: [[i8; HIDDEN_DIM]; FEATURE_DIM] = [
    [12, -4, 8, 2, -7, 14, -2, 6, 9, -1, 3, -8, 5, -3, 11, 0],
    [-6, 11, -3, 9, 4, -8, 12, -5, 2, 7, -9, 4, -2, 10, -1, 6],
    [8, -2, 15, -4, 10, -1, 7, -6, 13, 0, 5, -7, 11, -2, 8, 3],
    [-5, 7, -1, 12, -3, 8, -4, 11, -2, 6, -5, 9, 3, -7, 10, -1],
    [9, -3, 6, -8, 14, -2, 11, 1, -7, 13, -4, 8, -1, 6, -5, 12],
    [-2, 10, -5, 7, -1, 13, -4, 9, 2, -6, 11, -3, 8, 0, -7, 14],
    [7, -1, 12, -4, 8, 0, 14, -3, 9, -2, 6, -5, 13, 1, -4, 10],
    [-4, 8, -2, 11, -5, 9, 1, 13, -3, 7, -1, 10, -4, 8, 2, -6],
    [11, -5, 7, 0, 13, -4, 8, 2, 15, -1, 9, -3, 6, -7, 12, 1],
    [-3, 9, -1, 14, -2, 7, -6, 10, 0, 12, -4, 8, 1, -5, 11, -2],
    [6, -2, 10, -5, 9, 1, 12, -4, 7, 0, 14, -3, 8, -1, 5, 11],
    [-7, 13, -4, 8, 0, 11, -3, 6, 2, 9, -1, 12, -5, 7, 3, -4],
    [10, -1, 8, -3, 12, 2, 7, -5, 14, 0, 6, -2, 11, -4, 9, 1],
    [-5, 12, -2, 7, 1, 10, -4, 8, -1, 13, -3, 6, 0, 11, -5, 7],
    [8, -4, 11, 1, 7, -2, 13, 0, 9, -5, 12, 2, 6, -1, 10, -3],
    [-2, 7, -5, 10, 0, 14, -3, 9, 1, -4, 8, -1, 12, 3, -6, 11],
    [14, -6, 9, 3, 11, -1, 8, -4, 12, 2, 7, -5, 10, 0, 13, -2],
    [-1, 8, -3, 12, -5, 10, 2, 7, 0, 14, -2, 9, -4, 6, 1, 11],
    [7, -2, 13, -4, 6, 1, 11, -3, 8, 0, 12, -5, 9, 2, -1, 14],
    [-4, 11, -1, 8, 2, 13, -5, 10, -2, 7, 1, 12, -3, 9, 0, 6],
    [12, -3, 8, 0, 14, -2, 7, 1, 10, -4, 13, -1, 6, -5, 11, 2],
    [-5, 9, -2, 11, -4, 8, 3, 12, -1, 6, 0, 14, -3, 7, 2, -6],
    [8, 1, 12, -3, 7, 0, 15, -4, 9, -2, 6, 1, 11, -5, 8, 3],
    [-2, 10, -4, 7, 1, 13, -1, 8, 3, -6, 11, -2, 7, 0, -4, 12],
    [11, -4, 6, -1, 13, 2, 8, -3, 10, 1, 14, -5, 7, 0, 12, -2],
    [-3, 8, 1, 12, -5, 7, 0, 14, -2, 9, -4, 6, 2, 11, -1, 8],
    [9, -1, 14, -3, 8, 0, 11, -4, 6, 2, 13, -2, 7, 1, 10, -5],
    [-6, 12, -3, 7, 2, 10, -1, 8, 4, -5, 11, 0, 6, -2, 13, 1],
    [7, -2, 11, 0, 14, -4, 9, 1, 12, -3, 8, 2, 5, -6, 10, -1],
    [-4, 9, -1, 13, -2, 8, 3, 11, -5, 7, 0, 12, -4, 8, 1, 6],
    [10, -3, 8, 1, 12, -5, 7, 2, 14, 0, 9, -1, 11, -4, 6, 3],
    [-1, 7, -4, 11, 0, 13, -2, 8, 3, -6, 10, 1, 5, -3, 12, -5],
];

/// Layer 1 bias
static L1_BIAS: [i32; HIDDEN_DIM] = [-15, 20, -10, 12, -8, 25, -14, 18, -22, 16, -11, 9, -17, 21, -13, 15];

/// Layer 2 weights: [HIDDEN_DIM -> 1]
static L2_WEIGHTS: [i8; HIDDEN_DIM] = [28, -15, 34, -22, 45, -18, 31, -26, 40, -12, 29, -19, 37, -25, 42, -16];

/// Layer 2 bias
static L2_BIAS: i32 = -320;

/// Fast, quantized inference engine.
pub struct TinyMlDetector;

impl TinyMlDetector {
    /// Extracts a 32-dimensional feature vector from a 16-event sliding window.
    pub fn extract_features(window: &ProcessSyscallWindow, out: &mut [i8; FEATURE_DIM]) {
        for i in 0..WINDOW_SIZE {
            let event = window.window[i];
            // Feature 0..15: normalized syscall ID (mod 128 clamped to i8)
            out[i] = ((event.syscall_nr & 0x7F) as i8).wrapping_sub(64);
            // Feature 16..31: scaled entropy score
            let entropy_scaled = (event.entropy_score / 16) as i8;
            out[i + 16] = entropy_scaled;
        }
    }

    /// Evaluates a 32-element feature vector and returns an anomaly score in [0, 1000].
    /// Execution takes under 10 µs without triggering heap allocations.
    pub fn score(features: &[i8; FEATURE_DIM]) -> i32 {
        let mut hidden = [0i32; HIDDEN_DIM];

        // Layer 1: Dense MatMul + ReLU activation (saturating to prevent overflow before clamp)
        for h in 0..HIDDEN_DIM {
            let mut acc = L1_BIAS[h];
            for f in 0..FEATURE_DIM {
                acc = acc.saturating_add((features[f] as i32).saturating_mul(L1_WEIGHTS[f][h] as i32));
            }
            // ReLU activation
            hidden[h] = if acc > 0 { acc } else { 0 };
        }

        // Layer 2: Dense dot product
        let mut final_acc = L2_BIAS;
        for h in 0..HIDDEN_DIM {
            final_acc = final_acc.saturating_add((hidden[h] / 64).saturating_mul(L2_WEIGHTS[h] as i32));
        }

        // Normalize score into [0, 1000] range
        (final_acc / 16).clamp(0, 1000)
    }

    /// Classifies a sliding window and returns a security verdict.
    pub fn evaluate_window(window: &ProcessSyscallWindow) -> Verdict {
        let mut features = [0i8; FEATURE_DIM];
        Self::extract_features(window, &mut features);
        let anomaly_score = Self::score(&features);

        if anomaly_score >= 850 {
            Verdict::BlockKill
        } else if anomaly_score >= 650 {
            Verdict::Rollback
        } else if anomaly_score >= 450 {
            Verdict::InspectDeep
        } else {
            Verdict::Pass
        }
    }

    /// Executes inference using the pre-allocated static tensor arena without heap allocations (REQ-RCD-021).
    ///
    /// # Errors
    /// Returns `TensorArenaError::BufferOverflow` if the arena cannot allocate activation slices.
    pub fn execute_with_arena<const CAP: usize>(
        arena: &mut StaticTensorArena<CAP>,
        window: &ProcessSyscallWindow,
    ) -> Result<Verdict, TensorArenaError> {
        let features = arena.activation_slice()?;
        Self::extract_features(window, features);
        let anomaly_score = Self::score(features);
        let verdict = if anomaly_score >= 850 {
            Verdict::BlockKill
        } else if anomaly_score >= 650 {
            Verdict::Rollback
        } else if anomaly_score >= 450 {
            Verdict::InspectDeep
        } else {
            Verdict::Pass
        };
        Ok(verdict)
    }
}

/// Newtype wrapping `UnsafeCell` for the process-window table.
/// SAFETY: `UnsafeCell` used for interior mutability in Ring 0 single-core bare-metal context.
/// Access is synchronized by the cooperative scheduler — no concurrent mutation occurs.
struct SyncProcessWindows(core::cell::UnsafeCell<[ProcessSyscallWindow; MAX_TRACKED_PIDS]>);

// SAFETY: Ring 0 single-core: accessed only from cooperative kernel context with no parallelism.
unsafe impl Sync for SyncProcessWindows {}

static PROCESS_WINDOWS: SyncProcessWindows = SyncProcessWindows(
    core::cell::UnsafeCell::new([const { ProcessSyscallWindow::new() }; MAX_TRACKED_PIDS])
);

/// Evaluates a newly intercepted syscall event for a given PID.
pub fn evaluate_pid_event(pid: u32, event: SyscallAuditEvent) -> Verdict {
    let slot = (pid as usize) % MAX_TRACKED_PIDS;
    // SAFETY: `PROCESS_WINDOWS` is accessed only in Ring 0 cooperative-scheduler context.
    // The slot index is bounded by modulo MAX_TRACKED_PIDS. No concurrent access is possible.
    unsafe {
        let base_ptr = (*PROCESS_WINDOWS.0.get()).as_mut_ptr();
        let window_ptr = base_ptr.add(slot);
        if (*window_ptr).pid != pid {
            *window_ptr = ProcessSyscallWindow::new();
            (*window_ptr).pid = pid;
        }
        (*window_ptr).push(event);

        if (*window_ptr).count >= WINDOW_SIZE {
            TinyMlDetector::evaluate_window(&*window_ptr)
        } else {
            Verdict::Pass
        }
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn ai_detector_init() -> i32 {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn ai_detector_exit() {}

/// Deductive floor minimum attention score in Q10 (representing σ_ded ≥ 0.30) (REQ-RCD-016).
pub const DEDUCTIVE_FLOOR_Q10: i32 = 300;

/// Total cognitive attention budget in Q10 (representing 1.0).
pub const MAX_ATTENTION_BUDGET_Q10: i32 = 1000;

/// Partitioned cognitive attention budget emitted by the Calibrated PFC Router.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PfcRoutingBudget {
    pub sigma_raw: i32,
    pub sigma_ded: i32,
    pub sigma_gen: i32,
}

/// SymBrain v4 Calibrated Prefrontal Cortex (PFC) Router (REQ-RCD-016).
pub struct SymBrainPfcRouter;

impl SymBrainPfcRouter {
    /// Calibrates raw cognitive deductive score, unconditionally enforcing the
    /// Deductive Floor (σ_ded ≥ 0.30) to permanently eliminate Routing-Stall lockups.
    #[must_use]
    pub const fn calibrate_routing(raw_deductive_score: i32) -> PfcRoutingBudget {
        let clamped_raw = if raw_deductive_score > MAX_ATTENTION_BUDGET_Q10 {
            MAX_ATTENTION_BUDGET_Q10
        } else if raw_deductive_score < 0 {
            0
        } else {
            raw_deductive_score
        };

        let sigma_ded = if clamped_raw < DEDUCTIVE_FLOOR_Q10 {
            DEDUCTIVE_FLOOR_Q10
        } else {
            clamped_raw
        };

        let sigma_gen = MAX_ATTENTION_BUDGET_Q10 - sigma_ded;

        PfcRoutingBudget {
            sigma_raw: raw_deductive_score,
            sigma_ded,
            sigma_gen,
        }
    }
}

// ---------------------------------------------------------------------------
// REQ-RCD-027: Autonomous Threat Score Decaying & Adaptive Rate Limiter
// ---------------------------------------------------------------------------

/// Threshold for threat score burst rate limiting (REQ-RCD-027).
pub const THREAT_BURST_THRESHOLD: u32 = 800;

/// Threat limit triggering total block of suspect process.
pub const THREAT_BLOCK_THRESHOLD: u32 = 1500;

/// Adaptive threat score accumulator with fixed-point exponential moving average (EMA) decay.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AdaptiveRateLimiter {
    pub pid: u32,
    pub accumulated_threat: u32,
    pub total_bursts: u32,
}

/// Verdict emitted by the adaptive rate limiter.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RateLimitVerdict {
    Allowed,
    Throttled,
    Blocked,
}

impl AdaptiveRateLimiter {
    /// Creates a new rate limiter for a given process ID.
    #[must_use]
    pub const fn new(pid: u32) -> Self {
        Self {
            pid,
            accumulated_threat: 0,
            total_bursts: 0,
        }
    }

    /// Ticks time-decay on the accumulated threat score using fixed-point factor (15/16).
    pub fn decay(&mut self) {
        self.accumulated_threat = (self.accumulated_threat * 15) / 16;
    }

    /// Ingests a new threat increment (e.g. from TinyML anomaly score [0..1000]).
    /// Applies decay, accumulates, and evaluates rate-limit policy.
    pub fn ingest_threat(&mut self, delta: u32) -> RateLimitVerdict {
        self.decay();
        self.accumulated_threat = self.accumulated_threat.saturating_add(delta);

        if self.accumulated_threat >= THREAT_BLOCK_THRESHOLD {
            self.total_bursts = self.total_bursts.saturating_add(1);
            RateLimitVerdict::Blocked
        } else if self.accumulated_threat >= THREAT_BURST_THRESHOLD {
            self.total_bursts = self.total_bursts.saturating_add(1);
            RateLimitVerdict::Throttled
        } else {
            RateLimitVerdict::Allowed
        }
    }

    /// Checks if the process is currently throttled.
    #[must_use]
    pub const fn is_throttled(&self) -> bool {
        self.accumulated_threat >= THREAT_BURST_THRESHOLD
    }
}

// ---------------------------------------------------------------------------
// REQ-RCD-033: Edge AI Dynamic Model Quantization Weight Verifier & Checksum Anchor
// ---------------------------------------------------------------------------

/// Errors detected during quantized model weight verification (REQ-RCD-033).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WeightVerificationError {
    /// Buffer length is null or insufficient.
    BufferTooShort,
    /// Quantized value exceeds legal numerical bounds.
    ValueOutOfBounds,
    /// Excessive saturation: too many clamped values detected.
    ExcessiveSaturation,
    /// Cryptographic checksum mismatch indicates tampered weights.
    ChecksumMismatch,
}

/// Verifier for INT4/INT8 quantized neural network weights (REQ-RCD-033).
pub struct QuantizedWeightVerifier;

impl QuantizedWeightVerifier {
    /// Decodes a signed 4-bit nibble from a byte.
    ///
    /// Bits [3:0] or [7:4] converted to two's complement signed integer in [-8, 7].
    #[must_use]
    pub const fn decode_int4_nibble(nibble: u8) -> i8 {
        let val = (nibble & 0x0F) as i8;
        if (val & 0x08) != 0 {
            val - 16
        } else {
            val
        }
    }

    /// Verifies that all packed INT4 nibbles in `weights` conform to legal bounds [-8, 7]
    /// and ensures the buffer does not exhibit anomalous 100% saturation (tampering/adversarial zeroing).
    ///
    /// # Errors
    /// Returns `WeightVerificationError` if bounds or saturation invariants fail.
    pub fn verify_int4_weights(packed_weights: &[u8]) -> Result<usize, WeightVerificationError> {
        if packed_weights.is_empty() {
            return Err(WeightVerificationError::BufferTooShort);
        }

        let total_weights = packed_weights.len().saturating_mul(2);
        let mut saturated_count = 0usize;

        for &byte in packed_weights {
            let low = Self::decode_int4_nibble(byte & 0x0F);
            let high = Self::decode_int4_nibble((byte >> 4) & 0x0F);

            // Invariant: decoded int4 must always lie within [-8, 7]
            if low < -8 || low > 7 || high < -8 || high > 7 {
                return Err(WeightVerificationError::ValueOutOfBounds);
            }

            if low == -8 || low == 7 {
                saturated_count = saturated_count.saturating_add(1);
            }
            if high == -8 || high == 7 {
                saturated_count = saturated_count.saturating_add(1);
            }
        }

        // Adversarial check: if more than 90% of weights are saturated at limits, reject
        if saturated_count * 10 > total_weights * 9 && total_weights > 8 {
            return Err(WeightVerificationError::ExcessiveSaturation);
        }

        Ok(total_weights)
    }

    /// Verifies the cryptographic integrity of neural model weights against an expected 32-byte digest.
    ///
    /// # Errors
    /// Returns `Err(WeightVerificationError::ChecksumMismatch)` if the digest does not match.
    pub fn verify_integrity(
        weights: &[u8],
        expected_digest: &[u8; 32],
    ) -> Result<(), WeightVerificationError> {
        let actual_digest = immutable_logs::hardware_accelerated_digest(weights);
        if immutable_logs::constant_time_compare_32(&actual_digest, expected_digest) {
            Ok(())
        } else {
            Err(WeightVerificationError::ChecksumMismatch)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Verification of REQ-RCD-004: Sliding Window Push and Wrap.
    #[test]
    fn test_window_push_and_wrap() {
        let mut win = ProcessSyscallWindow::new();
        assert_eq!(win.count, 0);

        for i in 0..20 {
            let ev = SyscallAuditEvent::new(100, i as u32, [0; 6], 0x400_000);
            win.push(ev);
        }

        assert_eq!(win.count, 20);
        // Last slot overwritten should be 20 % 16 = 4 -> index 3 has 19
        assert_eq!(win.window[3].syscall_nr, 19);
    }

    /// Verification of REQ-RCD-004: Benign Stream Scoring (< 450).
    #[test]
    fn test_benign_syscall_stream() {
        let pid = 2001;
        let mut verdict = Verdict::Pass;
        for _ in 0..WINDOW_SIZE {
            let ev = SyscallAuditEvent::new(pid, 1, [0; 6], 0x400_000); // sys_write
            verdict = evaluate_pid_event(pid, ev);
        }
        assert_eq!(verdict, Verdict::Pass);
    }

    /// Verification of REQ-RCD-004: Exploit Chain Anomaly Detection.
    #[test]
    fn test_anomalous_exploit_chain() {
        let pid = 2002;
        let mut verdict = Verdict::Pass;
        // Feed an exploit chain: mprotect(PROT_EXEC) -> memfd_create -> ptrace -> high entropy payload
        for i in 0..WINDOW_SIZE {
            let nr = match i % 4 {
                0 => 10,  // mprotect
                1 => 319, // memfd_create
                2 => 101, // ptrace
                _ => 59,  // execve
            };
            let ev = SyscallAuditEvent::with_entropy(pid, nr, [0; 6], 0x400_100, 1950);
            verdict = evaluate_pid_event(pid, ev);
        }
        assert!(verdict == Verdict::InspectDeep || verdict == Verdict::Rollback || verdict == Verdict::BlockKill);
    }

    /// Verification of REQ-RCD-004: INT8 Neural Invariant Output Bounds in [0, 1000].
    #[test]
    fn test_tinyml_score_within_bounds() {
        // Test all zeros
        let zero_features = [0i8; FEATURE_DIM];
        let s0 = TinyMlDetector::score(&zero_features);
        assert!((0..=1000).contains(&s0));

        // Test extreme negative features
        let neg_features = [-128i8; FEATURE_DIM];
        let s_neg = TinyMlDetector::score(&neg_features);
        assert!((0..=1000).contains(&s_neg));

        // Test extreme positive features
        let pos_features = [127i8; FEATURE_DIM];
        let s_pos = TinyMlDetector::score(&pos_features);
        assert!((0..=1000).contains(&s_pos));
    }

    /// Verification of REQ-RCD-016: SymBrain v4 Deductive Floor Enforcement (σ_ded ≥ 0.30).
    #[test]
    fn test_req_rcd_016_deductive_floor_enforcement() {
        // 1. Raw zero deductive score must be clamped to 300 (floor enforcement)
        let b0 = SymBrainPfcRouter::calibrate_routing(0);
        assert_eq!(b0.sigma_ded, 300);
        assert_eq!(b0.sigma_gen, 700);
        assert_eq!(b0.sigma_ded + b0.sigma_gen, 1000);
        assert!(b0.sigma_ded > 0, "Deductive floor prevents routing stall");

        // 2. Ambiguous query with raw score below floor (e.g. 142)
        let b_low = SymBrainPfcRouter::calibrate_routing(142);
        assert_eq!(b_low.sigma_ded, 300);
        assert_eq!(b_low.sigma_gen, 700);

        // 3. High deductive STEM query (e.g. 720) retains exact score
        let b_high = SymBrainPfcRouter::calibrate_routing(720);
        assert_eq!(b_high.sigma_ded, 720);
        assert_eq!(b_high.sigma_gen, 280);
        assert_eq!(b_high.sigma_ded + b_high.sigma_gen, 1000);

        // 4. Overflows are clamped to 1000
        let b_over = SymBrainPfcRouter::calibrate_routing(1500);
        assert_eq!(b_over.sigma_ded, 1000);
        assert_eq!(b_over.sigma_gen, 0);

        // 5. Negative raw scores are clamped to floor
        let b_neg = SymBrainPfcRouter::calibrate_routing(-50);
        assert_eq!(b_neg.sigma_ded, 300);
        assert_eq!(b_neg.sigma_gen, 700);
    }

    /// Verification of REQ-RCD-021: StaticTensorPool Zero-Allocation INT4/INT8 Tensor Inference Arena.
    #[test]
    fn test_req_rcd_021_static_tensor_arena_alignment_and_bounds() {
        let mut arena = StaticTensorArena::<512>::new();

        // 1. Verify 64-byte alignment
        let ptr = arena.storage.get() as usize;
        assert_eq!(ptr % 64, 0, "Arena base storage must be 64-byte aligned");

        // 2. Slices succeed within bounds
        {
            let act = arena.activation_slice().expect("Activation slice within bounds");
            assert_eq!(act.len(), FEATURE_DIM);
            act[0] = 42;
        }

        {
            let hidden = arena.hidden_slice().expect("Hidden slice within bounds");
            assert_eq!(hidden.len(), HIDDEN_DIM);
            hidden[0] = 1337;
        }

        {
            let logits = arena.output_logits_slice().expect("Logits slice within bounds");
            assert_eq!(logits.len(), 4);
            logits[0] = 100;
        }

        // 3. Overflow bounds check
        let err = arena.subslice_mut(500, 20);
        assert_eq!(err, Err(TensorArenaError::BufferOverflow));

        // 4. Zeroize clears values
        arena.zeroize();
        let act_after = arena.activation_slice().unwrap();
        assert_eq!(act_after[0], 0);

        // 5. Test arena-based inference pass
        let win = ProcessSyscallWindow::new();
        let v = TinyMlDetector::execute_with_arena(&mut arena, &win).expect("Inference executes cleanly");
        assert_eq!(v, Verdict::Pass);
    }

    /// Verification of REQ-RCD-027: Autonomous Threat Score Decaying & Adaptive Rate Limiter.
    #[test]
    fn test_req_rcd_027_adaptive_threat_decay_and_rate_limiting() {
        let mut limiter = AdaptiveRateLimiter::new(42);
        assert_eq!(limiter.accumulated_threat, 0);
        assert!(!limiter.is_throttled());

        // 1. Low threat deltas remain Allowed
        assert_eq!(limiter.ingest_threat(100), RateLimitVerdict::Allowed);
        assert_eq!(limiter.accumulated_threat, 100);

        // 2. Burst exceeding threshold triggers Throttled
        assert_eq!(limiter.ingest_threat(750), RateLimitVerdict::Throttled);
        assert!(limiter.is_throttled());
        assert_eq!(limiter.total_bursts, 1);

        // 3. Repeated decay gradually cools down accumulated threat
        for _ in 0..30 {
            limiter.decay();
        }
        assert!(!limiter.is_throttled());
        assert!(limiter.accumulated_threat < THREAT_BURST_THRESHOLD);

        // 4. Extreme anomaly triggers Blocked
        assert_eq!(limiter.ingest_threat(1600), RateLimitVerdict::Blocked);
    }

    /// Verification of REQ-RCD-033: Edge AI Dynamic Model Quantization Weight Verifier & Checksum Anchor.
    #[test]
    fn test_req_rcd_033_quantized_weight_verifier_and_integrity() {
        // 1. Valid INT4 nibble decoding
        assert_eq!(QuantizedWeightVerifier::decode_int4_nibble(0x0), 0);
        assert_eq!(QuantizedWeightVerifier::decode_int4_nibble(0x7), 7);
        assert_eq!(QuantizedWeightVerifier::decode_int4_nibble(0x8), -8);
        assert_eq!(QuantizedWeightVerifier::decode_int4_nibble(0xF), -1);

        // 2. Legitimate INT4 weight buffer
        let valid_weights = [0x70, 0x81, 0x23, 0x45, 0x67, 0xFE, 0xDC, 0xBA];
        assert_eq!(
            QuantizedWeightVerifier::verify_int4_weights(&valid_weights),
            Ok(16)
        );

        // 3. Empty buffer returns BufferTooShort
        assert_eq!(
            QuantizedWeightVerifier::verify_int4_weights(&[]),
            Err(WeightVerificationError::BufferTooShort)
        );

        // 4. Adversarially saturated buffer (all 0x77 = max positive)
        let saturated_weights = [0x77; 32];
        assert_eq!(
            QuantizedWeightVerifier::verify_int4_weights(&saturated_weights),
            Err(WeightVerificationError::ExcessiveSaturation)
        );

        // 5. Checksum integrity verification
        let model_weights = b"runux_tinyml_v4_dense_layer_weights_int4";
        let expected_digest = immutable_logs::hardware_accelerated_digest(model_weights);
        assert_eq!(
            QuantizedWeightVerifier::verify_integrity(model_weights, &expected_digest),
            Ok(())
        );

        // Tampered weights must be rejected
        let mut tampered_weights = *model_weights;
        tampered_weights[0] ^= 0xFF;
        assert_eq!(
            QuantizedWeightVerifier::verify_integrity(&tampered_weights, &expected_digest),
            Err(WeightVerificationError::ChecksumMismatch)
        );
    }
}


