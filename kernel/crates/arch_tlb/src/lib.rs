#![no_std]
#![deny(clippy::all)]
#![warn(clippy::pedantic)]
#![allow(clippy::module_name_repetitions, clippy::cast_possible_truncation)]

//! Architecture-specific Translation Lookaside Buffer (TLB) Management and Shootdown.
//!
//! Provides safe abstractions for single-page invalidation (`invlpg` / `sfence.vma`),
//! complete address-space shootdowns, threshold-based range invalidation, and atomic
//! TLB invalidation generation tracking.

use core::ffi::c_int;
use core::sync::atomic::{AtomicBool, AtomicU64, Ordering};

use page_table::{VirtAddr, PAGE_SIZE};

/// Threshold above which range invalidation escalates to a full address space shootdown.
pub const RANGE_FLUSH_THRESHOLD_PAGES: usize = 32;

// ============================================================================
// Telemetry & Atomic State
// ============================================================================

static TLB_PAGE_FLUSHES: AtomicU64 = AtomicU64::new(0);
static TLB_FULL_FLUSHES: AtomicU64 = AtomicU64::new(0);
static TLB_RANGE_FLUSHES: AtomicU64 = AtomicU64::new(0);
static TLB_GENERATION: AtomicU64 = AtomicU64::new(1);

/// Snapshot of TLB operational telemetry.
#[derive(Copy, Clone, Debug, PartialEq, Eq, Default)]
pub struct TlbStats {
    pub page_flushes: u64,
    pub range_flushes: u64,
    pub full_flushes: u64,
    pub generation: u64,
}

// ============================================================================
// TLB Invalidation Primitives
// ============================================================================

/// Invalidate a single virtual page from the TLB.
///
/// # Safety
/// Caller must ensure that modifying hardware page table mappings and shooting down
/// TLB caches does not invalidate active execution contexts.
#[inline]
pub unsafe fn flush_page(vaddr: VirtAddr) {
    TLB_PAGE_FLUSHES.fetch_add(1, Ordering::Relaxed);
    TLB_GENERATION.fetch_add(1, Ordering::Release);

    #[cfg(all(target_arch = "x86_64", not(test)))]
    {
        // SAFETY: Direct hardware instruction on validated virtual address.
        unsafe {
            core::arch::asm!(
                "invlpg [{}]",
                in(reg) vaddr.as_usize(),
                options(nostack, preserves_flags)
            );
        }
    }

    #[cfg(all(target_arch = "riscv64", not(test)))]
    {
        // SAFETY: Direct hardware instruction on validated virtual address.
        unsafe {
            core::arch::asm!(
                "sfence.vma {}, zero",
                in(reg) vaddr.as_usize(),
                options(nostack)
            );
        }
    }

    let _ = vaddr;
}

/// Invalidate all entries in the TLB for the current address space.
///
/// # Safety
/// Caller must ensure that root translation structures remain valid.
#[inline]
pub unsafe fn flush_all() {
    TLB_FULL_FLUSHES.fetch_add(1, Ordering::Relaxed);
    TLB_GENERATION.fetch_add(1, Ordering::Release);

    #[cfg(all(target_arch = "x86_64", not(test)))]
    {
        // SAFETY: Reload CR3 to flush all non-global TLB entries.
        unsafe {
            let cr3: usize;
            core::arch::asm!("mov {}, cr3", out(reg) cr3, options(nostack, nomem));
            core::arch::asm!("mov cr3, {}", in(reg) cr3, options(nostack, nomem));
        }
    }

    #[cfg(all(target_arch = "riscv64", not(test)))]
    {
        // SAFETY: Flush all address mappings across all ASIDs.
        unsafe {
            core::arch::asm!("sfence.vma zero, zero", options(nostack));
        }
    }
}

/// Invalidate a contiguous range of virtual addresses.
///
/// If the range exceeds `RANGE_FLUSH_THRESHOLD_PAGES`, this escalates to `flush_all()`
/// to minimize inter-processor shootdown latency.
///
/// # Safety
/// Caller must guarantee the safety preconditions of `flush_page` and `flush_all`.
pub unsafe fn flush_range(start: VirtAddr, end: VirtAddr) {
    if start >= end {
        return;
    }

    TLB_RANGE_FLUSHES.fetch_add(1, Ordering::Relaxed);

    let span_bytes = end.as_usize().saturating_sub(start.as_usize());
    let page_count = span_bytes / PAGE_SIZE;

    if page_count > RANGE_FLUSH_THRESHOLD_PAGES {
        // SAFETY: Range is large; complete shootdown is strictly more efficient.
        unsafe { flush_all(); }
    } else {
        let mut curr = start.align_down().as_usize();
        let end_aligned = end.as_usize();
        while curr < end_aligned {
            if let Ok(vaddr) = VirtAddr::new(curr) {
                // SAFETY: Invalidate individual page in valid range.
                unsafe { flush_page(vaddr); }
            }
            curr = curr.saturating_add(PAGE_SIZE);
        }
    }
}

/// Retrieve current TLB performance and generation statistics.
#[must_use]
pub fn tlb_stats() -> TlbStats {
    TlbStats {
        page_flushes: TLB_PAGE_FLUSHES.load(Ordering::Relaxed),
        range_flushes: TLB_RANGE_FLUSHES.load(Ordering::Relaxed),
        full_flushes: TLB_FULL_FLUSHES.load(Ordering::Relaxed),
        generation: TLB_GENERATION.load(Ordering::Acquire),
    }
}

// ============================================================================
// Module Lifecycle & FFI Exports
// ============================================================================

pub static ARCH_TLB_INITIALIZED: AtomicBool = AtomicBool::new(false);

/// Module initialization.
///
/// # Safety
/// Caller must ensure CPU paging state is active.
#[no_mangle]
pub unsafe extern "C" fn arch_tlb_init() -> c_int {
    TLB_PAGE_FLUSHES.store(0, Ordering::Relaxed);
    TLB_FULL_FLUSHES.store(0, Ordering::Relaxed);
    TLB_RANGE_FLUSHES.store(0, Ordering::Relaxed);
    TLB_GENERATION.store(1, Ordering::Release);

    ARCH_TLB_INITIALIZED.store(true, Ordering::Release);
    0
}

/// Module cleanup.
///
/// # Safety
/// Caller must ensure no concurrent TLB operations are pending.
#[no_mangle]
pub unsafe extern "C" fn arch_tlb_exit() {
    ARCH_TLB_INITIALIZED.store(false, Ordering::Release);
}

// ============================================================================
// Unit Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_flush_page_increments_telemetry() {
        let initial_stats = tlb_stats();
        let vaddr = VirtAddr::new(0x0000_2000_0000).unwrap();

        // SAFETY: Test execution of flush_page
        unsafe { flush_page(vaddr); }

        let new_stats = tlb_stats();
        assert_eq!(new_stats.page_flushes, initial_stats.page_flushes + 1);
        assert!(new_stats.generation > initial_stats.generation);
    }

    #[test]
    fn test_flush_all_increments_telemetry() {
        let initial_stats = tlb_stats();

        // SAFETY: Test execution of flush_all
        unsafe { flush_all(); }

        let new_stats = tlb_stats();
        assert_eq!(new_stats.full_flushes, initial_stats.full_flushes + 1);
        assert!(new_stats.generation > initial_stats.generation);
    }

    #[test]
    fn test_flush_range_below_threshold() {
        let initial_stats = tlb_stats();
        let start = VirtAddr::new(0x0000_1000_0000).unwrap();
        // 4 pages span
        let end = VirtAddr::new(0x0000_1000_4000).unwrap();

        // SAFETY: Test execution of flush_range
        unsafe { flush_range(start, end); }

        let new_stats = tlb_stats();
        assert_eq!(new_stats.range_flushes, initial_stats.range_flushes + 1);
        assert_eq!(new_stats.page_flushes, initial_stats.page_flushes + 4);
    }

    #[test]
    fn test_flush_range_above_threshold_escalates_to_full() {
        let initial_stats = tlb_stats();
        let start = VirtAddr::new(0x0000_1000_0000).unwrap();
        // 64 pages span (threshold is 32)
        let end = VirtAddr::new(0x0000_1000_0000 + 64 * PAGE_SIZE).unwrap();

        // SAFETY: Test execution of flush_range
        unsafe { flush_range(start, end); }

        let new_stats = tlb_stats();
        assert_eq!(new_stats.range_flushes, initial_stats.range_flushes + 1);
        assert_eq!(new_stats.full_flushes, initial_stats.full_flushes + 1);
    }

    #[test]
    fn test_arch_tlb_lifecycle() {
        // SAFETY: Test preconditions
        unsafe {
            assert_eq!(arch_tlb_init(), 0);
            assert!(ARCH_TLB_INITIALIZED.load(Ordering::Acquire));
            arch_tlb_exit();
            assert!(!ARCH_TLB_INITIALIZED.load(Ordering::Acquire));
        }
    }
}
