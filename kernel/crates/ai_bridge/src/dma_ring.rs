#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals, unreachable_patterns)]
//! RunuX AI Bridge — Zero-Copy Hardware DMA Descriptor Ring (REQ-RCD-022)
//!
//! Provides a safe, bounded DMA descriptor ring queue for streaming system call
//! telemetry and tensor payloads directly to co-processors (RVV vector units,
//! PCIe accelerators, hardware security enclaves) without kernel heap allocations.

use core::mem::align_of;

/// Flag indicating hardware ownership of the descriptor.
pub const DMA_DESC_OWN_HW: u32 = 0x01;
/// Flag requesting an interrupt upon DMA completion.
pub const DMA_DESC_INTR: u32 = 0x02;
/// Flag indicating the final descriptor in the circular ring.
pub const DMA_DESC_WRAP: u32 = 0x04;
/// Flag indicating a hardware transmission or DMA parity error.
pub const DMA_DESC_ERR: u32 = 0x08;

/// Default DMA descriptor ring capacity.
pub const DEFAULT_DMA_RING_SIZE: usize = 64;

/// Error variants encountered during DMA descriptor ring operations (REQ-RCD-022).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DmaRingError {
    /// Ring queue is completely full; cannot enqueue further descriptors.
    RingFull,
    /// Ring queue is empty; no completed transfers to reclaim.
    RingEmpty,
    /// Source and destination buffers overlap, which violates DMA memory integrity.
    OverlappingBuffers,
    /// Transfer length is zero.
    ZeroLengthTransfer,
    /// Descriptor memory does not meet the 64-byte alignment requirement.
    MisalignedDescriptor,
    /// Invalid slot index.
    InvalidSlotIndex,
}

/// Hardware DMA descriptor with 64-byte cache line alignment (REQ-RCD-022).
///
/// Matches cache line boundaries on RISC-V RVV and x86_64 architectures,
/// eliminating false sharing between co-processor memory fetches and CPU caches.
#[repr(C, align(64))]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct HardwareDmaDescriptor {
    /// Physical source address.
    pub src_addr: u64,
    /// Physical destination address.
    pub dst_addr: u64,
    /// Transfer length in bytes.
    pub len: u32,
    /// Control and status flags (`DMA_DESC_OWN_HW`, etc.).
    pub flags: u32,
}

impl HardwareDmaDescriptor {
    /// Creates an idle, zero-initialized DMA descriptor.
    #[must_use]
    pub const fn new() -> Self {
        Self {
            src_addr: 0,
            dst_addr: 0,
            len: 0,
            flags: 0,
        }
    }

    /// Checks whether this descriptor is currently owned by the co-processor hardware.
    #[must_use]
    #[inline(always)]
    pub const fn is_hardware_owned(&self) -> bool {
        (self.flags & DMA_DESC_OWN_HW) != 0
    }
}

impl Default for HardwareDmaDescriptor {
    fn default() -> Self {
        Self::new()
    }
}

/// Verifies whether source and destination memory buffers are non-overlapping.
#[must_use]
#[inline(always)]
pub const fn is_non_overlapping(src: u64, dst: u64, len: u32) -> bool {
    let l = len as u64;
    (src.saturating_add(l) <= dst) || (dst.saturating_add(l) <= src)
}

/// Safe, bounded hardware DMA descriptor ring queue (REQ-RCD-022).
pub struct SafeHardwareDmaRing<const N: usize = DEFAULT_DMA_RING_SIZE> {
    descriptors: [HardwareDmaDescriptor; N],
    head: usize,
    tail: usize,
    completed_count: usize,
}

impl<const N: usize> SafeHardwareDmaRing<N> {
    /// Creates a new safe DMA descriptor ring queue.
    #[must_use]
    pub const fn new() -> Self {
        Self {
            descriptors: [HardwareDmaDescriptor::new(); N],
            head: 0,
            tail: 0,
            completed_count: 0,
        }
    }

    /// Enqueues a DMA transfer descriptor, transferring ownership to hardware co-processors.
    ///
    /// # Errors
    /// - `DmaRingError::ZeroLengthTransfer` if `len == 0`
    /// - `DmaRingError::OverlappingBuffers` if `[src, src + len)` and `[dst, dst + len)` overlap
    /// - `DmaRingError::RingFull` if the descriptor queue is full
    pub fn enqueue_transfer(
        &mut self,
        src_addr: u64,
        dst_addr: u64,
        len: u32,
        interrupt: bool,
    ) -> Result<usize, DmaRingError> {
        if len == 0 {
            return Err(DmaRingError::ZeroLengthTransfer);
        }
        if !is_non_overlapping(src_addr, dst_addr, len) {
            return Err(DmaRingError::OverlappingBuffers);
        }

        let next_head = (self.head + 1) % N;
        if next_head == self.tail {
            return Err(DmaRingError::RingFull);
        }

        let slot = self.head;
        let mut flags = DMA_DESC_OWN_HW;
        if interrupt {
            flags |= DMA_DESC_INTR;
        }
        if slot == N - 1 {
            flags |= DMA_DESC_WRAP;
        }

        self.descriptors[slot] = HardwareDmaDescriptor {
            src_addr,
            dst_addr,
            len,
            flags,
        };

        self.head = next_head;
        Ok(slot)
    }

    /// Simulates/records completion of a DMA transfer from hardware.
    ///
    /// # Errors
    /// Returns `DmaRingError::InvalidSlotIndex` if `slot >= N`.
    pub fn mark_completed(&mut self, slot: usize) -> Result<(), DmaRingError> {
        if slot >= N {
            return Err(DmaRingError::InvalidSlotIndex);
        }
        self.descriptors[slot].flags &= !DMA_DESC_OWN_HW;
        self.completed_count = self.completed_count.saturating_add(1);
        Ok(())
    }

    /// Reclaims all contiguous completed descriptors from the tail of the ring.
    pub fn reclaim_completed(&mut self) -> usize {
        let mut reclaimed = 0;
        while self.tail != self.head {
            if self.descriptors[self.tail].is_hardware_owned() {
                break;
            }
            self.tail = (self.tail + 1) % N;
            reclaimed += 1;
        }
        reclaimed
    }

    /// Returns the number of currently active transfers in flight.
    #[must_use]
    pub const fn in_flight(&self) -> usize {
        if self.head >= self.tail {
            self.head - self.tail
        } else {
            N - (self.tail - self.head)
        }
    }

    /// Returns a reference to a specific descriptor slot.
    #[must_use]
    pub fn get_descriptor(&self, slot: usize) -> Option<&HardwareDmaDescriptor> {
        self.descriptors.get(slot)
    }
}

impl<const N: usize> Default for SafeHardwareDmaRing<N> {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Verification of REQ-RCD-022: Zero-Copy Hardware DMA Descriptor Ring.
    #[test]
    fn test_req_rcd_022_hardware_dma_ring_descriptor_ownership() {
        // 1. Verify 64-byte alignment
        assert_eq!(align_of::<HardwareDmaDescriptor>(), 64);

        let mut ring = SafeHardwareDmaRing::<8>::new();
        assert_eq!(ring.in_flight(), 0);

        // 2. Reject zero-length transfer
        let err_zero = ring.enqueue_transfer(0x1000, 0x2000, 0, false);
        assert_eq!(err_zero, Err(DmaRingError::ZeroLengthTransfer));

        // 3. Reject overlapping buffers
        let err_overlap = ring.enqueue_transfer(0x1000, 0x1050, 0x100, false);
        assert_eq!(err_overlap, Err(DmaRingError::OverlappingBuffers));

        // 4. Enqueue legitimate transfers
        let s0 = ring.enqueue_transfer(0x1000, 0x5000, 0x200, true).expect("Enqueued slot 0");
        assert_eq!(s0, 0);
        let s1 = ring.enqueue_transfer(0x3000, 0x7000, 0x400, false).expect("Enqueued slot 1");
        assert_eq!(s1, 1);

        assert_eq!(ring.in_flight(), 2);
        assert!(ring.get_descriptor(s0).unwrap().is_hardware_owned());
        assert_eq!(ring.get_descriptor(s0).unwrap().flags & DMA_DESC_INTR, DMA_DESC_INTR);

        // 5. Hardware marks s0 completed
        ring.mark_completed(s0).expect("Mark completed");
        assert!(!ring.get_descriptor(s0).unwrap().is_hardware_owned());

        // 6. Reclaim advances tail
        let rec = ring.reclaim_completed();
        assert_eq!(rec, 1);
        assert_eq!(ring.in_flight(), 1);

        // 7. Complete s1 and reclaim
        ring.mark_completed(s1).expect("Mark completed");
        let rec2 = ring.reclaim_completed();
        assert_eq!(rec2, 1);
        assert_eq!(ring.in_flight(), 0);
    }
}
