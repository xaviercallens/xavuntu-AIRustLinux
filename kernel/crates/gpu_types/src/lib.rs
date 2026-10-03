//! RunuX GPU Compute Subsystem - Fundamental Types & C ABI Layer
//!
//! Provides `#![no_std]` definitions, bit-exact C ABI structures, and safe abstractions
//! matching the Lean 4 formal mathematical specifications in `specs/lean4/MVK/Phase13/GpuCompute.lean`.

#![no_std]
#![deny(clippy::all)]

use core::sync::atomic::{AtomicU64, Ordering};

/// PCI Resizable BAR (ReBAR) configuration structure matching hardware layout.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PciBarConfig {
    pub bar_index: u8,
    pub is_64bit: bool,
    pub is_prefetchable: bool,
    pub _reserved: u8,
    pub base_address: u64,
    pub size_bytes: u64,
}

impl PciBarConfig {
    pub const fn new(bar_index: u8, is_64bit: bool, is_prefetchable: bool, base_address: u64, size_bytes: u64) -> Self {
        Self {
            bar_index,
            is_64bit,
            is_prefetchable,
            _reserved: 0,
            base_address,
            size_bytes,
        }
    }

    /// Check whether a physical address is within the BAR window.
    pub fn contains_address(&self, addr: u64) -> bool {
        addr >= self.base_address && addr < (self.base_address.saturating_add(self.size_bytes))
    }
}

/// GPU DMA Transaction Descriptor crossing the hardware-software boundary.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GpuDmaDescriptor {
    pub device_id: u32,
    pub _padding0: u32,
    pub host_physical_addr: u64,
    pub device_vram_addr: u64,
    pub byte_count: u64,
    pub flags: u32,
    pub fence_seq: u64,
}

/// Hardware IOMMU Protection Domain bounds.
/// Strictly enforces isolation preventing DMA transactions from accessing Ring 0 kernel space.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IommuDomainSlot {
    pub domain_id: u32,
    pub device_id: u32,
    pub allowed_base: u64,
    pub allowed_length: u64,
}

impl IommuDomainSlot {
    pub const fn new(domain_id: u32, device_id: u32, allowed_base: u64, allowed_length: u64) -> Self {
        Self {
            domain_id,
            device_id,
            allowed_base,
            allowed_length,
        }
    }

    /// Validates whether a DMA request is strictly authorized within the domain slot.
    /// Implements invariant REQ-GPU-001 proven in Lean 4 Theorem 13.2 (`iommu_dma_isolation_guarantee`).
    pub fn is_dma_authorized(&self, tx: &GpuDmaDescriptor) -> bool {
        if self.device_id != tx.device_id {
            return false;
        }

        let tx_end = match tx.host_physical_addr.checked_add(tx.byte_count) {
            Some(end) => end,
            None => return false,
        };

        let slot_end = match self.allowed_base.checked_add(self.allowed_length) {
            Some(end) => end,
            None => return false,
        };

        tx.host_physical_addr >= self.allowed_base && tx_end <= slot_end
    }
}

/// Location of a heterogeneous virtual memory page.
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PageLocation {
    HostRam = 0,
    DeviceVram = 1,
    Unmapped = 2,
}

/// Heterogeneous Memory Management (HMM) page translation descriptor.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct HmmPageDescriptor {
    pub vaddr: u64,
    pub paddr: u64,
    pub location: PageLocation,
    pub is_writable: bool,
    pub is_valid: bool,
    pub _reserved: u8,
}

impl HmmPageDescriptor {
    pub const fn new(vaddr: u64, paddr: u64, location: PageLocation, is_writable: bool, is_valid: bool) -> Self {
        Self {
            vaddr,
            paddr,
            location,
            is_writable,
            is_valid,
            _reserved: 0,
        }
    }

    /// Verifies translation coherence (Theorem 13.3 `hmm_address_translation_safe`).
    pub fn is_coherent(&self) -> bool {
        self.is_valid && self.paddr > 0 && self.location != PageLocation::Unmapped
    }

    /// Atomically migrates page to a new location and physical address (Theorem 13.4).
    pub fn migrate(&mut self, new_loc: PageLocation, new_paddr: u64) -> Result<(), &'static str> {
        if new_loc == PageLocation::Unmapped || new_paddr == 0 {
            return Err("Invalid migration target");
        }
        self.location = new_loc;
        self.paddr = new_paddr;
        self.is_valid = true;
        Ok(())
    }
}

/// Monotonic DMA Fence synchronization primitive.
#[repr(C)]
#[derive(Debug)]
pub struct SafeDmaFence {
    context_id: u32,
    _padding: u32,
    seqno: AtomicU64,
}

impl SafeDmaFence {
    pub const fn new(context_id: u32, initial_seqno: u64) -> Self {
        Self {
            context_id,
            _padding: 0,
            seqno: AtomicU64::new(initial_seqno),
        }
    }

    pub fn context_id(&self) -> u32 {
        self.context_id
    }

    pub fn current_seqno(&self) -> u64 {
        self.seqno.load(Ordering::Acquire)
    }

    /// Atomically advance fence sequence number guaranteeing strict monotonicity (Theorem 13.7).
    pub fn signal_next(&self) -> u64 {
        self.seqno.fetch_add(1, Ordering::SeqCst) + 1
    }

    pub fn is_completed(&self, target_seqno: u64) -> bool {
        self.current_seqno() >= target_seqno
    }
}

/// Bounded Hardware Ring Buffer Index Wrapper (Theorems 13.5 & 13.6).
#[derive(Debug, Clone, Copy)]
pub struct SafeRingIndex {
    head: usize,
    tail: usize,
    size: usize,
}

impl SafeRingIndex {
    pub fn new(size: usize) -> Result<Self, &'static str> {
        if size == 0 {
            return Err("Ring buffer size must be strictly positive");
        }
        Ok(Self {
            head: 0,
            tail: 0,
            size,
        })
    }

    pub fn head_bounded(&self) -> usize {
        self.head % self.size
    }

    pub fn tail_bounded(&self) -> usize {
        self.tail % self.size
    }

    pub fn advance_head(&mut self) -> usize {
        let slot = self.head % self.size;
        self.head = self.head.wrapping_add(1);
        slot
    }

    pub fn advance_tail(&mut self) -> usize {
        let slot = self.tail % self.size;
        self.tail = self.tail.wrapping_add(1);
        slot
    }
}

/// Multi-Instance GPU (MIG) hardware slice partition descriptor (Theorem 13.8).
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GpuPartitionSlice {
    pub tenant_id: u32,
    pub compute_slice_id: u32,
    pub vram_base: u64,
    pub vram_size: u64,
}

impl GpuPartitionSlice {
    pub const fn new(tenant_id: u32, compute_slice_id: u32, vram_base: u64, vram_size: u64) -> Self {
        Self {
            tenant_id,
            compute_slice_id,
            vram_base,
            vram_size,
        }
    }

    /// Validates whether an access at `(addr, slice_id)` falls strictly inside this partition.
    pub fn authorizes_access(&self, addr: u64, slice_id: u32) -> bool {
        if self.compute_slice_id != slice_id {
            return false;
        }
        addr >= self.vram_base && addr < self.vram_base.saturating_add(self.vram_size)
    }

    /// Checks if two partitions are strictly disjoint in memory and compute slice.
    pub fn is_disjoint(&self, other: &Self) -> bool {
        let mem_disjoint = (self.vram_base.saturating_add(self.vram_size) <= other.vram_base)
            || (other.vram_base.saturating_add(other.vram_size) <= self.vram_base);
        let slice_disjoint = self.compute_slice_id != other.compute_slice_id;
        mem_disjoint && slice_disjoint
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pci_bar_bounds() {
        let bar = PciBarConfig::new(0, true, true, 0xE000_0000, 0x1000_0000);
        assert!(bar.contains_address(0xE000_0000));
        assert!(bar.contains_address(0xEFFF_FFFF));
        assert!(!bar.contains_address(0xDFFF_FFFF));
        assert!(!bar.contains_address(0xF000_0000));
    }

    #[test]
    fn test_iommu_isolation_enforcement() {
        let slot = IommuDomainSlot::new(1, 42, 0x1000_0000, 0x0100_0000);
        
        // Authorized DMA within bounds
        let valid_tx = GpuDmaDescriptor {
            device_id: 42,
            _padding0: 0,
            host_physical_addr: 0x1000_1000,
            device_vram_addr: 0x0,
            byte_count: 0x1000,
            flags: 0,
            fence_seq: 1,
        };
        assert!(slot.is_dma_authorized(&valid_tx));

        // Unauthorized: Ring 0 memory address (0xFFFF_8000_...)
        let attack_tx = GpuDmaDescriptor {
            device_id: 42,
            _padding0: 0,
            host_physical_addr: 0xFFFF_8000_0000_0000,
            device_vram_addr: 0x0,
            byte_count: 0x1000,
            flags: 0,
            fence_seq: 2,
        };
        assert!(!slot.is_dma_authorized(&attack_tx));
    }

    #[test]
    fn test_hmm_coherence_and_migration() {
        let mut page = HmmPageDescriptor::new(0x7FFF_0000, 0x2000_0000, PageLocation::HostRam, true, true);
        assert!(page.is_coherent());

        // Migrate to VRAM
        assert!(page.migrate(PageLocation::DeviceVram, 0x8000_0000).is_ok());
        assert_eq!(page.location, PageLocation::DeviceVram);
        assert_eq!(page.paddr, 0x8000_0000);
        assert!(page.is_coherent());

        // Invalid migration to Unmapped fails
        assert!(page.migrate(PageLocation::Unmapped, 0x0).is_err());
    }

    #[test]
    fn test_dma_fence_monotonicity() {
        let fence = SafeDmaFence::new(1, 100);
        assert_eq!(fence.current_seqno(), 100);
        assert!(!fence.is_completed(101));

        let next = fence.signal_next();
        assert_eq!(next, 101);
        assert_eq!(fence.current_seqno(), 101);
        assert!(fence.is_completed(101));
    }

    #[test]
    fn test_mig_tenant_isolation() {
        let p1 = GpuPartitionSlice::new(10, 0, 0x1000_0000, 0x1000_0000);
        let p2 = GpuPartitionSlice::new(20, 1, 0x2000_0000, 0x1000_0000);

        assert!(p1.is_disjoint(&p2));
        assert!(p1.authorizes_access(0x1000_5000, 0));
        assert!(!p2.authorizes_access(0x1000_5000, 0));
        assert!(!p1.authorizes_access(0x2000_5000, 1));
    }
}
