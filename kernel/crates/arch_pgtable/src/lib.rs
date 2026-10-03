#![no_std]
#![deny(clippy::all)]
#![warn(clippy::pedantic)]
#![allow(clippy::module_name_repetitions, clippy::cast_possible_truncation)]

//! Architecture-specific Page Table Formats and Hardware MMU Translation.
//!
//! Implements hardware-level page table entry encodings for x86_64 4-level paging (with NX bit 63)
//! and RISC-V Sv39 3-level paging, along with hardware page fault error code decoding and resolution.

use core::ffi::c_int;
use core::sync::atomic::{AtomicBool, Ordering};

use page_table::{MapFlags, PhysAddr, VirtAddr, PAGE_SIZE};

// ============================================================================
// x86_64 4-Level Paging Architecture
// ============================================================================

pub mod x86_64 {
    use super::*;

    pub const PTE_PRESENT: u64 = 1 << 0;
    pub const PTE_WRITABLE: u64 = 1 << 1;
    pub const PTE_USER: u64 = 1 << 2;
    pub const PTE_WRITE_THROUGH: u64 = 1 << 3;
    pub const PTE_NO_CACHE: u64 = 1 << 4;
    pub const PTE_ACCESSED: u64 = 1 << 5;
    pub const PTE_DIRTY: u64 = 1 << 6;
    pub const PTE_HUGE_PAGE: u64 = 1 << 7;
    pub const PTE_GLOBAL: u64 = 1 << 8;
    pub const PTE_NO_EXECUTE: u64 = 1 << 63;

    /// Convert architecture-independent MapFlags to x86_64 raw PTE bits.
    #[inline]
    #[must_use]
    pub fn flags_to_pte(flags: MapFlags, paddr: PhysAddr) -> u64 {
        let mut pte = (paddr.as_usize() as u64) & 0x000F_FFFF_FFFF_F000;

        if flags.is_present() {
            pte |= PTE_PRESENT;
        }
        if flags.is_writable() {
            pte |= PTE_WRITABLE;
        }
        if flags.is_user() {
            pte |= PTE_USER;
        }
        if flags.contains(MapFlags::NO_CACHE) {
            pte |= PTE_NO_CACHE;
        }
        if flags.contains(MapFlags::ACCESSED) {
            pte |= PTE_ACCESSED;
        }
        if flags.contains(MapFlags::DIRTY) {
            pte |= PTE_DIRTY;
        }
        if flags.contains(MapFlags::GLOBAL) {
            pte |= PTE_GLOBAL;
        }
        if flags.is_huge() {
            pte |= PTE_HUGE_PAGE;
        }
        // Invert execute permission: if NOT executable, set hardware NX bit 63
        if !flags.is_executable() {
            pte |= PTE_NO_EXECUTE;
        }

        pte
    }

    /// Extract architecture-independent MapFlags from x86_64 raw PTE bits.
    #[inline]
    #[must_use]
    pub fn pte_to_flags(pte: u64) -> MapFlags {
        let mut bits = 0u64;

        if (pte & PTE_PRESENT) != 0 {
            bits |= MapFlags::PRESENT.bits();
        }
        if (pte & PTE_WRITABLE) != 0 {
            bits |= MapFlags::WRITE.bits();
        }
        if (pte & PTE_USER) != 0 {
            bits |= MapFlags::USER.bits();
        }
        if (pte & PTE_NO_CACHE) != 0 {
            bits |= MapFlags::NO_CACHE.bits();
        }
        if (pte & PTE_ACCESSED) != 0 {
            bits |= MapFlags::ACCESSED.bits();
        }
        if (pte & PTE_DIRTY) != 0 {
            bits |= MapFlags::DIRTY.bits();
        }
        if (pte & PTE_GLOBAL) != 0 {
            bits |= MapFlags::GLOBAL.bits();
        }
        if (pte & PTE_HUGE_PAGE) != 0 {
            bits |= MapFlags::HUGE_PAGE.bits();
        }
        // If NX bit is clear and page is present, page is executable
        if (pte & PTE_NO_EXECUTE) == 0 && (pte & PTE_PRESENT) != 0 {
            bits |= MapFlags::EXECUTE.bits();
        }

        MapFlags(bits)
    }
}

// ============================================================================
// RISC-V Sv39 Paging Architecture
// ============================================================================

pub mod riscv_sv39 {
    use super::*;

    pub const PTE_V: u64 = 1 << 0; // Valid
    pub const PTE_R: u64 = 1 << 1; // Read
    pub const PTE_W: u64 = 1 << 2; // Write
    pub const PTE_X: u64 = 1 << 3; // Execute
    pub const PTE_U: u64 = 1 << 4; // User
    pub const PTE_G: u64 = 1 << 5; // Global
    pub const PTE_A: u64 = 1 << 6; // Accessed
    pub const PTE_D: u64 = 1 << 7; // Dirty

    /// Convert architecture-independent MapFlags to RISC-V Sv39 raw PTE bits.
    #[inline]
    #[must_use]
    pub fn flags_to_pte(flags: MapFlags, paddr: PhysAddr) -> u64 {
        let ppn = (paddr.as_usize() >> 12) as u64;
        let mut pte = ppn << 10;

        if flags.is_present() {
            pte |= PTE_V;
        }
        if flags.contains(MapFlags::READ) {
            pte |= PTE_R;
        }
        if flags.is_writable() {
            pte |= PTE_W;
        }
        if flags.is_executable() {
            pte |= PTE_X;
        }
        if flags.is_user() {
            pte |= PTE_U;
        }
        if flags.contains(MapFlags::GLOBAL) {
            pte |= PTE_G;
        }
        if flags.contains(MapFlags::ACCESSED) {
            pte |= PTE_A;
        }
        if flags.contains(MapFlags::DIRTY) {
            pte |= PTE_D;
        }

        pte
    }

    /// Extract architecture-independent MapFlags from RISC-V Sv39 raw PTE bits.
    #[inline]
    #[must_use]
    pub fn pte_to_flags(pte: u64) -> MapFlags {
        let mut bits = 0u64;

        if (pte & PTE_V) != 0 {
            bits |= MapFlags::PRESENT.bits();
        }
        if (pte & PTE_R) != 0 {
            bits |= MapFlags::READ.bits();
        }
        if (pte & PTE_W) != 0 {
            bits |= MapFlags::WRITE.bits();
        }
        if (pte & PTE_X) != 0 {
            bits |= MapFlags::EXECUTE.bits();
        }
        if (pte & PTE_U) != 0 {
            bits |= MapFlags::USER.bits();
        }
        if (pte & PTE_G) != 0 {
            bits |= MapFlags::GLOBAL.bits();
        }
        if (pte & PTE_A) != 0 {
            bits |= MapFlags::ACCESSED.bits();
        }
        if (pte & PTE_D) != 0 {
            bits |= MapFlags::DIRTY.bits();
        }

        MapFlags(bits)
    }

    /// Extract Sv39 virtual page numbers (VPN[2], VPN[1], VPN[0]).
    #[inline]
    #[must_use]
    pub const fn vpn_indices(vaddr: usize) -> (usize, usize, usize) {
        let vpn2 = (vaddr >> 30) & 0x1FF;
        let vpn1 = (vaddr >> 21) & 0x1FF;
        let vpn0 = (vaddr >> 12) & 0x1FF;
        (vpn2, vpn1, vpn0)
    }
}

// ============================================================================
// Hardware Page Fault Decoding & Resolution
// ============================================================================

/// Hardware error code emitted on page faults (e.g. x86_64 CR2 / exception error code).
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct PageFaultErrorCode(pub u32);

impl PageFaultErrorCode {
    pub const CAUSED_BY_WRITE: u32 = 1 << 1;
    pub const USER_MODE: u32 = 1 << 2;
    pub const MALFORMED_TABLE: u32 = 1 << 3;
    pub const INSTRUCTION_FETCH: u32 = 1 << 4;
    pub const PROTECTION_VIOLATION: u32 = 1 << 0;

    #[inline]
    #[must_use]
    pub const fn is_write(&self) -> bool {
        (self.0 & Self::CAUSED_BY_WRITE) != 0
    }

    #[inline]
    #[must_use]
    pub const fn is_user(&self) -> bool {
        (self.0 & Self::USER_MODE) != 0
    }

    #[inline]
    #[must_use]
    pub const fn is_instruction_fetch(&self) -> bool {
        (self.0 & Self::INSTRUCTION_FETCH) != 0
    }

    #[inline]
    #[must_use]
    pub const fn is_protection_violation(&self) -> bool {
        (self.0 & Self::PROTECTION_VIOLATION) != 0
    }
}

/// Dispatch resolution action for a page fault.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum FaultResolution {
    /// Page was not present; satisfy by allocating a physical frame.
    DemandPaging,
    /// Page was marked read-only for Copy-on-Write; duplicate frame and remap writable.
    CopyOnWrite,
    /// Memory violation or non-executable page execution; raise segmentation signal.
    SegmentationFault,
    /// Access control violation (user accessing kernel space).
    ProtectionViolation,
}

/// Classify a page fault given virtual address, error code, and existing mapping state.
#[inline]
#[must_use]
pub fn handle_page_fault(
    vaddr: VirtAddr,
    error_code: PageFaultErrorCode,
    is_present: bool,
    is_cow: bool,
) -> FaultResolution {
    if !is_present {
        // Page is absent in address space: if valid userspace range, perform demand paging
        if vaddr.as_usize() < 0x0000_8000_0000_0000 {
            FaultResolution::DemandPaging
        } else {
            FaultResolution::SegmentationFault
        }
    } else if error_code.is_instruction_fetch() {
        // NX execution attempt
        FaultResolution::SegmentationFault
    } else if error_code.is_write() && is_cow {
        // Write on read-only COW page
        FaultResolution::CopyOnWrite
    } else if error_code.is_user() && vaddr.as_usize() >= 0xFFFF_8000_0000_0000 {
        // User accessing supervisor address space
        FaultResolution::ProtectionViolation
    } else {
        FaultResolution::SegmentationFault
    }
}

// ============================================================================
// Module Lifecycle & FFI Exports
// ============================================================================

pub static ARCH_PGTABLE_INITIALIZED: AtomicBool = AtomicBool::new(false);

/// Architecture page table hardware feature verification and initialization.
///
/// # Safety
/// Caller must ensure CPU control registers (CR0, CR3, CR4) are initialized.
#[no_mangle]
pub unsafe extern "C" fn arch_pgtable_init() -> c_int {
    // Assert architecture constraints
    assert!(PAGE_SIZE == 4096);
    assert!(core::mem::size_of::<PageFaultErrorCode>() == 4);

    ARCH_PGTABLE_INITIALIZED.store(true, Ordering::Release);
    0
}

/// Module cleanup.
///
/// # Safety
/// Caller must ensure MMU mappings are synchronized.
#[no_mangle]
pub unsafe extern "C" fn arch_pgtable_exit() {
    ARCH_PGTABLE_INITIALIZED.store(false, Ordering::Release);
}

// ============================================================================
// Unit Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_x86_64_pte_encoding_and_nx() {
        let paddr = PhysAddr::new(0x1000_0000).unwrap();

        // Writable, non-executable mapping must have NX bit 63 set
        let rw_flags = MapFlags::PRESENT.union(MapFlags::READ).union(MapFlags::WRITE);
        let pte = x86_64::flags_to_pte(rw_flags, paddr);
        assert_ne!(pte & x86_64::PTE_PRESENT, 0);
        assert_ne!(pte & x86_64::PTE_WRITABLE, 0);
        assert_ne!(pte & x86_64::PTE_NO_EXECUTE, 0); // Hardware NX enforced!

        let decoded = x86_64::pte_to_flags(pte);
        assert!(decoded.is_present());
        assert!(decoded.is_writable());
        assert!(!decoded.is_executable());

        // Executable mapping must have NX bit 63 cleared
        let rx_flags = MapFlags::PRESENT.union(MapFlags::READ).union(MapFlags::EXECUTE);
        let rx_pte = x86_64::flags_to_pte(rx_flags, paddr);
        assert_eq!(rx_pte & x86_64::PTE_NO_EXECUTE, 0);
        let rx_decoded = x86_64::pte_to_flags(rx_pte);
        assert!(rx_decoded.is_executable());
    }

    #[test]
    fn test_riscv_sv39_pte_encoding() {
        let paddr = PhysAddr::new(0x8020_0000).unwrap();
        let flags = MapFlags::PRESENT.union(MapFlags::READ).union(MapFlags::WRITE).union(MapFlags::USER);

        let pte = riscv_sv39::flags_to_pte(flags, paddr);
        assert_ne!(pte & riscv_sv39::PTE_V, 0);
        assert_ne!(pte & riscv_sv39::PTE_R, 0);
        assert_ne!(pte & riscv_sv39::PTE_W, 0);
        assert_ne!(pte & riscv_sv39::PTE_U, 0);

        let decoded = riscv_sv39::pte_to_flags(pte);
        assert!(decoded.is_present());
        assert!(decoded.contains(MapFlags::READ));
        assert!(decoded.is_writable());
        assert!(decoded.is_user());

        let (vpn2, vpn1, vpn0) = riscv_sv39::vpn_indices(0x0000_0038_4020_1000);
        assert_eq!(vpn0, 1);
    }

    #[test]
    fn test_page_fault_classification() {
        let user_vaddr = VirtAddr::new(0x0000_1000_0000).unwrap();
        let kernel_vaddr = VirtAddr::new(0xFFFF_8000_0000_0000).unwrap();

        // 1. Demand Paging on unmapped user page
        let not_present = PageFaultErrorCode(0);
        let res1 = handle_page_fault(user_vaddr, not_present, false, false);
        assert_eq!(res1, FaultResolution::DemandPaging);

        // 2. Copy-on-Write on write to COW page
        let write_fault = PageFaultErrorCode(PageFaultErrorCode::CAUSED_BY_WRITE | PageFaultErrorCode::PROTECTION_VIOLATION);
        let res2 = handle_page_fault(user_vaddr, write_fault, true, true);
        assert_eq!(res2, FaultResolution::CopyOnWrite);

        // 3. Instruction fetch from NX page
        let nx_fault = PageFaultErrorCode(PageFaultErrorCode::INSTRUCTION_FETCH | PageFaultErrorCode::PROTECTION_VIOLATION);
        let res3 = handle_page_fault(user_vaddr, nx_fault, true, false);
        assert_eq!(res3, FaultResolution::SegmentationFault);

        // 4. User access to kernel memory
        let user_kernel_fault = PageFaultErrorCode(PageFaultErrorCode::USER_MODE | PageFaultErrorCode::PROTECTION_VIOLATION);
        let res4 = handle_page_fault(kernel_vaddr, user_kernel_fault, true, false);
        assert_eq!(res4, FaultResolution::ProtectionViolation);
    }

    #[test]
    fn test_arch_pgtable_lifecycle() {
        // SAFETY: Test preconditions
        unsafe {
            assert_eq!(arch_pgtable_init(), 0);
            assert!(ARCH_PGTABLE_INITIALIZED.load(Ordering::Acquire));
            arch_pgtable_exit();
            assert!(!ARCH_PGTABLE_INITIALIZED.load(Ordering::Acquire));
        }
    }
}
