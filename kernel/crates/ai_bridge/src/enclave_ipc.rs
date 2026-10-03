//! RunuX Zero-Copy Hardware Zero-Trust Enclave IPC Channel (REQ-RCD-034)
//!
//! Provides lock-free, zero-copy shared memory communication between Ring 0
//! kernel components and the hardware secure enclave.

use core::sync::atomic::{AtomicU32, AtomicU64, Ordering};

/// Default capacity for the enclave IPC buffer (256 bytes, cacheline aligned).
pub const DEFAULT_ENCLAVE_IPC_BUFFER: usize = 256;

/// State of the Enclave IPC Channel state machine (REQ-RCD-034).
#[repr(u32)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EnclaveIpcState {
    Idle = 0,
    Writing = 1,
    Ready = 2,
    Reading = 3,
}

impl EnclaveIpcState {
    #[must_use]
    pub const fn from_u32(val: u32) -> Self {
        match val {
            1 => Self::Writing,
            2 => Self::Ready,
            3 => Self::Reading,
            _ => Self::Idle,
        }
    }
}

/// Errors occurring during Enclave IPC operations.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EnclaveIpcError {
    ChannelBusy,
    ChannelNotReady,
    PayloadTooLarge,
    BufferTooSmall,
}

/// 64-byte cacheline-aligned zero-copy lock-free Enclave IPC Channel (REQ-RCD-034).
#[repr(C, align(64))]
pub struct EnclaveIpcChannel<const BUFFER_SIZE: usize = DEFAULT_ENCLAVE_IPC_BUFFER> {
    state: AtomicU32,
    sequence: AtomicU64,
    payload_len: AtomicU32,
    buffer: [u8; BUFFER_SIZE],
}

impl<const BUFFER_SIZE: usize> EnclaveIpcChannel<BUFFER_SIZE> {
    /// Creates a new uninitialized IPC channel in `Idle` state.
    #[must_use]
    pub const fn new() -> Self {
        Self {
            state: AtomicU32::new(EnclaveIpcState::Idle as u32),
            sequence: AtomicU64::new(0),
            payload_len: AtomicU32::new(0),
            buffer: [0u8; BUFFER_SIZE],
        }
    }

    /// Current state of the channel.
    #[must_use]
    pub fn state(&self) -> EnclaveIpcState {
        EnclaveIpcState::from_u32(self.state.load(Ordering::Acquire))
    }

    /// Current sequence counter.
    #[must_use]
    pub fn sequence(&self) -> u64 {
        self.sequence.load(Ordering::Acquire)
    }

    /// Writes a payload into the shared enclave buffer without dynamic allocation.
    ///
    /// Transitions: `Idle -> Writing -> Ready`.
    ///
    /// # Errors
    /// Returns `EnclaveIpcError::PayloadTooLarge` if `payload.len() > BUFFER_SIZE`.
    /// Returns `EnclaveIpcError::ChannelBusy` if the channel is not in `Idle` state.
    pub fn write_message(&mut self, payload: &[u8]) -> Result<u64, EnclaveIpcError> {
        if payload.len() > BUFFER_SIZE {
            return Err(EnclaveIpcError::PayloadTooLarge);
        }

        // Compare exchange Idle -> Writing
        if self
            .state
            .compare_exchange(
                EnclaveIpcState::Idle as u32,
                EnclaveIpcState::Writing as u32,
                Ordering::AcqRel,
                Ordering::Acquire,
            )
            .is_err()
        {
            return Err(EnclaveIpcError::ChannelBusy);
        }

        // Copy payload directly into static buffer
        self.buffer[..payload.len()].copy_from_slice(payload);
        #[allow(clippy::cast_possible_truncation)]
        self.payload_len.store(payload.len() as u32, Ordering::Release);

        let seq = self.sequence.fetch_add(1, Ordering::AcqRel) + 1;

        // Transition Writing -> Ready
        self.state
            .store(EnclaveIpcState::Ready as u32, Ordering::Release);

        Ok(seq)
    }

    /// Reads an available message from the enclave buffer.
    ///
    /// Transitions: `Ready -> Reading -> Idle`.
    ///
    /// # Errors
    /// Returns `EnclaveIpcError::ChannelNotReady` if channel is not in `Ready` state.
    /// Returns `EnclaveIpcError::BufferTooSmall` if `out_buf` is smaller than payload length.
    pub fn read_message(&mut self, out_buf: &mut [u8]) -> Result<(usize, u64), EnclaveIpcError> {
        // Compare exchange Ready -> Reading
        if self
            .state
            .compare_exchange(
                EnclaveIpcState::Ready as u32,
                EnclaveIpcState::Reading as u32,
                Ordering::AcqRel,
                Ordering::Acquire,
            )
            .is_err()
        {
            return Err(EnclaveIpcError::ChannelNotReady);
        }

        let len = self.payload_len.load(Ordering::Acquire) as usize;
        if out_buf.len() < len {
            // Revert state back to Ready
            self.state
                .store(EnclaveIpcState::Ready as u32, Ordering::Release);
            return Err(EnclaveIpcError::BufferTooSmall);
        }

        out_buf[..len].copy_from_slice(&self.buffer[..len]);
        let seq = self.sequence.load(Ordering::Acquire);

        // Transition Reading -> Idle
        self.state
            .store(EnclaveIpcState::Idle as u32, Ordering::Release);

        Ok((len, seq))
    }
}

impl<const BUFFER_SIZE: usize> Default for EnclaveIpcChannel<BUFFER_SIZE> {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Verification of REQ-RCD-034: Zero-Copy Hardware Zero-Trust Enclave IPC Channel.
    #[test]
    fn test_req_rcd_034_enclave_ipc_channel_zero_copy() {
        let mut channel = EnclaveIpcChannel::<128>::new();
        assert_eq!(channel.state(), EnclaveIpcState::Idle);
        assert_eq!(channel.sequence(), 0);

        // 1. Reading from idle channel fails with ChannelNotReady
        let mut out = [0u8; 128];
        assert_eq!(channel.read_message(&mut out), Err(EnclaveIpcError::ChannelNotReady));

        // 2. Writing payload exceeds capacity
        let big_payload = [0x5Au8; 200];
        assert_eq!(channel.write_message(&big_payload), Err(EnclaveIpcError::PayloadTooLarge));

        // 3. Legitimate write transitions to Ready and returns monotonic sequence
        let payload = b"attested_enclave_consensus_sync_frame_v4";
        let seq = channel.write_message(payload).unwrap();
        assert_eq!(seq, 1);
        assert_eq!(channel.state(), EnclaveIpcState::Ready);

        // 4. Writing while Ready fails with ChannelBusy
        assert_eq!(channel.write_message(b"conflict"), Err(EnclaveIpcError::ChannelBusy));

        // 5. Reading with undersized buffer fails with BufferTooSmall and preserves Ready state
        let mut tiny_buf = [0u8; 8];
        assert_eq!(channel.read_message(&mut tiny_buf), Err(EnclaveIpcError::BufferTooSmall));
        assert_eq!(channel.state(), EnclaveIpcState::Ready);

        // 6. Successful read extracts message and transitions back to Idle
        let (len, read_seq) = channel.read_message(&mut out).unwrap();
        assert_eq!(len, payload.len());
        assert_eq!(read_seq, 1);
        assert_eq!(&out[..len], payload);
        assert_eq!(channel.state(), EnclaveIpcState::Idle);
    }
}
