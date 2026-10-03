//! RunuX Intel VT-d / AMD-Vi IOMMU Protection Engine
//!
//! Enforces hardware DMA isolation for GPU and accelerated compute devices.
//! Implements strict Ring 0 containment as specified in Lean 4 Theorem 13.2
//! (`iommu_dma_isolation_guarantee`) and requirement REQ-GPU-001.

#![no_std]
#![deny(clippy::all)]

use gpu_types::{GpuDmaDescriptor, IommuDomainSlot};

/// Base boundary of the 64-bit kernel Ring 0 address space.
pub const KERNEL_SPACE_BASE: u64 = 0xFFFF_8000_0000_0000;

/// Standard page size (4 KiB).
pub const PAGE_SIZE: u64 = 4096;

/// IOMMU error types.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IommuError {
    /// Attempt to map or access kernel Ring 0 protected memory space.
    Ring0Violation,
    /// Invalid bus/device/function identifier.
    InvalidBdf,
    /// Device not found or domain not allocated.
    DeviceNotFound,
    /// Domain capacity exceeded or out of memory.
    OutOfMemory,
    /// Misaligned physical or I/O virtual address.
    MisalignedAddress,
    /// Address out of assigned hardware bounds.
    OutOfBounds,
}

/// Intel VT-d Root Entry (128 bits).
/// Represents root table entry for a PCI bus (0..255).
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct VtdRootEntry {
    /// Lower 64 bits: Present flag (bit 0) and Context Table Base Address (bits 63:12).
    pub lower: u64,
    /// Upper 64 bits: Reserved in standard VT-d.
    pub upper: u64,
}

impl VtdRootEntry {
    pub const fn empty() -> Self {
        Self { lower: 0, upper: 0 }
    }

    pub fn set_context_table(&mut self, context_table_paddr: u64) {
        // Bit 0 = Present, Bits 63:12 = PPN (4K aligned)
        self.lower = (context_table_paddr & !0xFFF) | 0x1;
    }

    pub fn is_present(&self) -> bool {
        (self.lower & 0x1) != 0
    }

    pub fn context_table_paddr(&self) -> u64 {
        self.lower & !0xFFF
    }
}

/// Intel VT-d Context Entry (128 bits).
/// Configures translation parameters and Second-Level Page Table Pointer (SLPTPTR)
/// for a specific device (0..31) and function (0..7).
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct VtdContextEntry {
    /// Lower 64 bits: Present (bit 0), Translation Type (bits 3:2), Domain ID (bits 23:8).
    pub lower: u64,
    /// Upper 64 bits: SLPTPTR (bits 63:12), Address Width (bits 2:0).
    pub upper: u64,
}

impl VtdContextEntry {
    pub const fn empty() -> Self {
        Self { lower: 0, upper: 0 }
    }

    pub fn configure(&mut self, domain_id: u16, slptptr: u64) {
        // lower: bit 0 (Present), bits 23:8 (Domain ID)
        self.lower = 0x1 | ((domain_id as u64) << 8);
        // upper: bits 63:12 = Second-Level Page Directory Pointer (4K aligned)
        self.upper = slptptr & !0xFFF;
    }

    pub fn is_present(&self) -> bool {
        (self.lower & 0x1) != 0
    }

    pub fn domain_id(&self) -> u16 {
        ((self.lower >> 8) & 0xFFFF) as u16
    }

    pub fn page_table_base(&self) -> u64 {
        self.upper & !0xFFF
    }
}

/// Second-Level Page Table Entry (SLPTE) for VT-d DMA remapping.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SlPageTableEntry {
    pub entry: u64,
}

impl SlPageTableEntry {
    pub const fn empty() -> Self {
        Self { entry: 0 }
    }

    /// Read permission flag (bit 0).
    pub const READ: u64 = 1 << 0;
    /// Write permission flag (bit 1).
    pub const WRITE: u64 = 1 << 1;

    pub fn configure(&mut self, host_paddr: u64, read: bool, write: bool) -> Result<(), IommuError> {
        // Enforce Ring 0 memory protection guarantee (REQ-GPU-001 / Theorem 13.2)
        if host_paddr >= KERNEL_SPACE_BASE {
            return Err(IommuError::Ring0Violation);
        }
        if (host_paddr % PAGE_SIZE) != 0 {
            return Err(IommuError::MisalignedAddress);
        }

        let mut flags = 0u64;
        if read {
            flags |= Self::READ;
        }
        if write {
            flags |= Self::WRITE;
        }

        self.entry = (host_paddr & !0xFFF) | flags;
        Ok(())
    }

    pub fn is_valid(&self) -> bool {
        (self.entry & (Self::READ | Self::WRITE)) != 0
    }

    pub fn host_paddr(&self) -> u64 {
        self.entry & !0xFFF
    }
}

/// Simulated hardware domain entry for device isolation.
pub const MAX_MAPPED_PAGES: usize = 256;

#[derive(Debug, Clone, Copy)]
pub struct IommuMapping {
    pub iova: u64,
    pub hpa: u64,
    pub is_write: bool,
}

/// Hardware IOMMU Protection Domain.
#[derive(Debug)]
pub struct IommuDomain {
    pub domain_id: u32,
    pub slot: IommuDomainSlot,
    mappings: [Option<IommuMapping>; MAX_MAPPED_PAGES],
    mapping_count: usize,
    iotlb_invalidated: bool,
}

impl IommuDomain {
    pub fn new(domain_id: u32, device_id: u32, allowed_base: u64, allowed_length: u64) -> Result<Self, IommuError> {
        // Prevent assigning domain overlapping with Ring 0
        let slot_end = allowed_base.checked_add(allowed_length).ok_or(IommuError::OutOfBounds)?;
        if allowed_base >= KERNEL_SPACE_BASE || slot_end > KERNEL_SPACE_BASE {
            return Err(IommuError::Ring0Violation);
        }

        Ok(Self {
            domain_id,
            slot: IommuDomainSlot::new(domain_id, device_id, allowed_base, allowed_length),
            mappings: [None; MAX_MAPPED_PAGES],
            mapping_count: 0,
            iotlb_invalidated: true,
        })
    }

    /// Maps an IO Virtual Address (IOVA) to Host Physical Address (HPA).
    /// Fallible and strictly checks bounds against Ring 0 tamper.
    pub fn map_page(&mut self, iova: u64, hpa: u64, is_write: bool) -> Result<(), IommuError> {
        if hpa >= KERNEL_SPACE_BASE {
            return Err(IommuError::Ring0Violation);
        }
        if (iova % PAGE_SIZE) != 0 || (hpa % PAGE_SIZE) != 0 {
            return Err(IommuError::MisalignedAddress);
        }

        let tx = GpuDmaDescriptor {
            device_id: self.slot.device_id,
            _padding0: 0,
            host_physical_addr: iova,
            device_vram_addr: 0,
            byte_count: PAGE_SIZE,
            flags: 0,
            fence_seq: 0,
        };

        if !self.slot.is_dma_authorized(&tx) {
            return Err(IommuError::OutOfBounds);
        }

        if self.mapping_count >= MAX_MAPPED_PAGES {
            return Err(IommuError::OutOfMemory);
        }

        // Store mapping
        for entry in self.mappings.iter_mut() {
            if entry.is_none() {
                *entry = Some(IommuMapping { iova, hpa, is_write });
                self.mapping_count += 1;
                self.iotlb_invalidated = false;
                return Ok(());
            }
        }

        Err(IommuError::OutOfMemory)
    }

    /// Invalidate IOTLB hardware cache line barrier.
    pub fn invalidate_iotlb(&mut self) {
        self.iotlb_invalidated = true;
    }

    /// Check whether IOTLB cache is properly synchronized.
    pub fn is_iotlb_coherent(&self) -> bool {
        self.iotlb_invalidated
    }

    /// Translates an IOVA through the domain's page table.
    pub fn translate(&self, iova: u64) -> Result<u64, IommuError> {
        let page_offset = iova % PAGE_SIZE;
        let base_iova = iova - page_offset;

        for entry in self.mappings.iter().flatten() {
            if entry.iova == base_iova {
                return Ok(entry.hpa + page_offset);
            }
        }

        Err(IommuError::OutOfBounds)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vtd_root_entry_setup() {
        let mut root = VtdRootEntry::empty();
        assert!(!root.is_present());

        root.set_context_table(0x1000_0000);
        assert!(root.is_present());
        assert_eq!(root.context_table_paddr(), 0x1000_0000);
    }

    #[test]
    fn test_vtd_context_entry_setup() {
        let mut ctx = VtdContextEntry::empty();
        assert!(!ctx.is_present());

        ctx.configure(42, 0x2000_0000);
        assert!(ctx.is_present());
        assert_eq!(ctx.domain_id(), 42);
        assert_eq!(ctx.page_table_base(), 0x2000_0000);
    }

    #[test]
    fn test_slpte_ring0_protection() {
        let mut pte = SlPageTableEntry::empty();

        // Valid user page
        assert!(pte.configure(0x3000_0000, true, true).is_ok());
        assert!(pte.is_valid());
        assert_eq!(pte.host_paddr(), 0x3000_0000);

        // Exploit attempt targeting Ring 0 Kernel Space (0xFFFF_8000_0000_0000)
        let exploit_result = pte.configure(KERNEL_SPACE_BASE + 0x1000, true, true);
        assert_eq!(exploit_result, Err(IommuError::Ring0Violation));
    }

    #[test]
    fn test_domain_mapping_and_translation() {
        let mut domain = IommuDomain::new(1, 100, 0x1000_0000, 0x0100_0000).expect("Domain creation");

        // Map valid 4KiB page
        let map_res = domain.map_page(0x1000_0000, 0x4000_0000, true);
        assert!(map_res.is_ok());
        assert!(!domain.is_iotlb_coherent());

        domain.invalidate_iotlb();
        assert!(domain.is_iotlb_coherent());

        // Translation check
        let translated = domain.translate(0x1000_0020).expect("Translation ok");
        assert_eq!(translated, 0x4000_0020);

        // Ring 0 tamper attempt
        let ring0_res = domain.map_page(0x1000_1000, KERNEL_SPACE_BASE + 0x2000, true);
        assert_eq!(ring0_res, Err(IommuError::Ring0Violation));
    }
}
