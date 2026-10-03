//! Lock-free Single-Producer Single-Consumer (SPSC) Ring Buffer for Kernel Audit Events
//!
//! Provides a zero-allocation, lock-free circular buffer operating in `#![no_std]`.
//! Designed for real-time streaming of `SyscallAuditEvent` structures from the Ring 0
//! syscall interception hook to the `ai_detector` TinyML classification pipeline.

use core::cell::UnsafeCell;
use core::mem::MaybeUninit;
use core::sync::atomic::{AtomicUsize, Ordering};

/// A lock-free SPSC circular ring buffer with power-of-two capacity.
///
/// # Invariants
/// - Capacity `CAP` must be a power of two (`CAP > 0 && (CAP & (CAP - 1)) == 0`).
/// - Single-producer on `push`, single-consumer on `pop`.
pub struct LockFreeAuditRingBuffer<T, const CAP: usize> {
    buffer: UnsafeCell<[MaybeUninit<T>; CAP]>,
    head: AtomicUsize,
    tail: AtomicUsize,
    dropped: AtomicUsize,
}

// SAFETY: Synchronization of slot access is guaranteed by Acquire-Release atomics
// on `head` and `tail`, ensuring data-race free access between one producer and one consumer.
unsafe impl<T: Send, const CAP: usize> Sync for LockFreeAuditRingBuffer<T, CAP> {}
unsafe impl<T: Send, const CAP: usize> Send for LockFreeAuditRingBuffer<T, CAP> {}

impl<T, const CAP: usize> LockFreeAuditRingBuffer<T, CAP> {
    /// Creates a new, uninitialized lock-free ring buffer.
    ///
    /// Compile-time check ensures `CAP` is a non-zero power of two.
    #[must_use]
    pub const fn new() -> Self {
        assert!(CAP > 0, "Capacity must be greater than zero");
        assert!((CAP & (CAP - 1)) == 0, "Capacity must be a power of two");

        Self {
            buffer: UnsafeCell::new([const { MaybeUninit::uninit() }; CAP]),
            head: AtomicUsize::new(0),
            tail: AtomicUsize::new(0),
            dropped: AtomicUsize::new(0),
        }
    }

    /// Returns the capacity of the ring buffer.
    #[inline(always)]
    pub const fn capacity(&self) -> usize {
        CAP
    }

    /// Checks if the ring buffer is empty.
    #[inline]
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Checks if the ring buffer is currently full.
    #[inline]
    pub fn is_full(&self) -> bool {
        self.len() >= CAP
    }

    /// Returns the current number of items waiting in the buffer.
    #[inline]
    pub fn len(&self) -> usize {
        let head = self.head.load(Ordering::Relaxed);
        let tail = self.tail.load(Ordering::Relaxed);
        head.wrapping_sub(tail)
    }

    /// Returns the total count of events dropped due to buffer saturation.
    #[inline]
    pub fn dropped_count(&self) -> usize {
        self.dropped.load(Ordering::Relaxed)
    }

    /// Pushes an item into the buffer.
    ///
    /// Returns `Ok(())` on success, or `Err(item)` if the buffer is full.
    pub fn push(&self, item: T) -> Result<(), T> {
        let head = self.head.load(Ordering::Relaxed);
        let tail = self.tail.load(Ordering::Acquire);

        if head.wrapping_sub(tail) >= CAP {
            self.dropped.fetch_add(1, Ordering::Relaxed);
            return Err(item);
        }

        let slot = head & (CAP - 1);
        // SAFETY: slot is strictly bounded by (CAP - 1) via power-of-two mask. The head atomic
        // is updated with Release ordering after the write, guaranteeing single-producer exclusivity.
        unsafe {
            let buffer_ptr = self.buffer.get() as *mut MaybeUninit<T>;
            (*buffer_ptr.add(slot)).write(item);
        }

        self.head.store(head.wrapping_add(1), Ordering::Release);
        Ok(())
    }

    /// Pushes an item into the buffer, overwriting the oldest unread element if full.
    ///
    /// Returns `true` if an older element was dropped to make room.
    ///
    /// # SPSC Invariant Note
    ///
    /// In a strict single-producer / single-consumer (SPSC) ring buffer the `tail` cursor is
    /// owned **exclusively** by the consumer. This method advances `tail` from the producer
    /// side, which is safe **only** when no concurrent consumer pop is in flight (i.e., when
    /// the Ring 0 cooperative scheduler guarantees that consumer and producer cannot overlap).
    /// Do **not** call this from a concurrent multi-threaded context where a consumer may be
    /// executing `pop()` simultaneously.
    pub fn push_overwrite(&self, item: T) -> bool {
        let head = self.head.load(Ordering::Relaxed);
        let tail = self.tail.load(Ordering::Acquire);
        let mut overwritten = false;

        if head.wrapping_sub(tail) >= CAP {
            // Advance tail to drop the oldest item
            self.tail.store(tail.wrapping_add(1), Ordering::Release);
            self.dropped.fetch_add(1, Ordering::Relaxed);
            overwritten = true;
        }

        let slot = head & (CAP - 1);
        // SAFETY: slot is strictly bounded by (CAP - 1). Access is localized to the producer thread,
        // and head is incremented with Release ordering.
        unsafe {
            let buffer_ptr = self.buffer.get() as *mut MaybeUninit<T>;
            (*buffer_ptr.add(slot)).write(item);
        }

        self.head.store(head.wrapping_add(1), Ordering::Release);
        overwritten
    }

    /// Pops the next item from the buffer.
    ///
    /// Returns `Some(item)` if available, or `None` if the buffer is empty.
    pub fn pop(&self) -> Option<T> {
        let tail = self.tail.load(Ordering::Relaxed);
        let head = self.head.load(Ordering::Acquire);

        if tail == head {
            return None;
        }

        let slot = tail & (CAP - 1);
        // SAFETY: slot is strictly bounded by (CAP - 1). Because tail != head under Acquire ordering,
        // the slot contains a valid, initialized item previously committed by push.
        let item = unsafe {
            let buffer_ptr = self.buffer.get() as *const MaybeUninit<T>;
            (*buffer_ptr.add(slot)).assume_init_read()
        };

        self.tail.store(tail.wrapping_add(1), Ordering::Release);
        Some(item)
    }
}

// ---------------------------------------------------------------------------
// REQ-RCD-030: Multi-Core Pre-Dispatch Sharded Lock-Free Telemetry Ring
// ---------------------------------------------------------------------------

/// Per-CPU sharded circular ring buffers eliminating cross-core cache line bouncing (REQ-RCD-030).
pub struct PerCpuRingArray<T, const CORES: usize, const CAP: usize> {
    shards: [LockFreeAuditRingBuffer<T, CAP>; CORES],
}

// SAFETY: Each shard is a LockFreeAuditRingBuffer with safe atomics; distinct CPU cores
// access distinct shards via modulo routing, ensuring no data races across cores.
unsafe impl<T: Send, const CORES: usize, const CAP: usize> Sync for PerCpuRingArray<T, CORES, CAP> {}
unsafe impl<T: Send, const CORES: usize, const CAP: usize> Send for PerCpuRingArray<T, CORES, CAP> {}

impl<T, const CORES: usize, const CAP: usize> PerCpuRingArray<T, CORES, CAP> {
    /// Creates a new per-CPU sharded ring array.
    #[must_use]
    pub const fn new() -> Self {
        assert!(CORES > 0, "Core count must be greater than zero");
        Self {
            shards: [const { LockFreeAuditRingBuffer::new() }; CORES],
        }
    }

    /// Pushes an item to the shard assigned to `cpu_id`.
    ///
    /// # Errors
    /// Returns `Err(item)` if the assigned core's buffer is full.
    pub fn push_on_cpu(&self, cpu_id: usize, item: T) -> Result<(), T> {
        let shard_idx = cpu_id % CORES;
        self.shards[shard_idx].push(item)
    }

    /// Pops an item from the shard assigned to `cpu_id`.
    pub fn pop_on_cpu(&self, cpu_id: usize) -> Option<T> {
        let shard_idx = cpu_id % CORES;
        self.shards[shard_idx].pop()
    }

    /// Returns the current occupancy of the shard assigned to `cpu_id`.
    #[must_use]
    pub fn len_on_cpu(&self, cpu_id: usize) -> usize {
        let shard_idx = cpu_id % CORES;
        self.shards[shard_idx].len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Verification of REQ-RCD-002: Lock-Free SPSC FIFO Ordering and Boundedness.
    #[test]
    fn test_ring_buffer_fifo() {
        let rb = LockFreeAuditRingBuffer::<u64, 4>::new();
        assert!(rb.is_empty());
        assert_eq!(rb.len(), 0);

        assert!(rb.push(10).is_ok());
        assert!(rb.push(20).is_ok());
        assert_eq!(rb.len(), 2);

        assert_eq!(rb.pop(), Some(10));
        assert_eq!(rb.pop(), Some(20));
        assert_eq!(rb.pop(), None);
        assert!(rb.is_empty());
    }

    /// Verification of REQ-RCD-002: Lock-Free SPSC Overflow and Non-Blocking Overwrite Eviction.
    #[test]
    fn test_ring_buffer_full_and_overwrite() {
        let rb = LockFreeAuditRingBuffer::<u32, 4>::new();
        assert!(rb.push(1).is_ok());
        assert!(rb.push(2).is_ok());
        assert!(rb.push(3).is_ok());
        assert!(rb.push(4).is_ok());

        // Full: standard push should fail
        assert_eq!(rb.push(5), Err(5));
        assert_eq!(rb.dropped_count(), 1);

        // Overwrite should succeed and evict 1
        assert!(rb.push_overwrite(5));
        assert_eq!(rb.dropped_count(), 2);

        assert_eq!(rb.pop(), Some(2));
        assert_eq!(rb.pop(), Some(3));
        assert_eq!(rb.pop(), Some(4));
        assert_eq!(rb.pop(), Some(5));
        assert_eq!(rb.pop(), None);
    }

    /// `len()` returns correct count after wrap-around.
    #[test]
    fn test_ring_buffer_len_after_wrap() {
        let rb = LockFreeAuditRingBuffer::<u32, 4>::new();
        // Fill and drain once
        for i in 0..4u32 {
            rb.push(i).unwrap();
        }
        for _ in 0..4 {
            rb.pop();
        }
        // Fill again (indices now wrap)
        rb.push(10).unwrap();
        rb.push(20).unwrap();
        assert_eq!(rb.len(), 2);
        assert_eq!(rb.pop(), Some(10));
        assert_eq!(rb.len(), 1);
    }

    /// `dropped_count` accumulates precisely across multiple overwrite events.
    #[test]
    fn test_dropped_count_precision() {
        let rb = LockFreeAuditRingBuffer::<u32, 4>::new();
        for i in 0..4u32 {
            rb.push(i).unwrap();
        }
        // Each push_overwrite on a full buffer increments dropped by 1
        rb.push_overwrite(99);
        rb.push_overwrite(100);
        // 1 from failed push in earlier test path + 2 from push_overwrite
        // In this isolated test only push_overwrite drops are counted
        assert_eq!(rb.dropped_count(), 2);
    }

    /// Verification of REQ-RCD-030: Multi-Core Pre-Dispatch Sharded Lock-Free Telemetry Ring.
    #[test]
    fn test_req_rcd_030_per_cpu_sharded_ring_isolation() {
        let sharded = PerCpuRingArray::<u64, 4, 4>::new();

        // Push to CPU 0
        assert_eq!(sharded.push_on_cpu(0, 100), Ok(()));
        assert_eq!(sharded.push_on_cpu(0, 101), Ok(()));
        assert_eq!(sharded.len_on_cpu(0), 2);

        // CPU 1, 2, 3 remain empty (shard isolation)
        assert_eq!(sharded.len_on_cpu(1), 0);
        assert_eq!(sharded.len_on_cpu(2), 0);
        assert_eq!(sharded.len_on_cpu(3), 0);

        // Push to CPU 2
        assert_eq!(sharded.push_on_cpu(2, 200), Ok(()));
        assert_eq!(sharded.len_on_cpu(2), 1);

        // Pop from CPU 0
        assert_eq!(sharded.pop_on_cpu(0), Some(100));
        assert_eq!(sharded.pop_on_cpu(0), Some(101));
        assert_eq!(sharded.pop_on_cpu(0), None);

        // Pop from CPU 2
        assert_eq!(sharded.pop_on_cpu(2), Some(200));
        assert_eq!(sharded.pop_on_cpu(2), None);
    }
}

