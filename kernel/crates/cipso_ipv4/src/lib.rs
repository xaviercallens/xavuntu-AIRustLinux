#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::unnecessary_cast)]

use core::ptr;

// SyncWrapper for safe global mutability
#[repr(transparent)]
pub struct SyncWrapper<T>(pub core::cell::UnsafeCell<T>);
unsafe impl<T> Sync for SyncWrapper<T> {}
impl<T> SyncWrapper<T> {
    pub const fn new(value: T) -> Self {
        Self(core::cell::UnsafeCell::new(value))
    }
    #[inline(always)]
    pub unsafe fn get_mut(&self) -> &mut T {
        // SAFETY: The caller must guarantee exclusive access or single-threaded context.
        unsafe { &mut *self.0.get() }
    }
}

use kernel_types::*;

pub const CIPSO_V4_OPT_LEN_MAX: c_int = 40;
pub const CIPSO_V4_HDR_LEN: c_int = 6;
pub const CIPSO_V4_TAG_RBM_BLEN: c_int = 4;
pub const CIPSO_V4_TAG_ENUM_BLEN: c_int = 4;
pub const CIPSO_V4_TAG_RNG_BLEN: c_int = 4;
pub const CIPSO_V4_TAG_RNG_CAT_MAX: c_int = 8;
pub const CIPSO_V4_TAG_LOC_BLEN: c_int = 6;
pub const CIPSO_V4_CACHE_BUCKETBITS: c_int = 7;
pub const CIPSO_V4_CACHE_BUCKETS: c_int = 1 << CIPSO_V4_CACHE_BUCKETBITS;
pub const CIPSO_V4_CACHE_REORDERLIMIT: c_int = 10;
pub const CIPSO_V4_CACHE_ENABLED_DEFAULT: c_int = 1;
pub const CIPSO_V4_CACHE_BUCKETS_SIZE_DEFAULT: c_int = 10;

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const ENOENT: c_int = -2;

type size_t = usize;

#[repr(C)]
pub struct cipso_v4_map_cache_bkt {
    lock: *mut c_void,
    size: c_uint,
    list: *mut c_void,
}

#[repr(C)]
pub struct cipso_v4_map_cache_entry {
    hash: u32,
    key: *mut u8,
    key_len: size_t,
    lsm_data: *mut c_void,
    activity: u32,
    list: *mut c_void,
}

#[repr(C)]
pub struct netlbl_lsm_secattr {
    cache: *mut c_void,
    flags: c_uint,
    type_: c_uint,
}

static CIPSO_V4_CACHE: SyncWrapper<*mut cipso_v4_map_cache_bkt> = SyncWrapper::new(ptr::null_mut());
static CIPSO_V4_CACHE_ENABLED: SyncWrapper<c_int> = SyncWrapper::new(CIPSO_V4_CACHE_ENABLED_DEFAULT);
static CIPSO_V4_CACHE_BUCKETSIZE: SyncWrapper<c_int> = SyncWrapper::new(CIPSO_V4_CACHE_BUCKETS_SIZE_DEFAULT);

unsafe extern "C" {
    fn netlbl_secattr_cache_free(cache: *mut c_void);
    fn kfree(ptr: *mut c_void);
    fn kmalloc(size: size_t, flags: c_int) -> *mut c_void;
    fn spin_lock_init(lock: *mut c_void);
    fn spin_lock_bh(lock: *mut c_void);
    fn spin_unlock_bh(lock: *mut c_void);
    fn INIT_LIST_HEAD(head: *mut c_void);
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {
        core::hint::spin_loop();
    }
}

#[unsafe(no_mangle)]
#[cfg(not(test))]
pub unsafe extern "C" fn rust_eh_personality() {}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn cipso_v4_cache_entry_free(entry: *mut cipso_v4_map_cache_entry) {
    if entry.is_null() {
        return;
    }

    if !(*entry).lsm_data.is_null() {
        netlbl_secattr_cache_free((*entry).lsm_data);
    }

    if !(*entry).key.is_null() {
        kfree((*entry).key as *mut c_void);
    }

    kfree(entry as *mut c_void);
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn cipso_v4_map_cache_hash(key: *const u8, key_len: c_uint) -> u32 {
    let mut hash: u32 = 0;
    let mut i: c_uint = 0;

    while i < key_len {
        let byte = *key.add(i as usize) as u32;
        hash = hash.wrapping_add(byte);
        hash = hash.wrapping_add(hash << 10);
        hash ^= hash >> 6;
        i += 1;
    }

    hash = hash.wrapping_add(hash << 3);
    hash ^= hash >> 11;
    hash = hash.wrapping_add(hash << 15);

    hash
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn cipso_v4_cache_init() -> c_int {
    let buckets = CIPSO_V4_CACHE_BUCKETS as usize;
    let size = buckets * core::mem::size_of::<cipso_v4_map_cache_bkt>();

    let cache_ptr = kmalloc(size as size_t, 0);
    if cache_ptr.is_null() {
        return ENOMEM;
    }

    let cache = cache_ptr as *mut cipso_v4_map_cache_bkt;
    for i in 0..buckets {
        let bucket = &mut *cache.add(i);
        spin_lock_init(&mut bucket.lock as *mut _ as *mut c_void);
        bucket.size = 0;
        INIT_LIST_HEAD(&mut bucket.list as *mut _ as *mut c_void);
    }

    *CIPSO_V4_CACHE.get_mut() = cache;
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn cipso_v4_cache_invalidate() {
    if (*CIPSO_V4_CACHE.get_mut()).is_null() {
        return;
    }

    let buckets = CIPSO_V4_CACHE_BUCKETS as usize;
    let cache = *CIPSO_V4_CACHE.get_mut();

    for i in 0..buckets {
        let bucket = &mut *cache.add(i);
        spin_lock_bh(&mut bucket.lock as *mut _ as *mut c_void);

        bucket.size = 0;
        INIT_LIST_HEAD(&mut bucket.list as *mut _ as *mut c_void);

        spin_unlock_bh(&mut bucket.lock as *mut _ as *mut c_void);
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn cipso_v4_cache_free() {
    if !(*CIPSO_V4_CACHE.get_mut()).is_null() {
        kfree(*CIPSO_V4_CACHE.get_mut() as *mut c_void);
        *CIPSO_V4_CACHE.get_mut() = ptr::null_mut();
    }
}

/// Add an entry to the CIPSO cache
///
/// # Safety
/// - `cipso_ptr` must be a valid pointer to a CIPSO option
/// - `secattr` must be a valid pointer to a netlbl_lsm_secattr
#[no_mangle]
pub unsafe extern "C" fn cipso_v4_cache_add(
    cipso_ptr: *const u8,
    secattr: *const netlbl_lsm_secattr,
) -> c_int {
    if (*CIPSO_V4_CACHE.get_mut()).is_null() || cipso_ptr.is_null() || secattr.is_null() {
        return 0;
    }

    if *CIPSO_V4_CACHE_ENABLED.get_mut() == 0 || *CIPSO_V4_CACHE_BUCKETSIZE.get_mut() <= 0 {
        return 0;
    }

    let cipso_ptr_len = *cipso_ptr.add(1) as c_uint;
    if cipso_ptr_len < CIPSO_V4_HDR_LEN as c_uint {
        return EINVAL;
    }

    // Allocate new entry
    extern "C" {
        fn kmalloc(size: size_t, flags: c_int) -> *mut c_void;
    }
    let entry_ptr = kmalloc(
        core::mem::size_of::<cipso_v4_map_cache_entry>() as size_t,
        0,
    );
    if entry_ptr.is_null() {
        return ENOMEM;
    }

    let entry = entry_ptr as *mut cipso_v4_map_cache_entry;
    (*entry).key = kmalloc(cipso_ptr_len as size_t, 0) as *mut u8;
    if (*entry).key.is_null() {
        extern "C" {
            fn kfree(ptr: *mut c_void);
        }
        kfree(entry as *mut c_void);
        return ENOMEM;
    }

    // Copy key
    for i in 0..cipso_ptr_len {
        // SAFETY: cipso_ptr and (*entry).key are valid for cipso_ptr_len bytes
        *(*entry).key.add(i as usize) = *cipso_ptr.add(i as usize);
    }

    (*entry).key_len = cipso_ptr_len as size_t;
    (*entry).hash = cipso_v4_map_cache_hash(cipso_ptr, cipso_ptr_len);
    (*entry).lsm_data = (*secattr).cache;
    (*entry).activity = 0;

    let bkt = (*entry).hash & (CIPSO_V4_CACHE_BUCKETS - 1) as u32;
    let cache = *CIPSO_V4_CACHE.get_mut() as *mut cipso_v4_map_cache_bkt;
    let bucket = &mut *cache.add(bkt as usize);

    // Acquire spinlock
    extern "C" {
        fn spin_lock_bh(lock: *mut c_void);
    }
    spin_lock_bh(&mut bucket.lock as *mut _ as *mut c_void);

    if bucket.size < *CIPSO_V4_CACHE_BUCKETSIZE.get_mut() as c_uint {
        // Add to head
        extern "C" {
            fn list_add(new_entry: *mut c_void, head: *mut c_void);
        }
        list_add(entry as *mut c_void, bucket.list);
        bucket.size += 1;
    } else {
        // Remove last entry
        let old_entry = {
            // SAFETY: (*bucket).list is valid
            let list = bucket.list;
            let entry = list as *mut cipso_v4_map_cache_entry;
            (*entry).list
        };

        // Remove old entry
        extern "C" {
            fn list_del(entry: *mut c_void);
        }
        list_del(old_entry);

        // Add new entry
        extern "C" {
            fn list_add(new_entry: *mut c_void, head: *mut c_void);
        }
        list_add(entry as *mut c_void, bucket.list);
    }

    // Release spinlock
    extern "C" {
        fn spin_unlock_bh(lock: *mut c_void);
    }
    spin_unlock_bh(&mut bucket.lock as *mut _ as *mut c_void);

    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn cipso_v4_cache_get_enabled() -> c_int {
    *CIPSO_V4_CACHE_ENABLED.get_mut()
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn cipso_v4_cache_set_bucketsize(size: c_int) {
    *CIPSO_V4_CACHE_BUCKETSIZE.get_mut() = size;
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn cipso_v4_cache_get_bucketsize() -> c_int {
    *CIPSO_V4_CACHE_BUCKETSIZE.get_mut()
}
