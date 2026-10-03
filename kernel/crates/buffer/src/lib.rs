#![no_std]
#![deny(clippy::all)]
#![warn(clippy::pedantic)]

//! High-Performance Circular DMA Buffer Subsystem
//!
//! Provides lockless and spinlock-synchronized circular ring buffers
//! for zero-copy direct memory access (DMA) packet transmission and reception.
//! Backed by `NetBuf` abstractions and hardware DMA descriptor representations.

#[cfg(test)]
extern crate std;

use core::ffi::c_int;
use core::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use kernel_types::SpinLock;

/// DMA descriptor representing physical memory address, length, and transfer flags.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DmaDescriptor {
    pub addr: u64,
    pub len: u32,
    pub flags: u32,
}

impl DmaDescriptor {
    pub const FLAG_DEVICE_OWNED: u32 = 1 << 0;
    pub const FLAG_END_OF_PACKET: u32 = 1 << 1;
    pub const FLAG_ERROR: u32 = 1 << 2;
    pub const FLAG_INTERRUPT: u32 = 1 << 3;

    /// Construct a new DMA descriptor.
    #[must_use]
    pub const fn new(addr: u64, len: u32, flags: u32) -> Self {
        Self { addr, len, flags }
    }

    /// Construct an empty (zeroed) DMA descriptor.
    #[must_use]
    pub const fn empty() -> Self {
        Self { addr: 0, len: 0, flags: 0 }
    }

    /// Check if the descriptor is currently owned by the DMA hardware device.
    #[must_use]
    pub const fn is_device_owned(&self) -> bool {
        (self.flags & Self::FLAG_DEVICE_OWNED) != 0
    }

    /// Check if this buffer marks the end of an egress/ingress frame.
    #[must_use]
    pub const fn is_end_of_packet(&self) -> bool {
        (self.flags & Self::FLAG_END_OF_PACKET) != 0
    }

    /// Check if hardware signaled a DMA transfer or checksum error.
    #[must_use]
    pub const fn has_error(&self) -> bool {
        (self.flags & Self::FLAG_ERROR) != 0
    }

    /// Set or clear device ownership flag.
    pub fn set_device_owned(&mut self, owned: bool) {
        if owned {
            self.flags |= Self::FLAG_DEVICE_OWNED;
        } else {
            self.flags &= !Self::FLAG_DEVICE_OWNED;
        }
    }
}

/// Buffer operation errors.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BufferError {
    /// Ring buffer capacity is exhausted.
    Full,
    /// Ring buffer contains no available descriptors.
    Empty,
    /// Buffer capacity must be a positive power of two.
    InvalidCapacity,
    /// Buffer subsystem is not initialized.
    NotInitialized,
    /// Invalid packet buffer size.
    InvalidSize,
}

/// Circular DMA descriptor ring buffer of power-of-two capacity `CAP`.
pub struct CircularDmaBuffer<const CAP: usize> {
    descriptors: SpinLock<[DmaDescriptor; CAP]>,
    head: AtomicUsize,
    tail: AtomicUsize,
}

impl<const CAP: usize> CircularDmaBuffer<CAP> {
    /// Create a new circular DMA buffer.
    ///
    /// # Panics
    /// Panics if `CAP` is zero or not a power of two.
    #[must_use]
    pub const fn new() -> Self {
        assert!(CAP > 0 && (CAP & (CAP - 1)) == 0, "Capacity must be a power of two");
        Self {
            descriptors: SpinLock::new([DmaDescriptor::empty(); CAP]),
            head: AtomicUsize::new(0),
            tail: AtomicUsize::new(0),
        }
    }

    /// Buffer capacity.
    #[must_use]
    pub const fn capacity(&self) -> usize {
        CAP
    }

    /// Current number of occupied slots in the ring.
    #[must_use]
    pub fn len(&self) -> usize {
        let head = self.head.load(Ordering::Acquire);
        let tail = self.tail.load(Ordering::Acquire);
        tail.wrapping_sub(head)
    }

    /// True if the ring buffer contains no descriptors.
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// True if the ring buffer is completely full.
    #[must_use]
    pub fn is_full(&self) -> bool {
        self.len() >= CAP
    }

    /// Number of available slots remaining in the ring buffer.
    #[must_use]
    pub fn available_space(&self) -> usize {
        CAP.saturating_sub(self.len())
    }

    /// Enqueue a DMA descriptor into the ring buffer.
    ///
    /// # Errors
    /// Returns `BufferError::Full` if no free descriptor slots are available.
    pub fn enqueue(&self, desc: DmaDescriptor) -> Result<(), BufferError> {
        let mut descs = self.descriptors.lock();
        let head = self.head.load(Ordering::Acquire);
        let tail = self.tail.load(Ordering::Acquire);

        if tail.wrapping_sub(head) >= CAP {
            return Err(BufferError::Full);
        }

        let index = tail & (CAP - 1);
        descs[index] = desc;
        self.tail.store(tail.wrapping_add(1), Ordering::Release);
        Ok(())
    }

    /// Dequeue a completed DMA descriptor from the ring buffer.
    ///
    /// # Errors
    /// Returns `BufferError::Empty` if the buffer contains no ready descriptors.
    pub fn dequeue(&self) -> Result<DmaDescriptor, BufferError> {
        let descs = self.descriptors.lock();
        let head = self.head.load(Ordering::Acquire);
        let tail = self.tail.load(Ordering::Acquire);

        if head == tail {
            return Err(BufferError::Empty);
        }

        let index = head & (CAP - 1);
        let desc = descs[index];
        self.head.store(head.wrapping_add(1), Ordering::Release);
        Ok(desc)
    }

    /// Inspect the descriptor at the front of the queue without removing it.
    ///
    /// # Errors
    /// Returns `BufferError::Empty` if the queue is empty.
    pub fn peek(&self) -> Result<DmaDescriptor, BufferError> {
        let descs = self.descriptors.lock();
        let head = self.head.load(Ordering::Acquire);
        let tail = self.tail.load(Ordering::Acquire);

        if head == tail {
            return Err(BufferError::Empty);
        }

        let index = head & (CAP - 1);
        Ok(descs[index])
    }

    /// Enqueue a zero-copy packet buffer as a DMA descriptor.
    ///
    /// # Errors
    /// Returns `BufferError::InvalidSize` if buffer length is zero,
    /// or `BufferError::Full` if descriptor ring is full.
    pub fn enqueue_netbuf(&self, buf: &kernel_types::NetBuf) -> Result<(), BufferError> {
        if buf.is_empty() {
            return Err(BufferError::InvalidSize);
        }

        let desc = DmaDescriptor::new(
            buf.as_ptr() as u64,
            buf.len() as u32,
            DmaDescriptor::FLAG_END_OF_PACKET | DmaDescriptor::FLAG_DEVICE_OWNED,
        );
        self.enqueue(desc)
    }

    /// Reset head and tail indices and zero all descriptor slots.
    pub fn reset(&self) {
        let mut descs = self.descriptors.lock();
        for desc in descs.iter_mut() {
            *desc = DmaDescriptor::empty();
        }
        self.head.store(0, Ordering::Release);
        self.tail.store(0, Ordering::Release);
    }
}

pub static BUFFER_INITIALIZED: AtomicBool = AtomicBool::new(false);

/// Module initialization
#[no_mangle]
// SAFETY: Atomic store initializes module flag without data race.
pub unsafe extern "C" fn buffer_init() -> c_int {
    BUFFER_INITIALIZED.store(true, Ordering::Release);
    0
}

/// Module cleanup
#[no_mangle]
// SAFETY: Atomic store clears module flag cleanly upon exit.
pub unsafe extern "C" fn buffer_exit() {
    BUFFER_INITIALIZED.store(false, Ordering::Release);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_buffer_init_exit() {
        // SAFETY: Exercising C-ABI lifecycle functions in test suite.
        unsafe {
            assert_eq!(buffer_init(), 0);
            assert!(BUFFER_INITIALIZED.load(Ordering::Acquire));
            buffer_exit();
            assert!(!BUFFER_INITIALIZED.load(Ordering::Acquire));
        }
    }

    #[test]
    fn test_dma_descriptor_flags() {
        let mut desc = DmaDescriptor::new(0x1000_0000, 1514, DmaDescriptor::FLAG_DEVICE_OWNED | DmaDescriptor::FLAG_END_OF_PACKET);
        assert!(desc.is_device_owned());
        assert!(desc.is_end_of_packet());
        assert!(!desc.has_error());

        desc.set_device_owned(false);
        assert!(!desc.is_device_owned());

        desc.flags |= DmaDescriptor::FLAG_ERROR;
        assert!(desc.has_error());
    }

    #[test]
    fn test_circular_buffer_basic_enqueue_dequeue() {
        let ring = CircularDmaBuffer::<4>::new();
        assert_eq!(ring.capacity(), 4);
        assert_eq!(ring.len(), 0);
        assert!(ring.is_empty());
        assert!(!ring.is_full());

        let d1 = DmaDescriptor::new(0x1000, 64, 0);
        let d2 = DmaDescriptor::new(0x2000, 128, 0);

        assert!(ring.enqueue(d1).is_ok());
        assert_eq!(ring.len(), 1);
        assert_eq!(ring.available_space(), 3);

        assert!(ring.enqueue(d2).is_ok());
        assert_eq!(ring.len(), 2);
        assert_eq!(ring.available_space(), 2);

        assert_eq!(ring.dequeue(), Ok(d1));
        assert_eq!(ring.len(), 1);

        assert_eq!(ring.dequeue(), Ok(d2));
        assert_eq!(ring.len(), 0);
        assert!(ring.is_empty());
    }

    #[test]
    fn test_circular_buffer_full_and_empty() {
        let ring = CircularDmaBuffer::<4>::new();

        for i in 0..4 {
            let desc = DmaDescriptor::new(i as u64 * 0x1000, 64, 0);
            assert!(ring.enqueue(desc).is_ok());
        }

        assert!(ring.is_full());
        assert_eq!(ring.len(), 4);
        assert_eq!(ring.available_space(), 0);

        // Enqueue on full ring should fail
        let extra = DmaDescriptor::new(0x5000, 64, 0);
        assert_eq!(ring.enqueue(extra), Err(BufferError::Full));

        // Drain ring
        for i in 0..4 {
            let res = ring.dequeue();
            assert!(res.is_ok());
            assert_eq!(res.unwrap().addr, i as u64 * 0x1000);
        }

        assert!(ring.is_empty());
        assert_eq!(ring.dequeue(), Err(BufferError::Empty));
    }

    #[test]
    fn test_circular_buffer_index_wrapping() {
        let ring = CircularDmaBuffer::<4>::new();

        // Perform 40 enqueue/dequeue cycles to force wrap-around
        for cycle in 0..40 {
            let desc = DmaDescriptor::new(cycle as u64, 100, 0);
            assert!(ring.enqueue(desc).is_ok());
            let out = ring.dequeue();
            assert_eq!(out, Ok(desc));
        }
        assert!(ring.is_empty());
    }

    #[test]
    fn test_circular_buffer_peek() {
        let ring = CircularDmaBuffer::<4>::new();
        let desc = DmaDescriptor::new(0xCAFE_BABE, 256, 0);

        assert_eq!(ring.peek(), Err(BufferError::Empty));
        assert!(ring.enqueue(desc).is_ok());

        assert_eq!(ring.peek(), Ok(desc));
        assert_eq!(ring.len(), 1); // Peek does not consume

        assert_eq!(ring.dequeue(), Ok(desc));
        assert!(ring.is_empty());
    }

    #[test]
    fn test_circular_buffer_reset() {
        let ring = CircularDmaBuffer::<4>::new();
        let d = DmaDescriptor::new(0x1000, 64, 0);
        assert!(ring.enqueue(d).is_ok());
        assert_eq!(ring.len(), 1);

        ring.reset();
        assert_eq!(ring.len(), 0);
        assert!(ring.is_empty());
        assert_eq!(ring.dequeue(), Err(BufferError::Empty));
    }

    #[test]
    fn test_circular_buffer_enqueue_netbuf() {
        let ring = CircularDmaBuffer::<4>::new();
        let mut raw_mem = [0u8; 128];

        // SAFETY: raw_mem is 128 bytes on the stack.
        let mut netbuf = unsafe {
            kernel_types::NetBuf::from_raw_parts(raw_mem.as_mut_ptr(), 128, 16)
        }.expect("from_raw_parts failed");
        assert_eq!(ring.enqueue_netbuf(&netbuf), Err(BufferError::InvalidSize));

        {
            let payload = netbuf.put(48).expect("put failed");
            payload.fill(0x55);
        }

        assert!(ring.enqueue_netbuf(&netbuf).is_ok());
        assert_eq!(ring.len(), 1);

        let desc = ring.dequeue().expect("dequeue failed");
        assert_eq!(desc.addr, netbuf.as_ptr() as u64);
        assert_eq!(desc.len, 48);
        assert!(desc.is_end_of_packet());
        assert!(desc.is_device_owned());
    }
}
