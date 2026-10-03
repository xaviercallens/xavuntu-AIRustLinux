#![no_std]

//! T-Ring (Tensor-Ring) Lock-Free Execution
//!
//! A lock-free submission queue mapped directly to TPU hardware doorbells.
//! Replaces legacy `ioctl()` syscalls. Submits XLA HLO operation descriptors
//! from Ring-0 without VFS overhead.

use core::sync::atomic::{AtomicU32, Ordering};

/// XLA HLO Operation Descriptor
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct HloDescriptor {
    pub op_code: u32,
    pub tensor_addr: u64,
    pub size: u32,
}

const RING_SIZE: usize = 256;

/// Lock-free T-Ring submission queue.
pub struct TRing {
    head: AtomicU32,
    tail: AtomicU32,
    buffer: [HloDescriptor; RING_SIZE],
    doorbell_ptr: *mut u32,
}

impl TRing {
    /// Initializes a new T-Ring.
    pub fn new(doorbell_addr: u64) -> Self {
        Self {
            head: AtomicU32::new(0),
            tail: AtomicU32::new(0),
            buffer: [HloDescriptor { op_code: 0, tensor_addr: 0, size: 0 }; RING_SIZE],
            doorbell_ptr: doorbell_addr as *mut u32,
        }
    }

    /// Submits an HLO descriptor to the queue and rings the doorbell.
    pub fn submit(&mut self, desc: HloDescriptor) -> Result<(), &'static str> {
        let current_tail = self.tail.load(Ordering::Relaxed);
        let next_tail = (current_tail + 1) % (RING_SIZE as u32);

        if next_tail == self.head.load(Ordering::Acquire) {
            return Err("T-Ring is full");
        }

        self.buffer[current_tail as usize] = desc;
        self.tail.store(next_tail, Ordering::Release);

        // Ring the hardware doorbell (mock)
        // SAFETY: We assume the doorbell pointer is valid MMIO.
        unsafe {
            core::ptr::write_volatile(self.doorbell_ptr, next_tail);
        }

        Ok(())
    }
}

unsafe impl Send for TRing {}
unsafe impl Sync for TRing {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tring_submit() {
        let mut doorbell = 0u32;
        let mut tring = TRing::new(&mut doorbell as *mut u32 as u64);
        
        let desc = HloDescriptor {
            op_code: 1,
            tensor_addr: 0x1000,
            size: 128,
        };
        
        assert!(tring.submit(desc).is_ok());
        assert_eq!(tring.tail.load(Ordering::Relaxed), 1);
    }
}
