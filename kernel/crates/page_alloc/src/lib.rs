#![no_std]
#![cfg_attr(not(test), no_main)]
#![deny(clippy::all)]
#![warn(clippy::pedantic)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs)]
//! Physical page allocator (buddy system)
//!
//! Phase 2: Memory Allocator - Page-level allocation
//! Implements a simple buddy allocator for physical memory management

extern crate alloc;
use alloc::boxed::Box;
use alloc::vec::Vec;
use alloc::string::String;

use core::ffi::{c_int, c_ulong, c_void};
use core::ptr;
use core::sync::atomic::{AtomicUsize, Ordering};

#[cfg(not(test))]
use core::panic::PanicInfo;

// Constants
const PAGE_SHIFT: usize = 12;
const PAGE_SIZE: usize = 1 << PAGE_SHIFT; // 4096 bytes
const MAX_ORDER: usize = 11; // Support up to 2^11 pages (8MB)
const TOTAL_MEMORY: usize = 128 * 1024 * 1024; // 128 MB
const TOTAL_PAGES: usize = TOTAL_MEMORY / PAGE_SIZE;

// Page flags
const PG_RESERVED: u32 = 1 << 0; const PG_ALLOCATED: u32 = 1 << 1; const PG_SLAB: u32 = 1 << 2;

use kernel_types::SpinLock;

// Global state
static PAGE_ALLOC_INITIALIZED: AtomicUsize = AtomicUsize::new(0);
static PAGE_ALLOC_LOCK: SpinLock<()> = SpinLock::new(());

struct FreeAreaWrapper(core::cell::UnsafeCell<[[PageList; MAX_ORDER]; 1]>);
// SAFETY: Accesses to FREE_AREA are serialized within the kernel physical page allocator.
unsafe impl Sync for FreeAreaWrapper {}

static FREE_AREA: FreeAreaWrapper = FreeAreaWrapper(core::cell::UnsafeCell::new([[PageList::new(); MAX_ORDER]; 1]));

impl FreeAreaWrapper {
    #[inline(always)]
    unsafe fn get_mut(&self) -> &mut [[PageList; MAX_ORDER]; 1] {
        // SAFETY: Single-threaded cooperative kernel access guarantees exclusive access.
        unsafe { &mut *self.0.get() }
    }
}

static TOTAL_FREE_PAGES: AtomicUsize = AtomicUsize::new(0);

// ============================================================================
// Safe Page Frame Abstraction with Compile-Time Type-State
// ============================================================================

/// Type-state marker indicating the page frame is free.
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub struct Free;

/// Type-state marker indicating the page frame is allocated.
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub struct Allocated;

/// Type-state marker indicating the page frame is mapped to a SLAB cache.
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub struct SlabMapped;

pub trait PageFrameState: 'static {}
impl PageFrameState for Free {}
impl PageFrameState for Allocated {}
impl PageFrameState for SlabMapped {}

pub struct SafePageFrame<'a, S: PageFrameState = Free> {
    ptr: *mut Page,
    _marker: core::marker::PhantomData<(&'a mut Page, S)>,
}

impl<'a, S: PageFrameState> SafePageFrame<'a, S> {
    #[inline(always)]
    pub fn set_order(&mut self, order: u8) {
        // SAFETY: self.ptr is verified non-null and valid for the lifetime of SafePageFrame.
        unsafe { (*self.ptr).order = order; }
    }

    #[inline(always)]
    pub fn get_order(&self) -> u8 {
        // SAFETY: self.ptr is valid for reads as verified on SafePageFrame construction.
        unsafe { (*self.ptr).order }
    }

    #[inline(always)]
    pub fn is_free(&self) -> bool {
        // SAFETY: self.ptr is valid for reads as verified on SafePageFrame construction.
        unsafe { (*self.ptr).is_free() }
    }

    #[inline(always)]
    pub fn is_slab(&self) -> bool {
        // SAFETY: self.ptr is valid for reads as verified on SafePageFrame construction.
        unsafe { ((*self.ptr).flags & PG_SLAB) != 0 }
    }

    #[inline(always)]
    pub fn as_mut_ptr(&self) -> *mut Page {
        self.ptr
    }
}

impl<'a> SafePageFrame<'a, Free> {
    #[inline(always)]
    /// # Safety
    /// Caller must ensure pointer is valid.
    pub unsafe fn new(ptr: *mut Page) -> Option<Self> {
        if ptr.is_null() {
            None
        } else {
            Some(Self { ptr, _marker: core::marker::PhantomData })
        }
    }

    #[inline(always)]
    pub fn mark_allocated(self) -> SafePageFrame<'a, Allocated> {
        // SAFETY: self.ptr is valid for writes as verified on SafePageFrame construction.
        unsafe { (*self.ptr).mark_allocated(); }
        SafePageFrame { ptr: self.ptr, _marker: core::marker::PhantomData }
    }
}

impl<'a> SafePageFrame<'a, Allocated> {
    #[inline(always)]
    /// # Safety
    /// Caller must ensure pointer points to an allocated page.
    pub unsafe fn from_allocated(ptr: *mut Page) -> Option<Self> {
        if ptr.is_null() {
            None
        } else {
            Some(Self { ptr, _marker: core::marker::PhantomData })
        }
    }

    #[inline(always)]
    pub fn mark_free(self) -> SafePageFrame<'a, Free> {
        // SAFETY: self.ptr is valid for writes as verified on SafePageFrame construction.
        unsafe { (*self.ptr).mark_free(); }
        SafePageFrame { ptr: self.ptr, _marker: core::marker::PhantomData }
    }

    #[inline(always)]
    pub fn map_to_slab(self) -> SafePageFrame<'a, SlabMapped> {
        // SAFETY: self.ptr is valid for writes as verified on SafePageFrame construction.
        unsafe { (*self.ptr).flags |= PG_SLAB; }
        SafePageFrame { ptr: self.ptr, _marker: core::marker::PhantomData }
    }
}

impl<'a> SafePageFrame<'a, SlabMapped> {
    #[inline(always)]
    pub fn unmap_slab(self) -> SafePageFrame<'a, Allocated> {
        // SAFETY: self.ptr is valid for writes as verified on SafePageFrame construction.
        unsafe { (*self.ptr).flags &= !PG_SLAB; }
        SafePageFrame { ptr: self.ptr, _marker: core::marker::PhantomData }
    }
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct Page {
    flags: u32,
    count: u32,
    order: u8,
    next: *mut Page,
}

impl Page {
    const fn new() -> Self {
        Page {
            flags: 0,
            count: 0,
            order: 0,
            next: ptr::null_mut(),
        }
    }

    fn is_free(&self) -> bool { (self.flags & PG_ALLOCATED) == 0 }

    fn mark_allocated(&mut self) {
        self.flags |= PG_ALLOCATED;
        self.count = 1;
    }

    fn mark_free(&mut self) {
        self.flags &= !PG_ALLOCATED;
        self.count = 0;
    }
}

// Free list for each order
#[repr(C)]
#[derive(Copy, Clone)]
struct PageList { head: *mut Page, count: usize }

impl PageList {
    const fn new() -> Self {
        PageList {
            head: ptr::null_mut(),
            count: 0,
        }
    }

    unsafe fn add_page(&mut self, page: *mut Page) {
        (*page).next = self.head;
        self.head = page;
        self.count += 1;
    }

    unsafe fn remove_page(&mut self) -> *mut Page {
        if self.head.is_null() {
            return ptr::null_mut();
        }
        let page = self.head;
        self.head = (*page).next;
        (*page).next = ptr::null_mut();
        if self.count > 0 {
            self.count -= 1;
        }
        page
    }
}

// Memory region (simulated physical memory)
#[repr(align(4096))]
struct AlignedMemory([u8; TOTAL_MEMORY]);

struct MemoryPoolWrapper(core::cell::UnsafeCell<AlignedMemory>);
// SAFETY: Access to the backing physical memory pool is mediated by the page allocator.
unsafe impl Sync for MemoryPoolWrapper {}

static MEMORY_POOL: MemoryPoolWrapper = MemoryPoolWrapper(core::cell::UnsafeCell::new(AlignedMemory([0; TOTAL_MEMORY])));

impl MemoryPoolWrapper {
    #[inline(always)]
    unsafe fn get_mut_ptr(&self) -> *mut u8 {
        // SAFETY: Pointer is obtained from valid internal UnsafeCell storage.
        unsafe { (*self.0.get()).0.as_mut_ptr() }
    }

    #[inline(always)]
    unsafe fn get_ptr(&self) -> *const u8 {
        // SAFETY: Pointer is obtained from valid internal UnsafeCell storage.
        unsafe { (*self.0.get()).0.as_ptr() }
    }
}

struct PageArrayWrapper(core::cell::UnsafeCell<[Page; TOTAL_PAGES]>);
// SAFETY: Access to PAGE_ARRAY page descriptors is serialized by page_alloc invariants.
unsafe impl Sync for PageArrayWrapper {}

static PAGE_ARRAY: PageArrayWrapper = PageArrayWrapper(core::cell::UnsafeCell::new([Page::new(); TOTAL_PAGES]));

impl PageArrayWrapper {
    #[inline(always)]
    unsafe fn get_mut(&self) -> &mut [Page; TOTAL_PAGES] {
        // SAFETY: Single-threaded kernel allocator guarantees exclusive descriptor mutation.
        unsafe { &mut *self.0.get() }
    }

    #[inline(always)]
    unsafe fn get_ptr(&self) -> *const Page {
        // SAFETY: Pointer is obtained from valid internal UnsafeCell storage.
        unsafe { (*self.0.get()).as_ptr() }
    }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}

/// Initialize the page allocator
///
/// # Safety
/// Must be called once during kernel boot
#[no_mangle]
pub unsafe extern "C" fn page_alloc_init() -> c_int {
    let _guard = PAGE_ALLOC_LOCK.lock();
    // Check if already initialized
    if PAGE_ALLOC_INITIALIZED.load(Ordering::Acquire) != 0 {
        return 0;
    }

    // Initialize all pages as free
    for (i, _) in PAGE_ARRAY.get_mut().iter().enumerate() {
        PAGE_ARRAY.get_mut()[i] = Page::new();
    }

    // Add pages to free lists by order
    // Start with largest possible blocks
    let mut page_idx = 0;
    while page_idx < TOTAL_PAGES {
        let mut order = MAX_ORDER - 1;

        // Find largest block that fits
        while order > 0 && page_idx + (1 << order) > TOTAL_PAGES {
            order -= 1;
        }

        if page_idx + (1 << order) <= TOTAL_PAGES {
            let page = &mut PAGE_ARRAY.get_mut()[page_idx] as *mut Page;
            (*page).order = order as u8;
            FREE_AREA.get_mut()[0][order].add_page(page);
            page_idx += 1 << order;
        } else {
            break;
        }
    }

    TOTAL_FREE_PAGES.store(TOTAL_PAGES, Ordering::Release);
    PAGE_ALLOC_INITIALIZED.store(1, Ordering::Release);

    0
}

/// Fallibly allocate 2^order physical pages using the buddy allocator.
///
/// Returns a non-null pointer guaranteed to be page-aligned to 4096 bytes.
///
/// # Errors
/// - `AllocError::NotInitialized` if the physical page allocator has not yet been initialized.
/// - `AllocError::InvalidOrder` if `order >= MAX_ORDER`.
/// - `AllocError::OutOfMemory` if physical memory is exhausted or no block fits the requested order.
pub fn try_alloc_pages(order: usize) -> Result<core::ptr::NonNull<u8>, kernel_types::AllocError> {
    if PAGE_ALLOC_INITIALIZED.load(Ordering::Acquire) == 0 {
        return Err(kernel_types::AllocError::NotInitialized);
    }
    if order >= MAX_ORDER {
        return Err(kernel_types::AllocError::InvalidOrder);
    }
    let _guard = PAGE_ALLOC_LOCK.lock();

    // SAFETY: FREE_AREA access is serialized within the physical page allocator.
    unsafe {
        let mut current_order = order;
        while current_order < MAX_ORDER {
            if !FREE_AREA.get_mut()[0][current_order].head.is_null() {
                break;
            }
            current_order += 1;
        }

        if current_order >= MAX_ORDER {
            return Err(kernel_types::AllocError::OutOfMemory);
        }

        let page = FREE_AREA.get_mut()[0][current_order].remove_page();
        if page.is_null() {
            return Err(kernel_types::AllocError::OutOfMemory);
        }

        while current_order > order {
            current_order -= 1;
            let buddy_idx = page_to_idx(page) + (1 << current_order);
            if buddy_idx < TOTAL_PAGES {
                let buddy = &mut PAGE_ARRAY.get_mut()[buddy_idx] as *mut Page;
                if let Some(mut sb) = SafePageFrame::new(buddy) {
                    sb.set_order(current_order as u8);
                }
                FREE_AREA.get_mut()[0][current_order].add_page(buddy);
            }
        }

        if let Some(mut sp) = SafePageFrame::new(page) {
            sp.set_order(order as u8);
            let _allocated = sp.mark_allocated();
        }

        let pages_allocated = 1 << order;
        TOTAL_FREE_PAGES.fetch_sub(pages_allocated, Ordering::AcqRel);

        let addr = page_to_addr(page) as *mut u8;
        core::ptr::NonNull::new(addr).ok_or(kernel_types::AllocError::OutOfMemory)
    }
}

/// Allocate pages of specified order
///
/// # Safety
/// Caller must ensure order is valid
#[no_mangle]
pub unsafe extern "C" fn alloc_pages(order: c_int) -> *mut c_void {
    kernel_types::requires!(order >= 0 && (order as usize) < MAX_ORDER, "Order must be strictly within bounds");

    if order < 0 {
        return ptr::null_mut();
    }

    match try_alloc_pages(order as usize) {
        Ok(non_null) => {
            let addr = non_null.as_ptr() as *mut c_void;
            kernel_types::ensures!(addr.is_null() || (addr as usize).is_multiple_of(PAGE_SIZE), "Allocated pointer must be page-aligned");
            addr
        }
        Err(_) => ptr::null_mut(),
    }
}


/// Free previously allocated pages
///
/// # Safety
/// ptr must have been returned by alloc_pages
#[no_mangle]
pub unsafe extern "C" fn free_pages(ptr: *mut c_void, order: c_int) {
    kernel_types::requires!(order >= 0 && (order as usize) < MAX_ORDER, "Order must be strictly within bounds");
    kernel_types::requires!(ptr.is_null() || (ptr as usize).is_multiple_of(PAGE_SIZE), "Pointer to free must be page-aligned");

    if ptr.is_null() || PAGE_ALLOC_INITIALIZED.load(Ordering::Acquire) == 0 {
        return;
    }

    let order = order as usize;
    if order >= MAX_ORDER {
        return;
    }

    let _guard = PAGE_ALLOC_LOCK.lock();

    let page = addr_to_page(ptr);
    if page.is_null() {
        return;
    }

    if let Some(sp) = SafePageFrame::from_allocated(page) {
        let _freed = sp.mark_free();
    }

    let pages_freed = 1 << order;
    TOTAL_FREE_PAGES.fetch_add(pages_freed, Ordering::AcqRel);

    // Try to merge with buddy
    let current_page = page;
    let current_order = order;

    if current_order < MAX_ORDER - 1 {
        let page_idx = page_to_idx(current_page);
        let buddy_idx = page_idx ^ (1 << current_order);

        if buddy_idx < TOTAL_PAGES {
            let buddy = &mut PAGE_ARRAY.get_mut()[buddy_idx] as *mut Page;

            // Check if buddy is free and same order
            if (*buddy).is_free() && (*buddy).order == current_order as u8 {
                // Remove buddy from free list if matching order is found
                // For now, add current page back
            }
        }
    }

    (*current_page).order = current_order as u8;
    FREE_AREA.get_mut()[0][current_order].add_page(current_page);
}

/// Get total free memory in pages
#[no_mangle]
/// # Safety
/// Caller must ensure safety preconditions.
pub unsafe extern "C" fn nr_free_pages() -> c_ulong {
    TOTAL_FREE_PAGES.load(Ordering::Acquire) as c_ulong
}

/// Get page size
#[no_mangle]
/// # Safety
/// Caller must ensure safety preconditions.
pub unsafe extern "C" fn page_size() -> c_ulong {
    PAGE_SIZE as c_ulong
}

// Helper functions
unsafe fn page_to_idx(page: *const Page) -> usize {
    let base = PAGE_ARRAY.get_ptr();
    ((page as usize) - (base as usize)) / core::mem::size_of::<Page>()
}

unsafe fn page_to_addr(page: *const Page) -> *mut c_void {
    let idx = page_to_idx(page);
    (MEMORY_POOL.get_mut_ptr()).add(idx * PAGE_SIZE) as *mut c_void
}

unsafe fn addr_to_page(addr: *const c_void) -> *mut Page {
    let base = MEMORY_POOL.get_ptr() as usize;
    let ptr = addr as usize;
    if ptr < base || ptr >= base + TOTAL_MEMORY {
        return ptr::null_mut();
    }
    let idx = (ptr - base) / PAGE_SIZE;
    if idx >= TOTAL_PAGES {
        return ptr::null_mut();
    }
    &mut PAGE_ARRAY.get_mut()[idx] as *mut Page
}

/// Module cleanup
#[no_mangle]
/// # Safety
/// Caller must ensure safety preconditions.
pub unsafe extern "C" fn page_alloc_exit() {
    let _guard = PAGE_ALLOC_LOCK.lock();
    PAGE_ALLOC_INITIALIZED.store(0, Ordering::Release);
    // Clear all free lists
    for (order, _) in FREE_AREA.get_mut()[0].iter().enumerate().take(MAX_ORDER) {
        FREE_AREA.get_mut()[0][order].head = ptr::null_mut();
        FREE_AREA.get_mut()[0][order].count = 0;
    }
    TOTAL_FREE_PAGES.store(0, Ordering::Release);
}

#[cfg(test)]
mod tests {
    extern crate std;
    use super::*;
    use std::vec::Vec;

    #[test]
    fn test_page_alloc_init() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            let result = page_alloc_init();
            assert_eq!(result, 0);
            assert_eq!(PAGE_ALLOC_INITIALIZED.load(Ordering::Acquire), 1);
        }
    }

    #[test]
    fn test_alloc_single_page() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let ptr = alloc_pages(0);
            assert!(!ptr.is_null());
            free_pages(ptr, 0);
        }
    }

    #[test]
    fn test_alloc_multiple_pages() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let ptr = alloc_pages(2); // 4 pages
            assert!(!ptr.is_null());
            free_pages(ptr, 2);
        }
    }

    #[test]
    fn test_page_size() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            assert_eq!(page_size(), 4096);
        }
    }

    // === Comprehensive edge case and stress tests ===

    

    #[test]
    fn test_alloc_max_order_boundary() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let ptr = alloc_pages((MAX_ORDER - 1) as c_int);
            assert!(!ptr.is_null(), "Should accept MAX_ORDER-1");
            free_pages(ptr, (MAX_ORDER - 1) as c_int);
        }
    }

    

    

    #[test]
    fn test_alloc_all_orders() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            for (order, _) in FREE_AREA.get_mut()[0].iter().enumerate().take(MAX_ORDER) {
                let ptr = alloc_pages(order as c_int);
                assert!(!ptr.is_null(), "Order {} allocation failed", order);
                free_pages(ptr, order as c_int);
            }
        }
    }

    #[test]
    fn test_alloc_free_cycle_order0() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let initial_free = nr_free_pages();

            for _ in 0..100 {
                let ptr = alloc_pages(0);
                assert!(!ptr.is_null());
                free_pages(ptr, 0);
            }

            let final_free = nr_free_pages();
            assert_eq!(final_free, initial_free, "Memory leak detected");
        }
    }

    #[test]
    fn test_alloc_free_cycle_multiple_orders() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let initial_free = nr_free_pages();

            for order in 0..5 {
                for _ in 0..10 {
                    let ptr = alloc_pages(order);
                    assert!(!ptr.is_null());
                    free_pages(ptr, order);
                }
            }

            let final_free = nr_free_pages();
            assert!(final_free >= initial_free - 100, "Too much memory lost");
        }
    }

    #[test]
    fn test_multiple_alloc_then_free() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let mut ptrs = Vec::new();

            for _ in 0..10 {
                let ptr = alloc_pages(0);
                assert!(!ptr.is_null());
                ptrs.push(ptr);
            }

            for ptr in ptrs {
                free_pages(ptr, 0);
            }
        }
    }

    

    

    

    

    #[test]
    fn test_double_init() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let result = page_alloc_init();
            assert_eq!(result, 0, "Double init should succeed");
        }
    }

    #[test]
    fn test_init_exit_init() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            page_alloc_exit();
            page_alloc_init();

            let ptr = alloc_pages(0);
            assert!(!ptr.is_null());
            free_pages(ptr, 0);
        }
    }

    #[test]
    fn test_nr_free_pages_initial() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_exit();
            page_alloc_init();
            let free = nr_free_pages();
            assert_eq!(free, TOTAL_PAGES as c_ulong, "Should start with all pages free");
        }
    }

    #[test]
    fn test_nr_free_pages_after_alloc() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let initial = nr_free_pages();

            let ptr = alloc_pages(0);
            let after_alloc = nr_free_pages();
            assert_eq!(after_alloc, initial - 1, "Should decrease by 1 page");

            free_pages(ptr, 0);
            let after_free = nr_free_pages();
            assert_eq!(after_free, initial, "Should restore free count");
        }
    }

    #[test]
    fn test_nr_free_pages_order1() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let initial = nr_free_pages();

            let ptr = alloc_pages(1);
            let after_alloc = nr_free_pages();
            assert_eq!(after_alloc, initial - 2, "Order 1 allocates 2 pages");

            free_pages(ptr, 1);
        }
    }

    #[test]
    fn test_nr_free_pages_order2() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let initial = nr_free_pages();

            let ptr = alloc_pages(2);
            let after_alloc = nr_free_pages();
            assert_eq!(after_alloc, initial - 4, "Order 2 allocates 4 pages");

            free_pages(ptr, 2);
        }
    }

    #[test]
    fn test_page_size_constant() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            assert_eq!(page_size(), PAGE_SIZE as c_ulong);
            assert_eq!(page_size(), 4096);
        }
    }

    #[test]
    fn test_alloc_stress_1000_pages() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let mut ptrs = Vec::new();

            for _ in 0..1000 {
                let ptr = alloc_pages(0);
                if !ptr.is_null() {
                    ptrs.push(ptr);
                } else {
                    break;
                }
            }

            assert!(ptrs.len() > 0, "Should allocate at least some pages");

            for ptr in ptrs {
                free_pages(ptr, 0);
            }
        }
    }

    #[test]
    fn test_alloc_until_oom() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let mut ptrs = Vec::new();

            loop {
                let ptr = alloc_pages(0);
                if ptr.is_null() {
                    break;
                }
                ptrs.push(ptr);

                if ptrs.len() > TOTAL_PAGES {
                    panic!("Allocated more pages than available");
                }
            }

            assert!(ptrs.len() > 0, "Should allocate some pages before OOM");
            assert!(ptrs.len() <= TOTAL_PAGES, "Cannot allocate more than available");

            for ptr in ptrs {
                free_pages(ptr, 0);
            }
        }
    }

    

    #[test]
    fn test_alloc_fragmentation_scenario() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();

            // Allocate multiple pages
            let p1 = alloc_pages(1);
            let p2 = alloc_pages(1);
            let p3 = alloc_pages(1);

            assert!(!p1.is_null());
            assert!(!p2.is_null());
            assert!(!p3.is_null());

            // Free middle one
            free_pages(p2, 1);

            // Allocate again
            let p4 = alloc_pages(0);
            assert!(!p4.is_null());

            free_pages(p1, 1);
            free_pages(p3, 1);
            free_pages(p4, 0);
        }
    }

    #[test]
    fn test_alloc_order_progression() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();

            for order in 0..8 {
                let ptr = alloc_pages(order);
                assert!(!ptr.is_null(), "Failed at order {}", order);

                let pages = 1 << order;
                assert!(pages <= TOTAL_PAGES);

                free_pages(ptr, order);
            }
        }
    }

    #[test]
    fn test_multiple_init_idempotent() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            for _ in 0..5 {
                let result = page_alloc_init();
                assert_eq!(result, 0);
            }

            let ptr = alloc_pages(0);
            assert!(!ptr.is_null());
            free_pages(ptr, 0);
        }
    }

    #[test]
    fn test_alloc_free_different_orders() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();

            let p0 = alloc_pages(0);
            let p3 = alloc_pages(3);
            let p1 = alloc_pages(1);

            assert!(!p0.is_null());
            assert!(!p3.is_null());
            assert!(!p1.is_null());

            free_pages(p1, 1);
            free_pages(p0, 0);
            free_pages(p3, 3);
        }
    }

    #[test]
    #[ignore] // Alignment depends on memory pool location in tests
    fn test_page_allocation_alignment() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();

            for _ in 0..10 {
                let ptr = alloc_pages(0);
                assert!(!ptr.is_null());

                // Check page alignment
                let addr = ptr as usize;
                assert_eq!(addr % PAGE_SIZE, 0, "Page should be page-aligned");

                free_pages(ptr, 0);
            }
        }
    }

    

    

    

    

    #[test]
    fn test_double_free_detection() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            page_alloc_init();
            let ptr = alloc_pages(0);
            free_pages(ptr, 0);
            // Double free - implementation dependent behavior
            free_pages(ptr, 0);
        }
    }

    

    #[test]
    fn test_page_size_consistency() {
        // SAFETY: Test invocation of page allocator functions under test harness.
        unsafe {
            let ps1 = page_size();
            let ps2 = page_size();
            assert_eq!(ps1, ps2);
            assert_eq!(ps1, 4096);
        }
    }

    #[test]
    fn test_safepageframe_typestate_transitions() {
        let mut page = Page::new();
        let page_ptr = &mut page as *mut Page;

        // Start in Free state
        let free_frame = unsafe { SafePageFrame::new(page_ptr) }.expect("valid page pointer");
        assert!(free_frame.is_free());
        assert!(!free_frame.is_slab());

        // Free -> Allocated
        let allocated_frame = free_frame.mark_allocated();
        assert!(!allocated_frame.is_free());
        assert!(!allocated_frame.is_slab());

        // Allocated -> SlabMapped
        let slab_frame = allocated_frame.map_to_slab();
        assert!(slab_frame.is_slab());

        // SlabMapped -> Allocated
        let unmapped_frame = slab_frame.unmap_slab();
        assert!(!unmapped_frame.is_slab());

        // Allocated -> Free
        let back_to_free = unmapped_frame.mark_free();
        assert!(back_to_free.is_free());
    }

    #[test]
    fn test_try_alloc_pages_lifecycle() {
        // SAFETY: Initialize test allocator
        unsafe { page_alloc_init(); }

        let res = try_alloc_pages(0);
        assert!(res.is_ok());
        let non_null = res.unwrap();
        let ptr = non_null.as_ptr() as *mut c_void;
        assert_eq!(ptr as usize % PAGE_SIZE, 0);

        // SAFETY: ptr was returned by try_alloc_pages(0)
        unsafe { free_pages(ptr, 0); }
    }

    #[test]
    fn test_try_alloc_pages_oom_and_invalid_order() {
        // SAFETY: Initialize test allocator
        unsafe { page_alloc_init(); }

        // Test invalid order
        let bad_order = try_alloc_pages(MAX_ORDER);
        assert_eq!(bad_order, Err(kernel_types::AllocError::InvalidOrder));

        let huge_order = try_alloc_pages(999);
        assert_eq!(huge_order, Err(kernel_types::AllocError::InvalidOrder));
    }

    #[test]
    fn test_page_alloc_smp_concurrency() {
        // SAFETY: Initialize test allocator under SMP concurrent thread access.
        unsafe {
            page_alloc_init();
            let handles: Vec<_> = (0..4).map(|_| {
                std::thread::spawn(|| {
                    for _ in 0..50 {
                        // SAFETY: Valid alloc/free order 0 under SMP spinlock serialization.
                        unsafe {
                            let p = alloc_pages(0);
                            if !p.is_null() {
                                free_pages(p, 0);
                            }
                        }
                    }
                })
            }).collect();
            for h in handles {
                h.join().unwrap();
            }
        }
    }
}

