//! RunuX GPU Compute Subsystem - DRM & Fences
//!
//! Provides bare-metal Direct Rendering Manager (DRM) equivalents:
//! ring buffer management and monotonic asynchronous fences.

#![no_std]
#![deny(clippy::all)]

use gpu_types::{SafeDmaFence, SafeRingIndex};
use core::sync::atomic::{AtomicBool, Ordering};

/// DRM Error types
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DrmError {
    RingFull,
    InvalidRingSize,
    FenceWaitTimeout,
}

/// GPU Command Packet structure
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GpuCommandPacket {
    pub opcode: u32,
    pub flags: u32,
    pub payload_addr: u64,
    pub payload_size: u64,
}

impl GpuCommandPacket {
    pub const fn empty() -> Self {
        Self {
            opcode: 0,
            flags: 0,
            payload_addr: 0,
            payload_size: 0,
        }
    }
}

/// Hardware Ring Buffer Manager (Theorems 13.5 & 13.6)
#[derive(Debug)]
pub struct DrmRingBuffer<const SIZE: usize> {
    index: SafeRingIndex,
    commands: [GpuCommandPacket; SIZE],
    is_active: AtomicBool,
}

impl<const SIZE: usize> DrmRingBuffer<SIZE> {
    pub fn new() -> Result<Self, DrmError> {
        let index = SafeRingIndex::new(SIZE).map_err(|_| DrmError::InvalidRingSize)?;
        Ok(Self {
            index,
            commands: [GpuCommandPacket::empty(); SIZE],
            is_active: AtomicBool::new(false),
        })
    }

    pub fn is_full(&self) -> bool {
        // Simple full check: if advancing head hits tail
        let next_head = (self.index.head_bounded() + 1) % SIZE;
        next_head == self.index.tail_bounded()
    }

    pub fn submit(&mut self, cmd: GpuCommandPacket) -> Result<(), DrmError> {
        if self.is_full() {
            return Err(DrmError::RingFull);
        }

        let slot = self.index.advance_head();
        self.commands[slot] = cmd;
        self.is_active.store(true, Ordering::Release);
        
        Ok(())
    }

    pub fn consume(&mut self) -> Option<GpuCommandPacket> {
        if self.index.head_bounded() == self.index.tail_bounded() {
            self.is_active.store(false, Ordering::Release);
            return None;
        }

        let slot = self.index.advance_tail();
        let cmd = self.commands[slot];
        self.commands[slot] = GpuCommandPacket::empty();
        
        Some(cmd)
    }

    pub fn is_active(&self) -> bool {
        self.is_active.load(Ordering::Acquire)
    }
}

/// DRM Subsystem Context
#[derive(Debug)]
pub struct DrmContext {
    context_id: u32,
    fence: SafeDmaFence,
}

impl DrmContext {
    pub const fn new(context_id: u32) -> Self {
        Self {
            context_id,
            fence: SafeDmaFence::new(context_id, 0),
        }
    }

    pub fn context_id(&self) -> u32 {
        self.context_id
    }

    pub fn emit_fence(&self) -> u64 {
        self.fence.signal_next()
    }

    pub fn check_fence(&self, seqno: u64) -> bool {
        self.fence.is_completed(seqno)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_drm_ring_buffer() {
        let mut ring = DrmRingBuffer::<4>::new().unwrap();
        assert!(!ring.is_active());

        // Submit 3 commands (size - 1 to distinguish full from empty)
        let cmd1 = GpuCommandPacket { opcode: 1, flags: 0, payload_addr: 0x1000, payload_size: 256 };
        let cmd2 = GpuCommandPacket { opcode: 2, flags: 0, payload_addr: 0x2000, payload_size: 512 };
        let cmd3 = GpuCommandPacket { opcode: 3, flags: 0, payload_addr: 0x3000, payload_size: 1024 };

        assert!(ring.submit(cmd1).is_ok());
        assert!(ring.submit(cmd2).is_ok());
        assert!(ring.submit(cmd3).is_ok());
        
        assert!(ring.is_active());
        assert!(ring.is_full());
        assert_eq!(ring.submit(cmd1), Err(DrmError::RingFull));

        assert_eq!(ring.consume(), Some(cmd1));
        assert_eq!(ring.consume(), Some(cmd2));
        assert_eq!(ring.consume(), Some(cmd3));
        assert_eq!(ring.consume(), None);
        
        assert!(!ring.is_active());
    }

    #[test]
    fn test_drm_fences() {
        let ctx = DrmContext::new(42);
        assert_eq!(ctx.context_id(), 42);

        let seq1 = ctx.emit_fence();
        assert_eq!(seq1, 1);
        assert!(ctx.check_fence(1));
        assert!(!ctx.check_fence(2));

        let seq2 = ctx.emit_fence();
        assert_eq!(seq2, 2);
        assert!(ctx.check_fence(2));
    }
}
