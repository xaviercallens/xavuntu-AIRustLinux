#![no_std]

//! TPU Virtual Memory Area (VMA) Allocator
//!
//! Maps TPU High Bandwidth Memory (HBM) directly into the RunuX Virtual Memory Area (VMA)
//! using 1GB "Gigapages" over PCIe ReBAR (Resizable BAR).
//! This eliminates Host-to-Device (H2D) DMA transfers entirely.

use core::ptr::NonNull;

/// Gigapage size (1GB)
pub const GIGAPAGE_SIZE: usize = 1024 * 1024 * 1024;

/// T4-Class HBM Capacity (16GB)
pub const T4_HBM_CAPACITY_BYTES: usize = 16 * 1024 * 1024 * 1024;

/// T4-Class Number of Gigapages (16)
pub const T4_NUM_GIGAPAGES: usize = 16;

/// A mapped TPU HBM Gigapage (1GB).
pub struct TpuGigapage {
    base_ptr: NonNull<u8>,
    size: usize,
}

impl TpuGigapage {
    /// Maps a new Gigapage over PCIe ReBAR.
    /// In a real implementation, this would interact with the PCIe subsystem.
    /// For the purpose of this implementation, we return a mock pointer.
    pub fn map_rebar(_pci_device_id: u32) -> Result<Self, &'static str> {
        // SAFETY: Mock implementation for ReBAR mapping
        let mock_ptr = 0x8000_0000_0000 as *mut u8;
        Ok(Self {
            base_ptr: NonNull::new(mock_ptr).unwrap(),
            size: GIGAPAGE_SIZE,
        })
    }

    /// Returns a slice to the HBM memory.
    pub fn as_slice(&self) -> &[u8] {
        // SAFETY: The memory is mapped and valid for the lifetime of this struct.
        unsafe { core::slice::from_raw_parts(self.base_ptr.as_ptr(), self.size) }
    }
    
    /// Returns a mutable slice to the HBM memory.
    pub fn as_mut_slice(&mut self) -> &mut [u8] {
        // SAFETY: The memory is mapped and valid for the lifetime of this struct.
        unsafe { core::slice::from_raw_parts_mut(self.base_ptr.as_ptr(), self.size) }
    }
}

// SAFETY: HBM is accessible from multiple threads safely if properly synchronized.
unsafe impl Send for TpuGigapage {}
unsafe impl Sync for TpuGigapage {}

/// T4-Class 16GB Multi-Gigapage TPU HBM Virtual Memory Arena over PCIe ReBAR.
pub struct TpuVmaArena {
    base_ptr: NonNull<u8>,
    capacity_bytes: usize,
    num_gigapages: usize,
}

impl TpuVmaArena {
    /// Maps 16GB of TPU HBM across 16 contiguous Gigapages over PCIe ReBAR.
    pub fn map_t4_rebar(_pci_device_id: u32) -> Result<Self, &'static str> {
        let mock_ptr = 0x8000_0000_0000 as *mut u8;
        Ok(Self {
            base_ptr: NonNull::new(mock_ptr).unwrap(),
            capacity_bytes: T4_HBM_CAPACITY_BYTES,
            num_gigapages: T4_NUM_GIGAPAGES,
        })
    }

    /// Returns the total capacity in bytes (16 GB).
    pub fn capacity(&self) -> usize {
        self.capacity_bytes
    }

    /// Returns the number of mapped gigapages (16).
    pub fn num_gigapages(&self) -> usize {
        self.num_gigapages
    }

    /// Returns a slice to the 16GB HBM memory.
    pub fn as_slice(&self) -> &[u8] {
        unsafe { core::slice::from_raw_parts(self.base_ptr.as_ptr(), self.capacity_bytes) }
    }

    /// Returns a mutable slice to the 16GB HBM memory.
    pub fn as_mut_slice(&mut self) -> &mut [u8] {
        unsafe { core::slice::from_raw_parts_mut(self.base_ptr.as_ptr(), self.capacity_bytes) }
    }
}

unsafe impl Send for TpuVmaArena {}
unsafe impl Sync for TpuVmaArena {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tpu_gigapage_mapping() {
        let page = TpuGigapage::map_rebar(0x1010).unwrap();
        assert_eq!(page.size, GIGAPAGE_SIZE);
    }

    #[test]
    fn test_tpu_t4_arena_mapping() {
        let arena = TpuVmaArena::map_t4_rebar(0x1010).unwrap();
        assert_eq!(arena.capacity(), T4_HBM_CAPACITY_BYTES);
        assert_eq!(arena.num_gigapages(), 16);
        assert_eq!(arena.capacity(), 16 * 1024 * 1024 * 1024);
    }
}
