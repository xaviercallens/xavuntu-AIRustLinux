//! RunuX GPU Compute Subsystem - Heterogeneous Memory Management (HMM)
//!
//! Implements HMM, UVA (Unified Virtual Addressing) and basic GEM/TTM-like 
//! memory mapping for the GPU. Provides atomic page migration.
//! Ensures memory coherence and non-aliasing as required by Lean 4 
//! Theorem 13.3 (`hmm_address_translation_safe`) and 13.4.

#![no_std]
#![deny(clippy::all)]

use gpu_types::{HmmPageDescriptor, PageLocation};

/// Standard page size (4 KiB)
pub const PAGE_SIZE: u64 = 4096;
/// Maximum number of tracked pages for this bare-metal implementation
pub const MAX_HMM_PAGES: usize = 512;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HmmError {
    InvalidMigrationTarget,
    AddressMisaligned,
    PageNotValid,
    OutOfMemory,
    PageNotFound,
}

/// Heterogeneous Memory Management Engine
#[derive(Debug)]
pub struct HmmManager {
    pages: [Option<HmmPageDescriptor>; MAX_HMM_PAGES],
    mapped_count: usize,
}

impl HmmManager {
    pub const fn new() -> Self {
        Self {
            pages: [None; MAX_HMM_PAGES],
            mapped_count: 0,
        }
    }

    /// Maps a virtual address to a physical address either in Host RAM or Device VRAM.
    /// Enforces UVA non-aliasing (Theorem 13.3).
    pub fn map_page(
        &mut self,
        vaddr: u64,
        paddr: u64,
        location: PageLocation,
        is_writable: bool,
    ) -> Result<(), HmmError> {
        if vaddr % PAGE_SIZE != 0 || paddr % PAGE_SIZE != 0 {
            return Err(HmmError::AddressMisaligned);
        }

        if location == PageLocation::Unmapped {
            return Err(HmmError::InvalidMigrationTarget);
        }

        // Check for aliasing
        for slot in self.pages.iter().flatten() {
            if slot.vaddr == vaddr {
                return Err(HmmError::PageNotValid); // Already mapped
            }
        }

        let desc = HmmPageDescriptor::new(vaddr, paddr, location, is_writable, true);
        if !desc.is_coherent() {
            return Err(HmmError::PageNotValid);
        }

        for slot in self.pages.iter_mut() {
            if slot.is_none() {
                *slot = Some(desc);
                self.mapped_count += 1;
                return Ok(());
            }
        }

        Err(HmmError::OutOfMemory)
    }

    /// Atomically migrates a page to a new location and physical address (Theorem 13.4).
    pub fn migrate_page(&mut self, vaddr: u64, new_loc: PageLocation, new_paddr: u64) -> Result<(), HmmError> {
        if vaddr % PAGE_SIZE != 0 || new_paddr % PAGE_SIZE != 0 {
            return Err(HmmError::AddressMisaligned);
        }

        for slot in self.pages.iter_mut().flatten() {
            if slot.vaddr == vaddr {
                return slot
                    .migrate(new_loc, new_paddr)
                    .map_err(|_| HmmError::InvalidMigrationTarget);
            }
        }
        Err(HmmError::PageNotFound)
    }

    /// Translates a virtual address to its physical backing and location.
    pub fn translate(&self, vaddr: u64) -> Option<(u64, PageLocation)> {
        let page_offset = vaddr % PAGE_SIZE;
        let base_vaddr = vaddr - page_offset;

        for slot in self.pages.iter().flatten() {
            if slot.vaddr == base_vaddr && slot.is_coherent() {
                return Some((slot.paddr + page_offset, slot.location));
            }
        }
        None
    }

    /// Number of mapped pages
    pub fn mapped_count(&self) -> usize {
        self.mapped_count
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hmm_map_and_translate() {
        let mut hmm = HmmManager::new();
        
        let map_res = hmm.map_page(0x1000_0000, 0x2000_0000, PageLocation::HostRam, true);
        assert!(map_res.is_ok());

        let translated = hmm.translate(0x1000_0050);
        assert_eq!(translated, Some((0x2000_0050, PageLocation::HostRam)));

        let unmapped = hmm.translate(0x1000_1000);
        assert_eq!(unmapped, None);
    }

    #[test]
    fn test_hmm_aliasing_protection() {
        let mut hmm = HmmManager::new();
        
        assert!(hmm.map_page(0x1000_0000, 0x2000_0000, PageLocation::HostRam, true).is_ok());
        // Second mapping to same vaddr should fail
        assert_eq!(
            hmm.map_page(0x1000_0000, 0x3000_0000, PageLocation::DeviceVram, false),
            Err(HmmError::PageNotValid)
        );
    }

    #[test]
    fn test_hmm_page_migration() {
        let mut hmm = HmmManager::new();
        
        assert!(hmm.map_page(0x1000_0000, 0x2000_0000, PageLocation::HostRam, true).is_ok());
        
        // Migrate to VRAM
        let mig_res = hmm.migrate_page(0x1000_0000, PageLocation::DeviceVram, 0x4000_0000);
        assert!(mig_res.is_ok());

        let translated = hmm.translate(0x1000_0050);
        assert_eq!(translated, Some((0x4000_0050, PageLocation::DeviceVram)));
    }
}
