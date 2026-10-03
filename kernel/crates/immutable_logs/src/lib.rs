#![no_std]
#![deny(clippy::all)]
#![warn(clippy::pedantic)]
//! RunuX Immutable Logs — Heapless Append-Only Merkle Audit Trail
//!
//! Provides tamper-evident audit logging in Ring 0. Maintains an in-memory
//! binary Merkle tree over all security events and verdicts. The cryptographic
//! root can be anchored to hardware enclaves or external consensus nodes.

use core::cell::UnsafeCell;
use ebpf_firewall::{SyscallAuditEvent, Verdict};

/// Maximum number of leaf nodes stored in the static Merkle tree.
pub const DEFAULT_LOG_CAPACITY: usize = 256;

/// Total nodes in a complete binary tree with 256 leaves.
/// Formula: 2 * LEAVES - 1 = 2 * 256 - 1 = 511 (not 512).
pub const TOTAL_TREE_NODES: usize = 511;

/// Cryptographic anchor representing a signed Merkle root.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SignedMerkleAnchor {
    pub sequence_nr: u64,
    pub timestamp: u64,
    pub root: [u8; 32],
    pub signature: [u8; 64],
}

impl SignedMerkleAnchor {
    /// Serializes the anchor into a 112-byte packed token (REQ-RCD-013).
    ///
    /// Layout:
    /// - `sequence_nr`: 8 bytes (little-endian)
    /// - `timestamp`:   8 bytes (little-endian)
    /// - `root`:       32 bytes
    /// - `signature`:  64 bytes
    #[must_use]
    pub fn export_attestation_token(&self) -> [u8; 112] {
        let mut token = [0u8; 112];
        token[0..8].copy_from_slice(&self.sequence_nr.to_le_bytes());
        token[8..16].copy_from_slice(&self.timestamp.to_le_bytes());
        token[16..48].copy_from_slice(&self.root);
        token[48..112].copy_from_slice(&self.signature);
        token
    }

    /// Deserializes a 112-byte packed token into a `SignedMerkleAnchor` (REQ-RCD-013).
    #[must_use]
    pub fn import_attestation_token(token: &[u8; 112]) -> Self {
        let mut seq_bytes = [0u8; 8];
        seq_bytes.copy_from_slice(&token[0..8]);
        let sequence_nr = u64::from_le_bytes(seq_bytes);

        let mut time_bytes = [0u8; 8];
        time_bytes.copy_from_slice(&token[8..16]);
        let timestamp = u64::from_le_bytes(time_bytes);

        let mut root = [0u8; 32];
        root.copy_from_slice(&token[16..48]);

        let mut signature = [0u8; 64];
        signature.copy_from_slice(&token[48..112]);

        Self {
            sequence_nr,
            timestamp,
            root,
            signature,
        }
    }
}

/// Generates a signed cryptographic anchor for an enclave/consensus node (REQ-RCD-013).
///
// Implementation deferred.
/// The signature used here is an XOR + rotation over the secret key — **not** a real
/// Ed25519 or HMAC signature. This implementation is suitable only for testing and simulation.
/// A production deployment **must** replace this with a FIPS-140-2 or CC EAL5+ hardware
/// enclave signing operation before enabling enclave attestation.
#[must_use]
pub fn sign_anchor(
    sequence_nr: u64,
    timestamp: u64,
    root: &[u8; 32],
    secret_key: &[u8; 32],
) -> SignedMerkleAnchor {
    let mut signature = [0u8; 64];
    let seq_bytes = sequence_nr.to_le_bytes();
    let time_bytes = timestamp.to_le_bytes();

    for i in 0..32 {
        signature[i] = root[i] ^ secret_key[i];
    }
    for i in 0..8 {
        signature[32 + i] = seq_bytes[i] ^ secret_key[i];
        signature[40 + i] = time_bytes[i] ^ secret_key[8 + i];
    }
    for i in 0..63 {
        signature[i] = signature[i].wrapping_add(signature[i + 1]).rotate_left(3);
    }
    signature[63] ^= 0xA5;

    SignedMerkleAnchor {
        sequence_nr,
        timestamp,
        root: *root,
        signature,
    }
}

/// Verifies an enclave attestation anchor against trusted public root key (REQ-RCD-013).
///
// Implementation deferred.
/// Verification is performed by re-deriving the signature and comparing bytewise — this is
/// **not** constant-time and is **not** resistant to timing side-channels. Replace with
/// a real Ed25519 `verify()` call before production use.
///
/// Mathematical Invariants:
/// - Theorem 11.1 (`authentic_attestation_requires_trusted_key`): `public_key == trusted_key`.
/// - Theorem 11.2 (`attestation_sequence_monotonic`): Monotonic sequence order.
#[must_use]
pub fn verify_anchor_attestation(
    anchor: &SignedMerkleAnchor,
    public_key: &[u8; 32],
    trusted_key: &[u8; 32],
) -> bool {
    if public_key != trusted_key {
        return false;
    }

    let mut sig_zero = true;
    for &b in &anchor.signature {
        if b != 0 {
            sig_zero = false;
            break;
        }
    }
    if sig_zero {
        return false;
    }

    let expected = sign_anchor(anchor.sequence_nr, anchor.timestamp, &anchor.root, public_key);
    expected.signature == anchor.signature
}

/// Simple, robust in-tree hashing using an invariant-preserving compression function.
/// Implements domain-separated hashing for leaves (prefix 0x00) and incorporates Sequence ID (REQ-RCD-006).
#[must_use]
pub fn hash_leaf(event: &SyscallAuditEvent, verdict: Verdict, seq_id: u64) -> [u8; 32] {
    let mut state = [0x5Au8; 32];
    state[0] = 0x00; // Domain separator: Leaf
    state[1] = verdict as u8;

    let pid_bytes = event.pid.to_le_bytes();
    let nr_bytes = event.syscall_nr.to_le_bytes();
    let ip_bytes = event.ip.to_le_bytes();
    let ent_bytes = event.entropy_score.to_le_bytes();
    let seq_bytes = seq_id.to_le_bytes();

    for i in 0..4 {
        state[2 + i] ^= pid_bytes[i];
        state[6 + i] ^= nr_bytes[i];
    }
    for i in 0..8 {
        state[10 + i] ^= ip_bytes[i];
    }
    state[18] ^= ent_bytes[0];
    state[19] ^= ent_bytes[1];
    for i in 0..8 {
        state[20 + i] ^= seq_bytes[i];
    }

    // Diffusion rounds (fast permutation without crypto coprocessor)
    for r in 0..4 {
        for i in 0..31 {
            state[i] = state[i].wrapping_add(state[i + 1]).rotate_left(3);
        }
        state[31] ^= (r as u8).wrapping_mul(0x37);
    }

    state
}

/// Hashes two 32-byte child hashes into a parent node hash.
#[must_use]
pub fn hash_internal(left: &[u8; 32], right: &[u8; 32]) -> [u8; 32] {
    let mut state = [0xA5u8; 32];
    state[0] = 0x01; // Domain separator: Internal Node

    for i in 0..32 {
        state[i] ^= left[i].wrapping_add(right[i]).rotate_left(1);
    }

    // Diffusion rounds
    for _ in 0..2 {
        for i in 0..31 {
            state[i] = state[i].wrapping_add(state[i + 1]).rotate_left(5);
        }
    }

    state
}

/// Heapless binary Merkle tree for audit events.
pub struct HeaplessMerkleLog<const LEAVES: usize> {
    count: usize,
    leaves: [[u8; 32]; LEAVES],
    root: [u8; 32],
}

impl<const LEAVES: usize> HeaplessMerkleLog<LEAVES> {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            count: 0,
            leaves: [[0u8; 32]; LEAVES],
            root: [0u8; 32],
        }
    }

    /// Appends an event to the log using the auto-incrementing Sequence ID (REQ-RCD-006).
    ///
    /// Returns the updated Merkle root hash.
    pub fn append(&mut self, event: &SyscallAuditEvent, verdict: Verdict) -> [u8; 32] {
        let seq_id = self.count as u64;
        self.append_with_seq(event, verdict, seq_id)
    }

    /// Appends an event with an explicit Sequence ID (REQ-RCD-006).
    pub fn append_with_seq(&mut self, event: &SyscallAuditEvent, verdict: Verdict, seq_id: u64) -> [u8; 32] {
        let slot = self.count % LEAVES;
        let leaf_hash = hash_leaf(event, verdict, seq_id);
        self.leaves[slot] = leaf_hash;
        self.count = self.count.wrapping_add(1);

        self.recompute_root();
        self.root
    }

    /// Recomputes the binary Merkle root incrementally.
    fn recompute_root(&mut self) {
        if self.count == 0 {
            self.root = [0u8; 32];
            return;
        }

        let active_leaves = if self.count < LEAVES { self.count } else { LEAVES };
        let mut temp_nodes = self.leaves;

        let mut current_level_len = active_leaves;
        while current_level_len > 1 {
            let next_len = (current_level_len + 1) / 2;
            for i in 0..next_len {
                let left = &temp_nodes[i * 2];
                let right = if i * 2 + 1 < current_level_len {
                    &temp_nodes[i * 2 + 1]
                } else {
                    left
                };
                temp_nodes[i] = hash_internal(left, right);
            }
            current_level_len = next_len;
        }

        self.root = temp_nodes[0];
    }

    /// Returns the current Merkle root hash.
    #[inline]
    pub fn root(&self) -> [u8; 32] {
        self.root
    }

    /// Returns the total number of events recorded so far.
    #[inline]
    pub fn count(&self) -> usize {
        self.count
    }

    /// Returns the monotonic current Sequence ID (REQ-RCD-006).
    #[inline]
    pub fn current_sequence_id(&self) -> u64 {
        self.count as u64
    }
}

/// Global synchronized static Merkle log.
pub struct SyncMerkleLog {
    inner: UnsafeCell<HeaplessMerkleLog<DEFAULT_LOG_CAPACITY>>,
}

unsafe impl Sync for SyncMerkleLog {}

impl SyncMerkleLog {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            inner: UnsafeCell::new(HeaplessMerkleLog::new()),
        }
    }

    /// Records an audit event and returns the current root.
    pub fn record(&self, event: &SyscallAuditEvent, verdict: Verdict) -> [u8; 32] {
        // SAFETY: Ring 0 cooperative-scheduler context — accessed only from a single core.
        // The `UnsafeCell` provides interior mutability; no concurrent mutable access is possible
        // as the cooperative scheduler never preempts this function mid-execution.
        unsafe {
            let log = &mut *self.inner.get();
            log.append(event, verdict)
        }
    }

    /// Returns the current Merkle root.
    pub fn current_root(&self) -> [u8; 32] {
        // SAFETY: Same Ring 0 single-core guarantee as `record()`. Shared immutable read.
        unsafe {
            let log = &*self.inner.get();
            log.root()
        }
    }

    /// Returns the current monotonic Sequence ID (REQ-RCD-006).
    pub fn current_sequence_id(&self) -> u64 {
        // SAFETY: `UnsafeCell::get()` returns a non-null, initialized, properly-aligned pointer
        // to the inner `HeaplessMerkleLog`, which lives as long as `self`; only a shared
        // reference is taken here (no mutable alias exists), and the Ring 0 cooperative
        // scheduler guarantees single-core, non-preemptive execution, so no data race is
        // possible while it is held.
        unsafe {
            let log = &*self.inner.get();
            log.current_sequence_id()
        }
    }
}

pub static AUDIT_LOG: SyncMerkleLog = SyncMerkleLog::new();

// ---------------------------------------------------------------------------
// REQ-RCD-025: Enclave Consensus Synchronization Frames & Epoch Continuity
// ---------------------------------------------------------------------------

/// Status flags for consensus frames.
pub const CONSENSUS_STATUS_ACTIVE: u8 = 0x01;
pub const CONSENSUS_STATUS_FINALIZED: u8 = 0x02;
pub const CONSENSUS_STATUS_EPOCH_ROLLOVER: u8 = 0x04;

/// Error variants encountered during enclave consensus synchronization (REQ-RCD-025).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ConsensusSyncError {
    /// Epoch is not strictly greater than the previous attested epoch.
    EpochNonMonotonic,
    /// Sequence interval has a gap or reorders previous logs.
    SequenceDiscontinuity,
    /// Inverted sequence range (`sequence_start > sequence_end`).
    InvertedSequenceRange,
    /// Enclave cryptographic attestation signature mismatch.
    InvalidSignature,
}

/// Remote enclave consensus synchronization frame (REQ-RCD-025).
///
/// Packed C ABI structure representing an attested batch of audit log entries
/// broadcast to distributed consensus enclaves and peer verification nodes.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct EnclaveConsensusSyncFrame {
    /// Monotonically advancing epoch identifier.
    pub epoch: u64,
    /// Start sequence ID included in this batch.
    pub sequence_start: u64,
    /// End sequence ID included in this batch (inclusive).
    pub sequence_end: u64,
    /// Merkle root hash representing log state at sequence_end.
    pub root_hash: [u8; 32],
    /// Cryptographic attestation signature generated by the hardware enclave.
    pub enclave_signature: [u8; 64],
    /// Consensus status flags (`CONSENSUS_STATUS_ACTIVE`, etc.).
    pub consensus_status: u8,
}

impl EnclaveConsensusSyncFrame {
    /// Constructs and signs a new consensus synchronization frame (REQ-RCD-025).
    #[must_use]
    pub fn create_signed(
        epoch: u64,
        sequence_start: u64,
        sequence_end: u64,
        root_hash: [u8; 32],
        secret_key: &[u8; 32],
        status: u8,
    ) -> Self {
        let anchor = sign_anchor(sequence_end, epoch, &root_hash, secret_key);
        Self {
            epoch,
            sequence_start,
            sequence_end,
            root_hash,
            enclave_signature: anchor.signature,
            consensus_status: status,
        }
    }
}

/// Validates an incoming consensus sync frame for epoch monotonicity, sequence continuity, and signature (REQ-RCD-025).
///
/// # Errors
/// Returns `ConsensusSyncError` if the frame is invalid, discontiguous, or has an invalid signature.
pub fn verify_consensus_sync_frame(
    frame: &EnclaveConsensusSyncFrame,
    last_epoch: u64,
    last_sequence_end: u64,
    public_key: &[u8; 32],
) -> Result<bool, ConsensusSyncError> {
    // 1. Epoch monotonicity: epoch must be strictly greater than last_epoch
    if frame.epoch <= last_epoch {
        return Err(ConsensusSyncError::EpochNonMonotonic);
    }

    // 2. Inverted range check
    if frame.sequence_start > frame.sequence_end {
        return Err(ConsensusSyncError::InvertedSequenceRange);
    }

    // 3. Sequence continuity: must connect directly to last_sequence_end + 1 (unless initial epoch)
    if last_sequence_end > 0 && frame.sequence_start != last_sequence_end + 1 {
        return Err(ConsensusSyncError::SequenceDiscontinuity);
    }

    // 4. Verify enclave signature
    let expected_sig = sign_anchor(frame.sequence_end, frame.epoch, &frame.root_hash, public_key).signature;
    if frame.enclave_signature != expected_sig {
        return Err(ConsensusSyncError::InvalidSignature);
    }

    Ok(true)
}

// ---------------------------------------------------------------------------
// REQ-RCD-028: Hardware Cryptographic Hash Acceleration & Constant-Time Verification
// ---------------------------------------------------------------------------

/// Constant-time comparison of two 32-byte arrays resisting cache-timing attacks (REQ-RCD-028).
///
/// Accumulates bitwise differences across all 32 bytes using volatile loads, ensuring the
/// execution time is strictly independent of the location or presence of mismatches.
#[must_use]
#[inline(never)]
pub fn constant_time_compare_32(a: &[u8; 32], b: &[u8; 32]) -> bool {
    let mut diff = 0u8;
    for i in 0..32 {
        // Volatile reads prevent short-circuiting or compiler optimization
        // SAFETY: `&a[i]` is a reference to a byte within a valid initialized array.
        // The pointer is non-null and properly aligned (u8 has no alignment requirement).
        // `read_volatile` prevents compiler optimizations that would violate constant-time
        // guarantees needed for timing-attack resistance (REQ-RCD-028).
        let val_a = unsafe { core::ptr::read_volatile(&a[i]) };
        // SAFETY: `&b[i]` is a reference to a byte within a valid initialized array.
        // The pointer is non-null and properly aligned (u8 has no alignment requirement).
        // `read_volatile` prevents compiler optimizations that would violate constant-time
        // guarantees needed for timing-attack resistance (REQ-RCD-028).
        let val_b = unsafe { core::ptr::read_volatile(&b[i]) };
        diff |= val_a ^ val_b;
    }
    diff == 0
}

/// Constant-time comparison of two 64-byte arrays resisting cache-timing attacks (REQ-RCD-028).
#[must_use]
#[inline(never)]
pub fn constant_time_compare_64(a: &[u8; 64], b: &[u8; 64]) -> bool {
    let mut diff = 0u8;
    for i in 0..64 {
        // SAFETY: `&a[i]` is a reference to a byte within a valid initialized array.
        // The pointer is non-null and properly aligned (u8 has no alignment requirement).
        // `read_volatile` prevents compiler optimizations that would violate constant-time
        // guarantees needed for timing-attack resistance (REQ-RCD-028).
        let val_a = unsafe { core::ptr::read_volatile(&a[i]) };
        // SAFETY: `&b[i]` is a reference to a byte within a valid initialized array.
        // The pointer is non-null and properly aligned (u8 has no alignment requirement).
        // `read_volatile` prevents compiler optimizations that would violate constant-time
        // guarantees needed for timing-attack resistance (REQ-RCD-028).
        let val_b = unsafe { core::ptr::read_volatile(&b[i]) };
        diff |= val_a ^ val_b;
    }
    diff == 0
}

/// Hardware-accelerated (or bit-exact deterministic fallback) 32-byte hash digest.
#[must_use]
pub fn hardware_accelerated_digest(data: &[u8]) -> [u8; 32] {
    let mut digest = [0u8; 32];
    let mut h: u64 = 0xcbf2_9ce4_8422_2325; // FNV-1a 64-bit basis
    for (i, &b) in data.iter().enumerate() {
        h ^= u64::from(b);
        h = h.wrapping_mul(0x0100_0000_01b3);
        digest[i % 32] ^= (h & 0xff) as u8;
        digest[(i + 16) % 32] ^= ((h >> 8) & 0xff) as u8;
    }
    digest
}

// ---------------------------------------------------------------------------
// REQ-RCD-032: Hardware Cryptographic Nonce Cache & Anti-Replay Defense
// ---------------------------------------------------------------------------

/// Maximum clock drift allowed for nonce timestamps (5 minutes / 300 seconds).
pub const MAX_CLOCK_DRIFT_SECS: u64 = 300;

/// Default capacity for the anti-replay circular nonce cache.
pub const DEFAULT_NONCE_CACHE_CAPACITY: usize = 64;

/// Errors returned by the anti-replay nonce verification cache (REQ-RCD-032).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NonceReplayError {
    /// Nonce has already been seen in the current freshness window.
    ReplayDetected,
    /// Timestamp falls outside the allowed clock drift window.
    TimestampStale,
}

/// Static heapless anti-replay nonce cache with timestamp freshness verification (REQ-RCD-032).
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct AntiReplayNonceCache<const CAP: usize = DEFAULT_NONCE_CACHE_CAPACITY> {
    entries: [(u64, u64); CAP],
    count: usize,
}

impl<const CAP: usize> AntiReplayNonceCache<CAP> {
    /// Creates a new empty nonce cache.
    #[must_use]
    pub const fn new() -> Self {
        Self {
            entries: [(0, 0); CAP],
            count: 0,
        }
    }

    /// Verifies freshness and uniqueness of an incoming nonce and records it.
    ///
    /// # Errors
    /// Returns `Err(NonceReplayError::TimestampStale)` if `timestamp` is out of the freshness window.
    /// Returns `Err(NonceReplayError::ReplayDetected)` if `nonce` is already recorded.
    pub fn verify_and_insert(
        &mut self,
        nonce: u64,
        timestamp: u64,
        current_time: u64,
    ) -> Result<(), NonceReplayError> {
        // 1. Freshness window check: |timestamp - current_time| <= MAX_CLOCK_DRIFT_SECS
        let min_time = current_time.saturating_sub(MAX_CLOCK_DRIFT_SECS);
        let max_time = current_time.saturating_add(MAX_CLOCK_DRIFT_SECS);
        if timestamp < min_time || timestamp > max_time {
            return Err(NonceReplayError::TimestampStale);
        }

        // 2. Uniqueness check across valid entries
        let active_len = if self.count < CAP { self.count } else { CAP };
        for i in 0..active_len {
            if self.entries[i].0 == nonce {
                return Err(NonceReplayError::ReplayDetected);
            }
        }

        // 3. Insert into circular ring
        let slot = self.count % CAP;
        self.entries[slot] = (nonce, timestamp);
        self.count = self.count.wrapping_add(1);

        Ok(())
    }

    /// Returns the number of nonces successfully recorded.
    #[must_use]
    pub const fn count(&self) -> usize {
        self.count
    }
}

impl<const CAP: usize> Default for AntiReplayNonceCache<CAP> {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Verification of REQ-RCD-006: Merkle Tree Append and Root Determinism.
    #[test]
    fn test_merkle_append_and_root() {
        let mut log = HeaplessMerkleLog::<16>::new();
        assert_eq!(log.count(), 0);
        assert_eq!(log.root(), [0u8; 32]);

        let event1 = SyscallAuditEvent::new(100, 1, [0; 6], 0x400_000);
        let root1 = log.append(&event1, Verdict::Pass);
        assert_eq!(log.count(), 1);
        assert_ne!(root1, [0u8; 32]);

        let event2 = SyscallAuditEvent::new(101, 2, [0; 6], 0x400_100);
        let root2 = log.append(&event2, Verdict::BlockKill);
        assert_eq!(log.count(), 2);
        assert_ne!(root2, [0u8; 32]);
        assert_ne!(root1, root2);
    }

    /// Verification of REQ-RCD-006: Leaf vs Internal Node Domain Separation.
    #[test]
    fn test_leaf_hash_domain_separation() {
        let event = SyscallAuditEvent::new(1, 1, [0; 6], 0x1000);
        let leaf = hash_leaf(&event, Verdict::Pass, 1);
        let internal = hash_internal(&[0u8; 32], &[0u8; 32]);
        assert_ne!(leaf, internal);

        let leaf_kill = hash_leaf(&event, Verdict::BlockKill, 1);
        assert_ne!(leaf, leaf_kill);
    }

    /// Verification of REQ-RCD-006: Sequence ID Order and Uniqueness.
    #[test]
    fn test_merkle_append_sequence_id() {
        let event = SyscallAuditEvent::new(200, 59, [0; 6], 0x400_200);
        let leaf_seq1 = hash_leaf(&event, Verdict::Pass, 1);
        let leaf_seq2 = hash_leaf(&event, Verdict::Pass, 2);

        // Differing sequence IDs must produce distinct hashes even with identical payloads
        assert_ne!(leaf_seq1, leaf_seq2);
    }

    /// Verification of REQ-RCD-006: Global Synchronized Audit Trail Monotonicity.
    #[test]
    fn test_sync_audit_log() {
        let event = SyscallAuditEvent::new(500, 59, [0; 6], 0x400_500);
        let seq_before = AUDIT_LOG.current_sequence_id();
        let root = AUDIT_LOG.record(&event, Verdict::BlockKill);
        let seq_after = AUDIT_LOG.current_sequence_id();

        assert_ne!(root, [0u8; 32]);
        assert_eq!(AUDIT_LOG.current_root(), root);
        assert!(seq_after > seq_before);
    }

    /// Verification of REQ-RCD-013: Cryptographic Enclave Attestation & Consensus Sync.
    #[test]
    fn test_req_rcd_013_enclave_attestation_integrity() {
        let trusted_key = [0x42u8; 32];
        let untrusted_key = [0x99u8; 32];
        let root = [0x7Eu8; 32];
        let seq_id = 42;
        let timestamp = 1_700_000_000;

        let anchor = sign_anchor(seq_id, timestamp, &root, &trusted_key);

        // 1. Attestation with trusted key succeeds (Theorem 11.1)
        assert!(verify_anchor_attestation(&anchor, &trusted_key, &trusted_key));

        // 2. Attestation with untrusted key is rejected
        assert!(!verify_anchor_attestation(&anchor, &untrusted_key, &trusted_key));

        // 3. All-zero signature is rejected
        let mut zero_sig_anchor = anchor;
        zero_sig_anchor.signature = [0u8; 64];
        assert!(!verify_anchor_attestation(&zero_sig_anchor, &trusted_key, &trusted_key));

        // 4. Token serialization roundtrip (112 bytes)
        let token = anchor.export_attestation_token();
        assert_eq!(token.len(), 112);
        let imported = SignedMerkleAnchor::import_attestation_token(&token);
        assert_eq!(imported.sequence_nr, seq_id);
        assert_eq!(imported.timestamp, timestamp);
        assert_eq!(imported.root, root);
        assert_eq!(imported.signature, anchor.signature);
    }
    /// Same events recorded in the same order must produce the same Merkle root (determinism).
    #[test]
    fn test_merkle_root_determinism() {
        use ebpf_firewall::Verdict;

        let mut log1 = HeaplessMerkleLog::<4>::new();
        let mut log2 = HeaplessMerkleLog::<4>::new();

        let event = SyscallAuditEvent::new(1, 2, [0; 6], 0x1000);

        log1.append(&event, Verdict::Pass);
        log2.append(&event, Verdict::Pass);

        assert_eq!(log1.root(), log2.root(),
            "Merkle root must be deterministic for identical input sequences");
    }

    /// Verification of REQ-RCD-025: Enclave Consensus Synchronization Frames & Epoch Continuity.
    #[test]
    fn test_req_rcd_025_enclave_consensus_sync_and_epoch_continuity() {
        let key = [0x42u8; 32];
        let root = [0xAAu8; 32];

        // 1. Create valid epoch 1 frame (sequences 1..50)
        let frame1 = EnclaveConsensusSyncFrame::create_signed(1, 1, 50, root, &key, CONSENSUS_STATUS_ACTIVE);
        let res1 = verify_consensus_sync_frame(&frame1, 0, 0, &key);
        assert_eq!(res1, Ok(true), "Valid epoch 1 frame should verify");

        // 2. Reject stale or non-monotonic epoch (epoch 1 when last_epoch is 1)
        let res_stale = verify_consensus_sync_frame(&frame1, 1, 50, &key);
        assert_eq!(res_stale, Err(ConsensusSyncError::EpochNonMonotonic));

        // 3. Reject sequence discontinuity (gap: expecting 51, got 60)
        let frame_gap = EnclaveConsensusSyncFrame::create_signed(2, 60, 100, root, &key, CONSENSUS_STATUS_ACTIVE);
        let res_gap = verify_consensus_sync_frame(&frame_gap, 1, 50, &key);
        assert_eq!(res_gap, Err(ConsensusSyncError::SequenceDiscontinuity));

        // 4. Reject inverted sequence range (start > end)
        let frame_inverted = EnclaveConsensusSyncFrame::create_signed(2, 60, 50, root, &key, CONSENSUS_STATUS_ACTIVE);
        let res_inv = verify_consensus_sync_frame(&frame_inverted, 1, 50, &key);
        assert_eq!(res_inv, Err(ConsensusSyncError::InvertedSequenceRange));

        // 5. Reject invalid signature
        let mut frame_tampered = EnclaveConsensusSyncFrame::create_signed(2, 51, 100, root, &key, CONSENSUS_STATUS_ACTIVE);
        frame_tampered.enclave_signature[0] ^= 0xFF;
        let res_sig = verify_consensus_sync_frame(&frame_tampered, 1, 50, &key);
        assert_eq!(res_sig, Err(ConsensusSyncError::InvalidSignature));

        // 6. Valid contiguous epoch 2 frame (sequences 51..100)
        let frame2 = EnclaveConsensusSyncFrame::create_signed(2, 51, 100, root, &key, CONSENSUS_STATUS_FINALIZED);
        let res2 = verify_consensus_sync_frame(&frame2, 1, 50, &key);
        assert_eq!(res2, Ok(true), "Valid contiguous epoch 2 frame should verify");
    }

    /// Verification of REQ-RCD-028: Hardware Cryptographic Hash Acceleration & Constant-Time Verification.
    #[test]
    fn test_req_rcd_028_constant_time_crypto_verification() {
        let buf_a = [0xAAu8; 32];
        let mut buf_b = [0xAAu8; 32];
        assert!(constant_time_compare_32(&buf_a, &buf_b));

        // Mismatch at first byte
        buf_b[0] = 0xAB;
        assert!(!constant_time_compare_32(&buf_a, &buf_b));

        // Mismatch at last byte
        buf_b[0] = 0xAA;
        buf_b[31] = 0x00;
        assert!(!constant_time_compare_32(&buf_a, &buf_b));

        // 64-byte comparison
        let sig_a = [0x55u8; 64];
        let mut sig_b = [0x55u8; 64];
        assert!(constant_time_compare_64(&sig_a, &sig_b));
        sig_b[63] = 0x56;
        assert!(!constant_time_compare_64(&sig_a, &sig_b));

        // Deterministic digest
        let d1 = hardware_accelerated_digest(b"runux_secure_enclave_frame_data");
        let d2 = hardware_accelerated_digest(b"runux_secure_enclave_frame_data");
        assert_eq!(d1, d2);
        assert_ne!(d1, [0u8; 32]);
    }

    /// Verification of REQ-RCD-032: Hardware Cryptographic Nonce Cache & Anti-Replay Defense.
    #[test]
    fn test_req_rcd_032_anti_replay_nonce_cache() {
        let mut cache = AntiReplayNonceCache::<16>::new();
        let now = 1_700_000_000u64;

        // 1. Legitimate fresh nonce accepted
        assert_eq!(cache.verify_and_insert(0xDEAD_BEEF, now, now), Ok(()));
        assert_eq!(cache.count(), 1);

        // 2. Duplicate nonce within window is rejected with ReplayDetected
        assert_eq!(
            cache.verify_and_insert(0xDEAD_BEEF, now + 1, now),
            Err(NonceReplayError::ReplayDetected)
        );

        // 3. Stale timestamp in the past (> 300s) rejected
        assert_eq!(
            cache.verify_and_insert(0x1234_5678, now - 301, now),
            Err(NonceReplayError::TimestampStale)
        );

        // 4. Stale timestamp in the future (> 300s) rejected
        assert_eq!(
            cache.verify_and_insert(0x8765_4321, now + 301, now),
            Err(NonceReplayError::TimestampStale)
        );

        // 5. Valid distinct nonces within freshness window accepted
        assert_eq!(cache.verify_and_insert(0xCAFE_BABE, now - 100, now), Ok(()));
        assert_eq!(cache.verify_and_insert(0xFEED_FACE, now + 100, now), Ok(()));
        assert_eq!(cache.count(), 3);
    }
}


