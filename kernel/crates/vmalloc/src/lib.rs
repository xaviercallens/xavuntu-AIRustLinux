#![no_std]
#![deny(clippy::all)]
#![warn(clippy::pedantic)]

//! Virtual memory allocator
//!
//! This module implements freestanding vmalloc functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel mm/vmalloc.c, backed by physical page allocation without libc dependencies.

#[cfg(test)]
extern crate std;

use core::ffi::{c_int, c_ulong, c_void};
use core::sync::atomic::{AtomicBool, Ordering};

const VMALLOC_MAGIC: u32 = 0x564D_414C; // "VMAL"
const PAGE_SIZE: usize = 4096;

#[repr(C)]
struct VmallocArea {
    magic: u32,
    order: c_int,
    size: usize,
    nr_pages: usize,
}

#[cfg(not(test))]
extern "C" {
    fn alloc_pages(order: c_int) -> *mut c_void;
    fn free_pages(ptr: *mut c_void, order: c_int);
    fn page_size() -> c_ulong;
}

#[cfg(test)]
use self::tests::{alloc_pages, free_pages, page_size};

pub static VMALLOC_INITIALIZED: AtomicBool = AtomicBool::new(false);
pub static VMALLOC_LOCK: kernel_types::SpinLock<()> = kernel_types::SpinLock::new(());

/// Module initialization
#[no_mangle]
/// # Safety
/// Caller must ensure safety preconditions.
pub unsafe extern "C" fn vmalloc_init() -> c_int {
    let _guard = VMALLOC_LOCK.lock();
    VMALLOC_INITIALIZED.store(true, Ordering::Release);
    0
}

/// Module cleanup
#[no_mangle]
/// # Safety
/// Caller must ensure safety preconditions.
pub unsafe extern "C" fn vmalloc_exit() {
    let _guard = VMALLOC_LOCK.lock();
    VMALLOC_INITIALIZED.store(false, Ordering::Release);
}

/// Helper to compute minimum buddy order for given size
fn size_to_order(total_bytes: usize) -> c_int {
    let pg_size = unsafe { page_size() as usize };
    let mut order = 0;
    while (pg_size << order) < total_bytes && order < 11 {
        order += 1;
    }
    order as c_int
}

/// Fallibly allocate virtually contiguous memory backed by buddy pages.
///
/// Returns a non-null pointer to usable memory following the tracking header.
///
/// # Errors
/// - `AllocError::InvalidSize` if `size == 0` or header addition overflows.
/// - `AllocError::InvalidOrder` if `order >= 11`.
/// - `AllocError::OutOfMemory` if physical page allocation fails.
pub fn try_vmalloc(size: usize) -> Result<core::ptr::NonNull<u8>, kernel_types::AllocError> {
    if size == 0 {
        return Err(kernel_types::AllocError::InvalidSize);
    }

    let header_size = core::mem::size_of::<VmallocArea>();
    let total_bytes = size.checked_add(header_size).ok_or(kernel_types::AllocError::InvalidSize)?;

    let order = size_to_order(total_bytes);
    if order >= 11 {
        return Err(kernel_types::AllocError::InvalidOrder);
    }

    let _guard = VMALLOC_LOCK.lock();

    let page_mem = unsafe { alloc_pages(order) };
    if page_mem.is_null() {
        return Err(kernel_types::AllocError::OutOfMemory);
    }

    let area = page_mem as *mut VmallocArea;
    let nr_pages = (1 << order) as usize;

    // SAFETY: page_mem is verified non-null and allocated from underlying buddy allocator
    unsafe {
        (*area).magic = VMALLOC_MAGIC;
        (*area).order = order;
        (*area).size = size;
        (*area).nr_pages = nr_pages;

        let user_ptr = (page_mem as usize + header_size) as *mut u8;
        core::ptr::NonNull::new(user_ptr).ok_or(kernel_types::AllocError::OutOfMemory)
    }
}

/// Allocate virtually contiguous memory backed by physical pages.
///
/// # Safety
/// The caller must ensure that the allocated memory is initialized before use
/// and released via `vfree`.
#[no_mangle]
pub unsafe extern "C" fn vmalloc(size: usize) -> *mut c_void {
    match try_vmalloc(size) {
        Ok(non_null) => non_null.as_ptr() as *mut c_void,
        Err(_) => core::ptr::null_mut(),
    }
}


/// Free virtually contiguous memory allocated with `vmalloc`.
///
/// # Safety
/// `addr` must point to memory returned by `vmalloc`, or be null / sentinel.
#[no_mangle]
pub unsafe extern "C" fn vfree(addr: *mut c_void) {
    if addr.is_null() || addr as usize == 1 {
        return;
    }

    let header_size = core::mem::size_of::<VmallocArea>();
    let area_addr = addr as usize - header_size;
    let area = area_addr as *mut VmallocArea;

    let _guard = VMALLOC_LOCK.lock();

    unsafe {
        // Validate magic header to protect against double free and alien pointers
        if (*area).magic != VMALLOC_MAGIC {
            return;
        }

        // Invalidate magic immediately to mitigate double-free corruption
        (*area).magic = 0;
        let order = (*area).order;

        free_pages(area as *mut c_void, order);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;
    use std::vec::Vec;
    use std::vec;

    static MOCK_PAGES: Mutex<Vec<Vec<u8>>> = Mutex::new(Vec::new());

    pub(crate) unsafe extern "C" fn alloc_pages(order: c_int) -> *mut c_void {
        if order < 0 || order >= 11 {
            return core::ptr::null_mut();
        }
        let size = 4096 * (1 << order);
        let mut buf = vec![0u8; size];
        let ptr = buf.as_mut_ptr() as *mut c_void;
        let mut pool = MOCK_PAGES.lock().unwrap();
        pool.push(buf);
        ptr
    }

    pub(crate) unsafe extern "C" fn free_pages(_ptr: *mut c_void, _order: c_int) {
        // In mock test harness, page free accepts the call safely
    }

    pub(crate) unsafe extern "C" fn page_size() -> c_ulong {
        4096
    }

    #[test]
    fn test_init_exit() {
        unsafe {
            assert_eq!(vmalloc_init(), 0);
            assert!(VMALLOC_INITIALIZED.load(Ordering::Acquire));
            vmalloc_exit();
            assert!(!VMALLOC_INITIALIZED.load(Ordering::Acquire));
        }
    }

    #[test]
    fn test_vmalloc_basic_alloc_and_free() {
        unsafe {
            let ptr = vmalloc(1024);
            assert!(!ptr.is_null());
            vfree(ptr);
        }
    }

    #[test]
    fn test_vmalloc_zero_size() {
        unsafe {
            let ptr = vmalloc(0);
            assert!(ptr.is_null());
        }
    }

    #[test]
    fn test_vmalloc_write_and_read() {
        unsafe {
            let ptr = vmalloc(256) as *mut u8;
            assert!(!ptr.is_null());
            for i in 0..256 {
                core::ptr::write(ptr.add(i), (i & 0xFF) as u8);
            }
            for i in 0..256 {
                assert_eq!(core::ptr::read(ptr.add(i)), (i & 0xFF) as u8);
            }
            vfree(ptr as *mut c_void);
        }
    }

    #[test]
    fn test_vmalloc_sentinel_and_null_free() {
        unsafe {
            vfree(core::ptr::null_mut());
            vfree(1 as *mut c_void);
        }
    }

    #[test]
    fn test_vmalloc_double_free_mitigation() {
        unsafe {
            let ptr = vmalloc(512);
            assert!(!ptr.is_null());
            vfree(ptr);
            // Second free should safely be rejected by magic check
            vfree(ptr);
        }
    }

    #[test]
    fn test_vmalloc_large_allocation() {
        unsafe {
            let ptr = vmalloc(16 * 1024); // 16 KB -> order 3
            assert!(!ptr.is_null());
            vfree(ptr);
        }
    }

    #[test]
    fn test_try_vmalloc_success() {
        let res = try_vmalloc(1024);
        assert!(res.is_ok());
        let non_null = res.unwrap();
        unsafe {
            let ptr = non_null.as_ptr();
            for i in 0..1024 {
                core::ptr::write(ptr.add(i), 0xAA);
            }
            assert_eq!(core::ptr::read(ptr), 0xAA);
            assert_eq!(core::ptr::read(ptr.add(1023)), 0xAA);
            vfree(ptr as *mut c_void);
        }
    }

    #[test]
    fn test_try_vmalloc_zero_size() {
        let res = try_vmalloc(0);
        assert_eq!(res, Err(kernel_types::AllocError::InvalidSize));
    }

    #[test]
    fn test_try_vmalloc_overflow() {
        let res = try_vmalloc(usize::MAX);
        assert_eq!(res, Err(kernel_types::AllocError::InvalidSize));
    }

    #[test]
    fn test_try_vmalloc_order_too_large() {
        let res = try_vmalloc(64 * 1024 * 1024); // Exceeds order 10 (4096 << 10 = 4MB)
        assert_eq!(res, Err(kernel_types::AllocError::InvalidOrder));
    }

    #[test]
    fn test_vmalloc_smp_concurrency() {
        use std::thread;
        use std::vec::Vec;

        let mut handles = Vec::new();
        for t in 0..4 {
            let handle = thread::spawn(move || {
                for i in 0..50 {
                    let size = 128 + ((t * 10 + i) % 512);
                    unsafe {
                        let ptr = vmalloc(size) as *mut u8;
                        assert!(!ptr.is_null());
                        // Write thread-specific pattern
                        for b in 0..size {
                            core::ptr::write(ptr.add(b), (t as u8).wrapping_add(b as u8));
                        }
                        // Verify pattern
                        for b in 0..size {
                            assert_eq!(core::ptr::read(ptr.add(b)), (t as u8).wrapping_add(b as u8));
                        }
                        vfree(ptr as *mut c_void);
                    }
                }
            });
            handles.push(handle);
        }

        for handle in handles {
            handle.join().unwrap();
        }
    }
}
