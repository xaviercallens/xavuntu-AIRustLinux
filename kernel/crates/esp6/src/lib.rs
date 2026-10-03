#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(non_snake_case)]

use core::ffi::{c_int, c_uchar, c_uint, c_ulong, c_ushort, c_void};
use core::ptr::null_mut;

pub type size_t = usize;
pub type c_size_t = usize;
pub type socklen_t = u32;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct CacheKey {
    pub spi: c_uint,
    pub daddr: [u8; 16],
    pub saddr: [u8; 16],
    pub proto: c_uchar,
    pub family: c_ushort,
    pub ifindex: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct CacheStatistics {
    pub lookups: c_ulong,
    pub hits: c_ulong,
    pub misses: c_ulong,
    pub inserts: c_ulong,
    pub removes: c_ulong,
    pub errors: c_ulong,
}

#[repr(C)]
pub struct CacheEntry {
    pub key: CacheKey,
    pub value: *mut c_void,
    pub next: *mut CacheEntry,
}

pub struct CacheManager {
    head: *mut CacheEntry,
    count: usize,
    stats: CacheStatistics,
}

impl CacheManager {
    pub const fn new() -> Self {
        Self {
            head: null_mut(),
            count: 0,
            stats: CacheStatistics {
                lookups: 0,
                hits: 0,
                misses: 0,
                inserts: 0,
                removes: 0,
                errors: 0,
            },
        }
    }
}

// SAFETY: Both `a` and `b` are checked for null before dereferencing; the caller must
// guarantee that non-null pointers are valid, aligned, and live for the duration of
// this call, which is upheld by all call sites within this module where pointers
// originate from live `CacheEntry` nodes managed by the kernel allocator.
unsafe fn key_eq(a: *const CacheKey, b: *const CacheKey) -> bool {
    if a.is_null() || b.is_null() {
        return false;
    }
    // SAFETY: `a` is non-null (checked above) and points to a valid `CacheKey` as
    // guaranteed by the caller.
    let ka = unsafe { &*a };
    // SAFETY: `b` is non-null (checked above) and points to a valid `CacheKey` as
    // guaranteed by the caller.
    let kb = unsafe { &*b };

    ka.spi == kb.spi
        && ka.daddr == kb.daddr
        && ka.saddr == kb.saddr
        && ka.proto == kb.proto
        && ka.family == kb.family
        && ka.ifindex == kb.ifindex
}

extern "C" {
    fn kmalloc(size: size_t, flags: c_int) -> *mut c_void;
    fn kfree(ptr: *mut c_void);
}

#[no_mangle]
pub extern "C" fn esp6_cache_manager_new() -> *mut CacheManager {
    // SAFETY: `kmalloc` is a kernel allocator that returns either a valid pointer or null;
    // the null case is handled immediately after this call.
    let ptr = unsafe { kmalloc(core::mem::size_of::<CacheManager>(), 0) } as *mut CacheManager;
    if ptr.is_null() {
        return null_mut();
    }

    // SAFETY: `ptr` is non-null and exclusively owned (freshly allocated by kmalloc above);
    // writing a valid `CacheManager` value into it is sound.
    unsafe {
        ptr.write(CacheManager::new());
    }
    ptr
}

#[no_mangle]
// SAFETY: FFI function called by the kernel C side; `mgr` must be a valid pointer
// previously returned by `esp6_cache_manager_new`, or null (null is handled explicitly).
// The caller must not use `mgr` after this call.
pub unsafe extern "C" fn esp6_cache_manager_free(mgr: *mut CacheManager) {
    if mgr.is_null() {
        return;
    }

    // SAFETY: `mgr` is non-null (checked above) and points to a valid `CacheManager`
    // allocated by `esp6_cache_manager_new`; reading its `head` field is sound.
    let mut current = unsafe { (*mgr).head };
    while !current.is_null() {
        // SAFETY: `current` is non-null and points to a live `CacheEntry` node that
        // was allocated by `kmalloc` in `esp6_cache_insert`; reading `next` before
        // freeing is required to advance the iteration.
        let next = unsafe { (*current).next };
        // SAFETY: `current` is a valid, kmalloc-allocated pointer; `kfree` accepts any
        // pointer previously returned by the kernel allocator.
        unsafe { kfree(current as *mut c_void) };
        current = next;
    }

    // SAFETY: `mgr` is a valid, kmalloc-allocated pointer (from `esp6_cache_manager_new`);
    // all entries have been freed above so this is the final deallocation.
    unsafe { kfree(mgr as *mut c_void) };
}

#[no_mangle]
// SAFETY: FFI function called by the kernel C side; `mgr` must be a valid non-null
// pointer to a `CacheManager` (or null, handled explicitly), and `key` must point to
// a valid `CacheKey` for the duration of this call.  `value` is an opaque pointer
// stored verbatim and is not dereferenced here.
pub unsafe extern "C" fn esp6_cache_insert(
    mgr: *mut CacheManager,
    key: *const CacheKey,
    value: *mut c_void,
) -> c_int {
    if mgr.is_null() || key.is_null() {
        return -22;
    }

    // SAFETY: `kmalloc` returns a valid pointer or null; the null case is handled below.
    let entry_ptr = unsafe { kmalloc(core::mem::size_of::<CacheEntry>(), 0) } as *mut CacheEntry;
    if entry_ptr.is_null() {
        // SAFETY: `mgr` is non-null (checked above) and points to a valid `CacheManager`;
        // incrementing the error counter is the only write and no aliasing occurs here.
        unsafe { (*mgr).stats.errors += 1 };
        return -12;
    }

    // SAFETY: `entry_ptr` is non-null and exclusively owned (freshly allocated).
    // `mgr` and `key` are both non-null and valid as checked above.  Writing a
    // `CacheEntry` into `entry_ptr` and updating `mgr` fields is sound because we hold
    // exclusive ownership of the new node and `mgr` is not aliased at this point.
    unsafe {
        entry_ptr.write(CacheEntry {
            key: *key,
            value,
            next: (*mgr).head,
        });

        (*mgr).head = entry_ptr;
        (*mgr).count += 1;
        (*mgr).stats.inserts += 1;
    }

    0
}

#[no_mangle]
// SAFETY: FFI function called by the kernel C side; `mgr` must be a valid pointer to a
// `CacheManager` (or null, handled explicitly), and `key` must point to a valid
// `CacheKey` for the duration of this call.
pub unsafe extern "C" fn esp6_cache_lookup(
    mgr: *mut CacheManager,
    key: *const CacheKey,
) -> *mut c_void {
    if mgr.is_null() || key.is_null() {
        return null_mut();
    }

    // SAFETY: `mgr` is non-null and points to a valid `CacheManager`; incrementing
    // the lookups counter is safe because no aliasing occurs at this point.
    unsafe { (*mgr).stats.lookups += 1 };

    // SAFETY: `mgr` is non-null and valid; reading `head` starts the linked-list walk.
    let mut current = unsafe { (*mgr).head };
    while !current.is_null() {
        // SAFETY: `current` is non-null and points to a live `CacheEntry` node; passing
        // a reference to its `key` field to `key_eq` is sound.
        if unsafe { key_eq(&(*current).key, key) } {
            // SAFETY: `mgr` is non-null and valid; updating the hit counter is safe.
            unsafe { (*mgr).stats.hits += 1 };
            // SAFETY: `current` is non-null and valid; reading the `value` field is sound.
            return unsafe { (*current).value };
        }
        // SAFETY: `current` is non-null and points to a valid `CacheEntry`; reading
        // `next` advances the iteration.
        current = unsafe { (*current).next };
    }

    // SAFETY: `mgr` is non-null and valid; updating the miss counter is safe.
    unsafe { (*mgr).stats.misses += 1 };
    null_mut()
}

#[no_mangle]
// SAFETY: FFI function called by the kernel C side; `mgr` must be a valid pointer to a
// `CacheManager` (or null, handled explicitly), and `key` must point to a valid
// `CacheKey` for the duration of this call.
pub unsafe extern "C" fn esp6_cache_remove(mgr: *mut CacheManager, key: *const CacheKey) -> c_int {
    if mgr.is_null() || key.is_null() {
        return -22;
    }

    let mut prev: *mut CacheEntry = null_mut();
    // SAFETY: `mgr` is non-null and valid; reading `head` starts the linked-list walk.
    let mut current = unsafe { (*mgr).head };

    while !current.is_null() {
        // SAFETY: `current` is non-null and points to a live `CacheEntry`; passing a
        // reference to its `key` field to `key_eq` is sound.
        if unsafe { key_eq(&(*current).key, key) } {
            if prev.is_null() {
                // SAFETY: `mgr` is non-null and valid; `current` is non-null so reading
                // its `next` field and storing it into `mgr.head` is sound.
                unsafe { (*mgr).head = (*current).next };
            } else {
                // SAFETY: `prev` is non-null and points to a live `CacheEntry`; updating
                // its `next` pointer to skip the removed node is sound.
                unsafe { (*prev).next = (*current).next };
            }

            // SAFETY: `mgr` is non-null and valid; decrementing count and updating stats
            // is safe.  `current` was allocated by `kmalloc` and is no longer reachable
            // after the pointer fixup above, so freeing it here is correct.
            unsafe {
                (*mgr).count -= 1;
                (*mgr).stats.removes += 1;
                kfree(current as *mut c_void);
            }

            return 0;
        }

        prev = current;
        // SAFETY: `current` is non-null and points to a valid `CacheEntry`; reading
        // `next` advances the iteration.
        current = unsafe { (*current).next };
    }

    -2
}

#[no_mangle]
// SAFETY: FFI function called by the kernel C side; `mgr` must be a valid pointer to a
// `CacheManager` (or null, handled explicitly).
pub unsafe extern "C" fn esp6_cache_count(mgr: *const CacheManager) -> usize {
    if mgr.is_null() {
        return 0;
    }
    // SAFETY: `mgr` is non-null (checked above) and points to a valid `CacheManager`;
    // reading the `count` field is sound.
    unsafe { (*mgr).count }
}

#[no_mangle]
// SAFETY: FFI function called by the kernel C side; `mgr` must be a valid pointer to a
// `CacheManager` (or null, handled explicitly), and `out_stats` must be a valid,
// writable pointer to a `CacheStatistics` (or null, handled explicitly).
pub unsafe extern "C" fn esp6_cache_get_stats(
    mgr: *const CacheManager,
    out_stats: *mut CacheStatistics,
) -> c_int {
    if mgr.is_null() || out_stats.is_null() {
        return -22;
    }

    // SAFETY: Both `mgr` and `out_stats` are non-null (checked above); `mgr` points to
    // a valid `CacheManager` and `out_stats` points to writable memory of sufficient size
    // as guaranteed by the kernel caller.
    unsafe {
        *out_stats = (*mgr).stats;
    }
    0
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
