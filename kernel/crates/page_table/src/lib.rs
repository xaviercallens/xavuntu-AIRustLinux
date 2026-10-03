#![no_std]
#![deny(clippy::all)]
#![warn(clippy::pedantic)]
#![allow(clippy::module_name_repetitions, clippy::cast_possible_truncation)]

//! Architecture-independent Virtual Memory and Page Table Management.
//!
//! Provides canonical address primitives (`VirtAddr`, `PhysAddr`), memory protection flags
//! (`MapFlags`) with hardware $W \oplus X$ invariant enforcement, a zero-allocation
//! `FrameAllocator` trait, raw `PageTableEntry` manipulations, and a safe multi-level
//! `VmSpace` translation walker.

use core::ffi::c_int;
use core::sync::atomic::{AtomicBool, Ordering};

pub const PAGE_SHIFT: usize = 12;
pub const PAGE_SIZE: usize = 1 << PAGE_SHIFT; // 4096 bytes
pub const PAGE_MASK: usize = !(PAGE_SIZE - 1);
pub const ENTRIES_PER_TABLE: usize = 512;

// ============================================================================
// Error Definitions
// ============================================================================

/// Errors encountered during virtual memory operations.
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub enum VmError {
    /// Address is not properly aligned to the expected page boundary.
    NotAligned,
    /// Address is outside the canonical address space.
    InvalidAddress,
    /// Violation of the W^X security invariant (simultaneously Writable and Executable).
    WritableAndExecutableViolation,
    /// The virtual address is already mapped to a physical frame.
    AlreadyMapped,
    /// The virtual address is not mapped in the page table hierarchy.
    NotMapped,
    /// Frame allocator exhausted available physical memory.
    OutOfMemory,
    /// Operation attempted on an invalid or uninitialized table.
    InvalidTable,
}

// ============================================================================
// Address Abstractions
// ============================================================================

/// Canonical 48-bit Virtual Address.
#[derive(Copy, Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Default)]
pub struct VirtAddr(pub usize);

impl VirtAddr {
    /// Create a new canonical virtual address.
    ///
    /// # Errors
    /// Returns `VmError::InvalidAddress` if the address is non-canonical in 48-bit space.
    #[inline]
    pub const fn new(addr: usize) -> Result<Self, VmError> {
        // In 48-bit canonical addressing, bits [63:47] must be sign-extended copies of bit 47.
        let sign_extended = ((addr as isize) >> 47) as usize;
        if sign_extended == 0 || sign_extended == !0 {
            Ok(Self(addr))
        } else {
            Err(VmError::InvalidAddress)
        }
    }

    /// Construct a virtual address without canonicality verification.
    ///
    /// # Safety
    /// Caller must ensure `addr` is within the valid architecture address space.
    #[inline]
    #[must_use]
    pub const unsafe fn new_unchecked(addr: usize) -> Self {
        Self(addr)
    }

    #[inline]
    #[must_use]
    pub const fn as_usize(&self) -> usize {
        self.0
    }

    #[inline]
    #[must_use]
    pub const fn is_aligned_4k(&self) -> bool {
        (self.0 & (PAGE_SIZE - 1)) == 0
    }

    #[inline]
    #[must_use]
    pub const fn align_down(&self) -> Self {
        Self(self.0 & PAGE_MASK)
    }

    /// Align address up to next 4KB boundary.
    ///
    /// # Errors
    /// Returns `VmError::InvalidAddress` on overflow.
    #[inline]
    pub fn align_up(&self) -> Result<Self, VmError> {
        let rounded = self.0.checked_add(PAGE_SIZE - 1).ok_or(VmError::InvalidAddress)? & PAGE_MASK;
        Self::new(rounded)
    }

    #[inline]
    #[must_use]
    pub const fn pml4_index(&self) -> usize {
        (self.0 >> 39) & 0x1FF
    }

    #[inline]
    #[must_use]
    pub const fn pdpt_index(&self) -> usize {
        (self.0 >> 30) & 0x1FF
    }

    #[inline]
    #[must_use]
    pub const fn pd_index(&self) -> usize {
        (self.0 >> 21) & 0x1FF
    }

    #[inline]
    #[must_use]
    pub const fn pt_index(&self) -> usize {
        (self.0 >> 12) & 0x1FF
    }

    #[inline]
    #[must_use]
    pub const fn page_offset(&self) -> usize {
        self.0 & (PAGE_SIZE - 1)
    }
}

/// Physical Frame Address.
#[derive(Copy, Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Default)]
pub struct PhysAddr(pub usize);

impl PhysAddr {
    /// Create a new physical address.
    ///
    /// # Errors
    /// Returns `VmError::InvalidAddress` if bits exceed 52-bit physical limit.
    #[inline]
    pub const fn new(addr: usize) -> Result<Self, VmError> {
        if addr < (1 << 52) {
            Ok(Self(addr))
        } else {
            Err(VmError::InvalidAddress)
        }
    }

    /// Construct a physical address without range checks.
    ///
    /// # Safety
    /// Caller must ensure `addr` is a valid physical bus address.
    #[inline]
    #[must_use]
    pub const unsafe fn new_unchecked(addr: usize) -> Self {
        Self(addr)
    }

    #[inline]
    #[must_use]
    pub const fn as_usize(&self) -> usize {
        self.0
    }

    #[inline]
    #[must_use]
    pub const fn is_aligned_4k(&self) -> bool {
        (self.0 & (PAGE_SIZE - 1)) == 0
    }

    #[inline]
    #[must_use]
    pub const fn align_down(&self) -> Self {
        Self(self.0 & PAGE_MASK)
    }
}

/// Supported hardware page sizes.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum PageSize {
    Size4KB,
    Size2MB,
    Size1GB,
}

impl PageSize {
    #[inline]
    #[must_use]
    pub const fn bytes(&self) -> usize {
        match self {
            Self::Size4KB => 4096,
            Self::Size2MB => 2 * 1024 * 1024,
            Self::Size1GB => 1024 * 1024 * 1024,
        }
    }
}

// ============================================================================
// Protection Flags & W^X Enforcement
// ============================================================================

/// Memory mapping permission and cache control flags.
#[derive(Copy, Clone, Debug, PartialEq, Eq, Default)]
pub struct MapFlags(pub u64);

impl MapFlags {
    pub const NONE: Self = Self(0);
    pub const PRESENT: Self = Self(1 << 0);
    pub const READ: Self = Self(1 << 1);
    pub const WRITE: Self = Self(1 << 2);
    pub const EXECUTE: Self = Self(1 << 3);
    pub const USER: Self = Self(1 << 4);
    pub const ACCESSED: Self = Self(1 << 5);
    pub const DIRTY: Self = Self(1 << 6);
    pub const GLOBAL: Self = Self(1 << 7);
    pub const NO_CACHE: Self = Self(1 << 8);
    pub const HUGE_PAGE: Self = Self(1 << 9);

    /// Construct safe flags enforcing the W^X invariant.
    ///
    /// # Errors
    /// Returns `VmError::WritableAndExecutableViolation` if both WRITE and EXECUTE are asserted.
    #[inline]
    pub const fn new(bits: u64) -> Result<Self, VmError> {
        let flags = Self(bits);
        if flags.is_writable() && flags.is_executable() {
            Err(VmError::WritableAndExecutableViolation)
        } else {
            Ok(flags)
        }
    }

    /// Construct flags bypassing W^X checks for early boot or self-modifying code.
    ///
    /// # Safety
    /// Caller must guarantee that writable-and-executable memory is isolated and safe.
    #[inline]
    #[must_use]
    pub const unsafe fn allow_wx(bits: u64) -> Self {
        Self(bits)
    }

    #[inline]
    #[must_use]
    pub const fn bits(&self) -> u64 {
        self.0
    }

    #[inline]
    #[must_use]
    pub const fn contains(&self, other: Self) -> bool {
        (self.0 & other.0) == other.0
    }

    #[inline]
    #[must_use]
    pub const fn is_present(&self) -> bool {
        self.contains(Self::PRESENT)
    }

    #[inline]
    #[must_use]
    pub const fn is_writable(&self) -> bool {
        self.contains(Self::WRITE)
    }

    #[inline]
    #[must_use]
    pub const fn is_executable(&self) -> bool {
        self.contains(Self::EXECUTE)
    }

    #[inline]
    #[must_use]
    pub const fn is_user(&self) -> bool {
        self.contains(Self::USER)
    }

    #[inline]
    #[must_use]
    pub const fn is_huge(&self) -> bool {
        self.contains(Self::HUGE_PAGE)
    }

    #[inline]
    #[must_use]
    pub const fn union(self, other: Self) -> Self {
        Self(self.0 | other.0)
    }

    #[inline]
    #[must_use]
    pub const fn difference(self, other: Self) -> Self {
        Self(self.0 & !other.0)
    }

    /// Validate the W^X security invariant.
    ///
    /// # Errors
    /// Returns `VmError::WritableAndExecutableViolation` if `WRITE` and `EXECUTE` are both set.
    #[inline]
    pub const fn validate_wx(&self) -> Result<(), VmError> {
        if self.is_writable() && self.is_executable() {
            Err(VmError::WritableAndExecutableViolation)
        } else {
            Ok(())
        }
    }
}

// ============================================================================
// Frame Allocator Interface
// ============================================================================

/// Zero-allocation trait for supplying 4KB physical frames to the page table walker.
pub trait FrameAllocator {
    /// Allocate a 4096-byte page-aligned physical frame.
    fn allocate_frame(&mut self) -> Option<PhysAddr>;

    /// Deallocate a previously allocated physical frame.
    fn deallocate_frame(&mut self, frame: PhysAddr);
}

// ============================================================================
// Page Table Entry & Table Structures
// ============================================================================

/// Raw 64-bit page table entry.
#[repr(transparent)]
#[derive(Copy, Clone, Debug, Default, PartialEq, Eq)]
pub struct PageTableEntry(pub u64);

impl PageTableEntry {
    pub const UNUSED: Self = Self(0);

    #[inline]
    #[must_use]
    pub const fn new(raw: u64) -> Self {
        Self(raw)
    }

    #[inline]
    #[must_use]
    pub const fn is_unused(&self) -> bool {
        self.0 == 0
    }

    #[inline]
    #[must_use]
    pub const fn is_present(&self) -> bool {
        (self.0 & MapFlags::PRESENT.0) != 0
    }

    #[inline]
    #[must_use]
    pub const fn is_writable(&self) -> bool {
        (self.0 & MapFlags::WRITE.0) != 0
    }

    #[inline]
    #[must_use]
    pub const fn is_executable(&self) -> bool {
        (self.0 & MapFlags::EXECUTE.0) != 0
    }

    #[inline]
    #[must_use]
    pub const fn is_user(&self) -> bool {
        (self.0 & MapFlags::USER.0) != 0
    }

    #[inline]
    #[must_use]
    pub const fn is_huge(&self) -> bool {
        (self.0 & MapFlags::HUGE_PAGE.0) != 0
    }

    /// Extract physical frame address pointed to by this entry.
    #[inline]
    #[must_use]
    pub const fn frame_address(&self) -> Option<PhysAddr> {
        if self.is_present() {
            let addr = (self.0 as usize) & 0x000F_FFFF_FFFF_F000;
            Some(PhysAddr(addr))
        } else {
            None
        }
    }

    #[inline]
    #[must_use]
    pub const fn flags(&self) -> MapFlags {
        MapFlags(self.0 & 0xFFF)
    }

    #[inline]
    pub fn set(&mut self, frame: PhysAddr, flags: MapFlags) {
        let addr = (frame.as_usize() as u64) & 0x000F_FFFF_FFFF_F000;
        self.0 = addr | (flags.bits() & 0xFFF);
    }

    #[inline]
    pub fn clear(&mut self) {
        self.0 = 0;
    }
}

/// A 4KB page table holding 512 entries.
#[repr(C, align(4096))]
#[derive(Debug)]
pub struct PageTable {
    pub entries: [PageTableEntry; ENTRIES_PER_TABLE],
}

impl Default for PageTable {
    fn default() -> Self {
        Self::new()
    }
}

impl PageTable {
    #[inline]
    #[must_use]
    pub const fn new() -> Self {
        Self {
            entries: [PageTableEntry::UNUSED; ENTRIES_PER_TABLE],
        }
    }

    #[inline]
    pub fn zero(&mut self) {
        for entry in &mut self.entries {
            entry.clear();
        }
    }
}

// ============================================================================
// Virtual Memory Space & Safe Multi-Level Walker
// ============================================================================

/// High-level virtual memory space abstraction managing the root page directory.
pub struct VmSpace {
    root_frame: PhysAddr,
}

impl VmSpace {
    /// Create a new virtual memory space anchored at the provided root physical frame.
    ///
    /// # Safety
    /// `root_frame` must reference a valid, dedicated 4KB-aligned physical page frame.
    #[inline]
    pub unsafe fn new(root_frame: PhysAddr) -> Result<Self, VmError> {
        if !root_frame.is_aligned_4k() {
            return Err(VmError::NotAligned);
        }
        Ok(Self { root_frame })
    }

    #[inline]
    #[must_use]
    pub const fn root_frame(&self) -> PhysAddr {
        self.root_frame
    }

    /// Map a virtual page to a physical page frame under the specified protection flags.
    ///
    /// # Safety
    /// The physical address `paddr` and allocated table frames must point to valid accessible memory.
    pub unsafe fn map<A: FrameAllocator>(
        &mut self,
        vaddr: VirtAddr,
        paddr: PhysAddr,
        flags: MapFlags,
        allocator: &mut A,
    ) -> Result<(), VmError> {
        if !vaddr.is_aligned_4k() || !paddr.is_aligned_4k() {
            return Err(VmError::NotAligned);
        }
        flags.validate_wx()?;

        // SAFETY: Pointer is obtained from verified 4KB-aligned root physical frame.
        let pml4 = unsafe { &mut *(self.root_frame.as_usize() as *mut PageTable) };
        let pml4_idx = vaddr.pml4_index();

        let pdpt_frame = if pml4.entries[pml4_idx].is_present() {
            pml4.entries[pml4_idx].frame_address().ok_or(VmError::InvalidTable)?
        } else {
            let new_frame = allocator.allocate_frame().ok_or(VmError::OutOfMemory)?;
            // SAFETY: Newly allocated frame is zeroed.
            unsafe { (*(new_frame.as_usize() as *mut PageTable)).zero(); }
            let intermediate_flags = MapFlags::PRESENT.union(MapFlags::WRITE).union(MapFlags::USER);
            pml4.entries[pml4_idx].set(new_frame, intermediate_flags);
            new_frame
        };

        // SAFETY: PDPT pointer is derived from validated frame.
        let pdpt = unsafe { &mut *(pdpt_frame.as_usize() as *mut PageTable) };
        let pdpt_idx = vaddr.pdpt_index();

        let pd_frame = if pdpt.entries[pdpt_idx].is_present() {
            pdpt.entries[pdpt_idx].frame_address().ok_or(VmError::InvalidTable)?
        } else {
            let new_frame = allocator.allocate_frame().ok_or(VmError::OutOfMemory)?;
            // SAFETY: Newly allocated frame is zeroed.
            unsafe { (*(new_frame.as_usize() as *mut PageTable)).zero(); }
            let intermediate_flags = MapFlags::PRESENT.union(MapFlags::WRITE).union(MapFlags::USER);
            pdpt.entries[pdpt_idx].set(new_frame, intermediate_flags);
            new_frame
        };

        // SAFETY: PD pointer is derived from validated frame.
        let pd = unsafe { &mut *(pd_frame.as_usize() as *mut PageTable) };
        let pd_idx = vaddr.pd_index();

        let pt_frame = if pd.entries[pd_idx].is_present() {
            pd.entries[pd_idx].frame_address().ok_or(VmError::InvalidTable)?
        } else {
            let new_frame = allocator.allocate_frame().ok_or(VmError::OutOfMemory)?;
            // SAFETY: Newly allocated frame is zeroed.
            unsafe { (*(new_frame.as_usize() as *mut PageTable)).zero(); }
            let intermediate_flags = MapFlags::PRESENT.union(MapFlags::WRITE).union(MapFlags::USER);
            pd.entries[pd_idx].set(new_frame, intermediate_flags);
            new_frame
        };

        // SAFETY: PT pointer is derived from validated frame.
        let pt = unsafe { &mut *(pt_frame.as_usize() as *mut PageTable) };
        let pt_idx = vaddr.pt_index();

        if pt.entries[pt_idx].is_present() {
            return Err(VmError::AlreadyMapped);
        }

        pt.entries[pt_idx].set(paddr, flags.union(MapFlags::PRESENT));
        Ok(())
    }

    /// Unmap a virtual page and return the previously mapped physical frame address.
    ///
    /// # Safety
    /// Calling code must perform appropriate TLB shootdown after unmapping.
    pub unsafe fn unmap<A: FrameAllocator>(
        &mut self,
        vaddr: VirtAddr,
        _allocator: &mut A,
    ) -> Result<PhysAddr, VmError> {
        if !vaddr.is_aligned_4k() {
            return Err(VmError::NotAligned);
        }

        // SAFETY: Root frame access.
        let pml4 = unsafe { &mut *(self.root_frame.as_usize() as *mut PageTable) };
        let pml4_entry = &mut pml4.entries[vaddr.pml4_index()];
        if !pml4_entry.is_present() {
            return Err(VmError::NotMapped);
        }

        // SAFETY: PDPT frame access.
        let pdpt = unsafe { &mut *(pml4_entry.frame_address().ok_or(VmError::InvalidTable)?.as_usize() as *mut PageTable) };
        let pdpt_entry = &mut pdpt.entries[vaddr.pdpt_index()];
        if !pdpt_entry.is_present() {
            return Err(VmError::NotMapped);
        }

        // SAFETY: PD frame access.
        let pd = unsafe { &mut *(pdpt_entry.frame_address().ok_or(VmError::InvalidTable)?.as_usize() as *mut PageTable) };
        let pd_entry = &mut pd.entries[vaddr.pd_index()];
        if !pd_entry.is_present() {
            return Err(VmError::NotMapped);
        }

        // SAFETY: PT frame access.
        let pt = unsafe { &mut *(pd_entry.frame_address().ok_or(VmError::InvalidTable)?.as_usize() as *mut PageTable) };
        let pt_entry = &mut pt.entries[vaddr.pt_index()];
        if !pt_entry.is_present() {
            return Err(VmError::NotMapped);
        }

        let paddr = pt_entry.frame_address().ok_or(VmError::NotMapped)?;
        pt_entry.clear();
        Ok(paddr)
    }

    /// Translate a virtual address to physical address and permission flags.
    ///
    /// # Safety
    /// Table structures in physical memory must be valid.
    #[must_use]
    pub unsafe fn translate(&self, vaddr: VirtAddr) -> Option<(PhysAddr, MapFlags)> {
        // SAFETY: Root table read.
        let pml4 = unsafe { &*(self.root_frame.as_usize() as *const PageTable) };
        let pml4_entry = &pml4.entries[vaddr.pml4_index()];
        if !pml4_entry.is_present() {
            return None;
        }

        // SAFETY: PDPT table read.
        let pdpt = unsafe { &*(pml4_entry.frame_address()?.as_usize() as *const PageTable) };
        let pdpt_entry = &pdpt.entries[vaddr.pdpt_index()];
        if !pdpt_entry.is_present() {
            return None;
        }

        // Check for 1GB huge page
        if pdpt_entry.is_huge() {
            let base = pdpt_entry.frame_address()?.as_usize();
            let offset = vaddr.as_usize() & ((1 << 30) - 1);
            return Some((PhysAddr(base + offset), pdpt_entry.flags()));
        }

        // SAFETY: PD table read.
        let pd = unsafe { &*(pdpt_entry.frame_address()?.as_usize() as *const PageTable) };
        let pd_entry = &pd.entries[vaddr.pd_index()];
        if !pd_entry.is_present() {
            return None;
        }

        // Check for 2MB huge page
        if pd_entry.is_huge() {
            let base = pd_entry.frame_address()?.as_usize();
            let offset = vaddr.as_usize() & ((1 << 21) - 1);
            return Some((PhysAddr(base + offset), pd_entry.flags()));
        }

        // SAFETY: PT table read.
        let pt = unsafe { &*(pd_entry.frame_address()?.as_usize() as *const PageTable) };
        let pt_entry = &pt.entries[vaddr.pt_index()];
        if !pt_entry.is_present() {
            return None;
        }

        let base = pt_entry.frame_address()?.as_usize();
        let offset = vaddr.page_offset();
        Some((PhysAddr(base + offset), pt_entry.flags()))
    }

    /// Check whether a virtual address is mapped.
    ///
    /// # Safety
    /// Root frame memory must be accessible.
    #[inline]
    #[must_use]
    pub unsafe fn is_mapped(&self, vaddr: VirtAddr) -> bool {
        // SAFETY: Guaranteed by caller.
        unsafe { self.translate(vaddr).is_some() }
    }
}

// ============================================================================
// Module Lifecycle & FFI Exports
// ============================================================================

pub static PAGE_TABLE_INITIALIZED: AtomicBool = AtomicBool::new(false);

/// Module initialization.
///
/// # Safety
/// Caller must ensure memory subsystem is ready for page table operations.
#[no_mangle]
pub unsafe extern "C" fn page_table_init() -> c_int {
    // Assert fundamental architectural invariants
    assert!(core::mem::size_of::<PageTable>() == PAGE_SIZE);
    assert!(core::mem::align_of::<PageTable>() == PAGE_SIZE);
    assert!(core::mem::size_of::<PageTableEntry>() == 8);

    PAGE_TABLE_INITIALIZED.store(true, Ordering::Release);
    0
}

/// Module cleanup.
///
/// # Safety
/// Caller must ensure all virtual spaces are flushed or unmapped.
#[no_mangle]
pub unsafe extern "C" fn page_table_exit() {
    PAGE_TABLE_INITIALIZED.store(false, Ordering::Release);
}

// ============================================================================
// Unit Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    struct SimpleFrameAllocator {
        pool: [PageTable; 16],
        allocated: [bool; 16],
    }

    impl SimpleFrameAllocator {
        fn new() -> Self {
            Self {
                pool: [
                    PageTable::new(), PageTable::new(), PageTable::new(), PageTable::new(),
                    PageTable::new(), PageTable::new(), PageTable::new(), PageTable::new(),
                    PageTable::new(), PageTable::new(), PageTable::new(), PageTable::new(),
                    PageTable::new(), PageTable::new(), PageTable::new(), PageTable::new(),
                ],
                allocated: [false; 16],
            }
        }
    }

    impl FrameAllocator for SimpleFrameAllocator {
        fn allocate_frame(&mut self) -> Option<PhysAddr> {
            for (idx, alloc) in self.allocated.iter_mut().enumerate() {
                if !*alloc {
                    *alloc = true;
                    let addr = &mut self.pool[idx] as *mut PageTable as usize;
                    return Some(PhysAddr(addr));
                }
            }
            None
        }

        fn deallocate_frame(&mut self, frame: PhysAddr) {
            for (idx, table) in self.pool.iter_mut().enumerate() {
                let addr = table as *mut PageTable as usize;
                if addr == frame.as_usize() {
                    self.allocated[idx] = false;
                    table.zero();
                    break;
                }
            }
        }
    }

    #[test]
    fn test_canonical_virt_addr() {
        let low_vaddr = VirtAddr::new(0x0000_7FFF_FFFF_0000);
        assert!(low_vaddr.is_ok());
        assert!(low_vaddr.unwrap().is_aligned_4k());

        let high_vaddr = VirtAddr::new(0xFFFF_8000_0000_0000);
        assert!(high_vaddr.is_ok());

        let non_canonical = VirtAddr::new(0x000F_8000_0000_0000);
        assert_eq!(non_canonical, Err(VmError::InvalidAddress));
    }

    #[test]
    fn test_virt_addr_indexing() {
        // Address: PML4=1, PDPT=2, PD=3, PT=4, Offset=0x123
        let raw = (1 << 39) | (2 << 30) | (3 << 21) | (4 << 12) | 0x123;
        let vaddr = VirtAddr::new(raw).expect("valid canonical addr");
        assert_eq!(vaddr.pml4_index(), 1);
        assert_eq!(vaddr.pdpt_index(), 2);
        assert_eq!(vaddr.pd_index(), 3);
        assert_eq!(vaddr.pt_index(), 4);
        assert_eq!(vaddr.page_offset(), 0x123);
    }

    #[test]
    fn test_wx_security_enforcement() {
        // Read + Write is permitted
        let rw = MapFlags::new(MapFlags::READ.bits() | MapFlags::WRITE.bits());
        assert!(rw.is_ok());

        // Read + Execute is permitted
        let rx = MapFlags::new(MapFlags::READ.bits() | MapFlags::EXECUTE.bits());
        assert!(rx.is_ok());

        // Write + Execute must be strictly rejected by W^X invariant
        let wx = MapFlags::new(MapFlags::WRITE.bits() | MapFlags::EXECUTE.bits());
        assert_eq!(wx, Err(VmError::WritableAndExecutableViolation));

        // Bypass via allow_wx
        // SAFETY: Verified test bypass
        let allowed_wx = unsafe { MapFlags::allow_wx(MapFlags::WRITE.bits() | MapFlags::EXECUTE.bits()) };
        assert!(allowed_wx.is_writable());
        assert!(allowed_wx.is_executable());
    }

    #[test]
    fn test_page_table_entry_layout() {
        let mut entry = PageTableEntry::new(0);
        assert!(entry.is_unused());

        let frame = PhysAddr::new(0x1000_0000).unwrap();
        let flags = MapFlags::PRESENT.union(MapFlags::WRITE).union(MapFlags::USER);
        entry.set(frame, flags);

        assert!(entry.is_present());
        assert!(entry.is_writable());
        assert!(entry.is_user());
        assert_eq!(entry.frame_address(), Some(frame));

        entry.clear();
        assert!(entry.is_unused());
    }

    #[test]
    fn test_vmspace_mapping_lifecycle() {
        let mut allocator = SimpleFrameAllocator::new();
        let root_frame = allocator.allocate_frame().expect("root table frame");
        
        // SAFETY: root_frame is guaranteed valid by test frame allocator
        let mut vmspace = unsafe { VmSpace::new(root_frame).expect("valid root") };

        let vaddr = VirtAddr::new(0x0000_1234_5678_0000).unwrap();
        let paddr = PhysAddr::new(0x2000_0000).unwrap();
        let flags = MapFlags::PRESENT.union(MapFlags::READ).union(MapFlags::WRITE);

        // Verify unmapped initially
        // SAFETY: Valid vmspace
        assert!(!unsafe { vmspace.is_mapped(vaddr) });

        // Map page
        // SAFETY: Addresses and test allocator are valid
        let map_res = unsafe { vmspace.map(vaddr, paddr, flags, &mut allocator) };
        assert!(map_res.is_ok());

        // Verify mapped and translated
        // SAFETY: Valid vmspace
        assert!(unsafe { vmspace.is_mapped(vaddr) });
        // SAFETY: Valid vmspace
        let trans = unsafe { vmspace.translate(vaddr) };
        assert!(trans.is_some());
        let (translated_paddr, translated_flags) = trans.unwrap();
        assert_eq!(translated_paddr, paddr);
        assert!(translated_flags.contains(MapFlags::WRITE));

        // Mapping again should return AlreadyMapped
        // SAFETY: Valid vmspace
        let dup_res = unsafe { vmspace.map(vaddr, paddr, flags, &mut allocator) };
        assert_eq!(dup_res, Err(VmError::AlreadyMapped));

        // Unmap page
        // SAFETY: Valid vmspace
        let unmap_res = unsafe { vmspace.unmap(vaddr, &mut allocator) };
        assert_eq!(unmap_res, Ok(paddr));
        // SAFETY: Valid vmspace
        assert!(!unsafe { vmspace.is_mapped(vaddr) });
    }

    #[test]
    fn test_module_lifecycle() {
        // SAFETY: Preconditions verified
        unsafe {
            assert_eq!(page_table_init(), 0);
            assert!(PAGE_TABLE_INITIALIZED.load(Ordering::Acquire));
            page_table_exit();
            assert!(!PAGE_TABLE_INITIALIZED.load(Ordering::Acquire));
        }
    }
}
