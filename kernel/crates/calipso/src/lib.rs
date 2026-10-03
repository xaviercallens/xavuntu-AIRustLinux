#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

use core::ptr;
use core::sync::atomic::{AtomicPtr, Ordering};
use kernel_types::*;
use core::ffi::c_void;

// C-compatible aliases
type size_t = usize;
type c_size_t = usize;
type socklen_t = u32;

// Constants from C
pub const CALIPSO_OPT_LEN_MAX: c_int = 2 + 252;
pub const CALIPSO_HDR_LEN: c_int = 2 + 8;
pub const CALIPSO_OPT_LEN_MAX_WITH_PAD: c_int = 3 + CALIPSO_OPT_LEN_MAX + 7;
pub const CALIPSO_MAX_BUFFER: c_int = 6 + CALIPSO_OPT_LEN_MAX;
pub const CALIPSO_CACHE_BUCKETBITS: c_int = 7;
pub const CALIPSO_CACHE_BUCKETS: c_int = 1 << CALIPSO_CACHE_BUCKETBITS;
pub const CALIPSO_CACHE_REORDERLIMIT: c_int = 10;

// Error codes (kernel-style negative errno)
pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const ENOENT: c_int = -2;

#[repr(C)]
pub struct list_head { pub next: *mut list_head, pub prev: *mut list_head }

#[repr(C)]
pub struct spinlock_t { _priv: [u8; 0] }

#[repr(C)]
pub struct refcount_t { pub refs: c_int }

#[repr(C)]
pub struct netlbl_lsm_cache { pub refcount: refcount_t }

#[repr(C)]
pub struct calipso_map_cache_bkt {
    pub lock: spinlock_t,
    pub size: c_uint,
    pub list: list_head,
}

#[repr(C)]
pub struct calipso_map_cache_entry {
    pub hash: c_uint,
    pub key: *mut u8,
    pub key_len: size_t,
    pub lsm_data: *mut netlbl_lsm_cache,
    pub activity: c_uint,
    pub list: list_head,
}

#[repr(C)]
pub struct netlbl_lsm_secattr {
    pub cache: *mut c_void,
    pub flags: c_uint,
    pub type_: c_uint,
}

pub struct CacheKey { pub ptr: *const u8, pub len: usize }

pub struct CacheManager { pub buckets: *mut calipso_map_cache_bkt }

pub struct CacheStatistics { pub buckets: c_uint, pub entries: c_uint }

unsafe extern "C" {
    fn netlbl_secattr_cache_free(ptr: *mut netlbl_lsm_cache);
    fn jhash(key: *const u8, length: c_uint, initval: c_uint) -> c_uint;

    fn spin_lock_init(lock: *mut spinlock_t);
    fn spin_lock_bh(lock: *mut spinlock_t);
    fn spin_unlock_bh(lock: *mut spinlock_t);

    fn list_del(entry: *mut list_head);

    fn refcount_inc(r: *mut refcount_t);

    fn kcalloc(n: c_size_t, size: c_size_t, flags: c_uint) -> *mut c_void;
    fn kfree(ptr: *const c_void);
}

const GFP_KERNEL: c_uint = 0x10;

#[no_mangle]
pub static calipso_cache: AtomicPtr<calipso_map_cache_bkt> = AtomicPtr::new(ptr::null_mut());

#[no_mangle]
pub static calipso_cache_bucketsize: c_uint = CALIPSO_CACHE_BUCKETS as c_uint;

#[no_mangle]
pub unsafe extern "C" fn calipso_cache_enabled() -> c_int {
    (!calipso_cache.load(Ordering::Relaxed).is_null()) as c_int
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {
        core::hint::spin_loop();
    }
}

#[no_mangle]
pub unsafe extern "C" fn calipso_cache_entry_free(entry: *mut calipso_map_cache_entry) {
    if entry.is_null() {
        return;
    }
    if !(*entry).lsm_data.is_null() {
        netlbl_secattr_cache_free((*entry).lsm_data);
    }
    if !(*entry).key.is_null() {
        kfree((*entry).key as *const c_void);
    }
    kfree(entry as *const c_void);
}

#[no_mangle]
pub unsafe extern "C" fn calipso_map_cache_hash(key: *const u8, key_len: c_uint) -> c_uint {
    jhash(key, key_len, 0)
}

#[no_mangle]
pub unsafe extern "C" fn calipso_cache_init() -> c_int {
    let base = kcalloc(
        CALIPSO_CACHE_BUCKETS as c_size_t,
        core::mem::size_of::<calipso_map_cache_bkt>() as c_size_t,
        GFP_KERNEL,
    ) as *mut calipso_map_cache_bkt;

    if base.is_null() {
        return ENOMEM;
    }

    for i in 0..CALIPSO_CACHE_BUCKETS {
        let cache = base.add(i as usize);
        spin_lock_init(&mut (*cache).lock);
        (*cache).size = 0;
        (*cache).list.next = &mut (*cache).list;
        (*cache).list.prev = &mut (*cache).list;
    }

    calipso_cache.store(base, Ordering::Release);
    0
}
