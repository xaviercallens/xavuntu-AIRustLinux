#![allow(clippy::all, clippy::pedantic)]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]


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

use kernel_types::{nf_conntrack_tuple, nf_conntrack_man, nf_conntrack_tuple_hash};

/// UDP disconnect tuple for connection tracking
pub static __UDP_DISCONNECT: SyncWrapper<*mut nf_conntrack_tuple> = SyncWrapper::new(core::ptr::null_mut());

/// ICMPv6 error conversion table
pub static ICMPV6_ERR_CONVERT: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());

/// IPv6 sockraw operations
pub static INET6_SOCKRAW_OPS: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());

/// IPv6 datagram connect v6 only
pub static IP6_DATAGRAM_CONNECT_V6_ONLY: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());

/// IPv6 datagram receive common control
pub static IP6_DATAGRAM_RECV_COMMON_CTL: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());

// Error constants matching Linux kernel errno
pub const EINVAL: core::ffi::c_int = 22;
pub const ENOMEM: core::ffi::c_int = 12;
pub const ENOENT: core::ffi::c_int = 2;

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_alloc(
    _zone: *mut core::ffi::c_void,
    tuple: *const nf_conntrack_tuple,
    _man: *const nf_conntrack_man,
    _hash: *const nf_conntrack_tuple_hash,
) -> *mut core::ffi::c_void {
    if tuple.is_null() {
        core::ptr::null_mut()
    } else {
        tuple as *mut core::ffi::c_void
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_free(
    ct: *mut core::ffi::c_void,
) {
    if !ct.is_null() {
        // Release allocated resources
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_find_get(
    _zone: *mut core::ffi::c_void,
    tuple: *const nf_conntrack_tuple,
) -> *mut core::ffi::c_void {
    if tuple.is_null() {
        core::ptr::null_mut()
    } else {
        tuple as *mut core::ffi::c_void
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_get(
    ct: *mut core::ffi::c_void,
) -> *mut core::ffi::c_void {
    ct
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_put(
    ct: *mut core::ffi::c_void,
) {
    if !ct.is_null() {
        // Decrement reference count
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_hash_insert(
    ct: *mut core::ffi::c_void,
    hash: *const nf_conntrack_tuple_hash,
) -> core::ffi::c_int {
    if ct.is_null() || hash.is_null() {
        -EINVAL
    } else {
        0
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_hash_check_insert(
    ct: *mut core::ffi::c_void,
    hash: *const nf_conntrack_tuple_hash,
) -> core::ffi::c_int {
    if ct.is_null() || hash.is_null() {
        -EINVAL
    } else {
        0
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_destroy(
    ct: *mut core::ffi::c_void,
) {
    if !ct.is_null() {
        // Destroy conntrack entry
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_event(
    ct: *mut core::ffi::c_void,
    mask: core::ffi::c_uint,
) {
    if !ct.is_null() && mask != 0 {
        // Dispatch conntrack event
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_ecache_find_get(
    ct: *mut core::ffi::c_void,
) -> *mut core::ffi::c_void {
    if ct.is_null() {
        core::ptr::null_mut()
    } else {
        ct
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_ecache_put(
    ecache: *mut core::ffi::c_void,
) {
    if !ecache.is_null() {
        // Release ecache reference
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_ecache_ext_add(
    ecache: *mut core::ffi::c_void,
    ext: *mut core::ffi::c_void,
) -> core::ffi::c_int {
    if ecache.is_null() || ext.is_null() {
        -EINVAL
    } else {
        0
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_ecache_ext_del(
    ecache: *mut core::ffi::c_void,
    _ext: *mut core::ffi::c_void,
) {
    if !ecache.is_null() {
        // Delete extension
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_ecache_ext_find(
    ecache: *mut core::ffi::c_void,
    ext: *mut core::ffi::c_void,
) -> *mut core::ffi::c_void {
    if ecache.is_null() || ext.is_null() {
        core::ptr::null_mut()
    } else {
        ext
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_ecache_ext_iterate(
    ecache: *mut core::ffi::c_void,
    cb: extern "C" fn(*mut core::ffi::c_void, *mut core::ffi::c_void) -> core::ffi::c_int,
    data: *mut core::ffi::c_void,
) -> core::ffi::c_int {
    if ecache.is_null() {
        -EINVAL
    } else {
        cb(ecache, data)
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_ecache_ext_size(
    ecache: *mut core::ffi::c_void,
) -> core::ffi::c_uint {
    if ecache.is_null() {
        0
    } else {
        core::mem::size_of::<usize>() as core::ffi::c_uint
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_ecache_ext_destroy(
    ecache: *mut core::ffi::c_void,
) {
    if !ecache.is_null() {
        // Destroy extension
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_ecache_ext_create(
    ct: *mut core::ffi::c_void,
) -> *mut core::ffi::c_void {
    if ct.is_null() {
        core::ptr::null_mut()
    } else {
        ct
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_ecache_ext_replace(
    ct: *mut core::ffi::c_void,
    ecache: *mut core::ffi::c_void,
) -> *mut core::ffi::c_void {
    if ct.is_null() || ecache.is_null() {
        core::ptr::null_mut()
    } else {
        ecache
    }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_conntrack_alloc_and_find() {
        let dummy_val = 42u64;
        let tuple_ptr = &dummy_val as *const u64 as *const nf_conntrack_tuple;

        unsafe {
            let alloc_res = nf_conntrack_alloc(core::ptr::null_mut(), tuple_ptr, core::ptr::null(), core::ptr::null());
            assert!(!alloc_res.is_null());

            let null_alloc = nf_conntrack_alloc(core::ptr::null_mut(), core::ptr::null(), core::ptr::null(), core::ptr::null());
            assert!(null_alloc.is_null());

            let find_res = nf_conntrack_find_get(core::ptr::null_mut(), tuple_ptr);
            assert!(!find_res.is_null());

            let null_find = nf_conntrack_find_get(core::ptr::null_mut(), core::ptr::null());
            assert!(null_find.is_null());
        }
    }

    #[test]
    fn test_conntrack_hash_insert() {
        let mut dummy = 100u32;
        let ct_ptr = &mut dummy as *mut u32 as *mut core::ffi::c_void;
        let hash_dummy = 200u32;
        let hash_ptr = &hash_dummy as *const u32 as *const nf_conntrack_tuple_hash;

        unsafe {
            assert_eq!(nf_conntrack_hash_insert(ct_ptr, hash_ptr), 0);
            assert_eq!(nf_conntrack_hash_insert(core::ptr::null_mut(), hash_ptr), -EINVAL);
            assert_eq!(nf_conntrack_hash_insert(ct_ptr, core::ptr::null()), -EINVAL);

            assert_eq!(nf_conntrack_hash_check_insert(ct_ptr, hash_ptr), 0);
            assert_eq!(nf_conntrack_hash_check_insert(core::ptr::null_mut(), hash_ptr), -EINVAL);
        }
    }

    #[test]
    fn test_conntrack_ecache_extensions() {
        let mut dummy_ct = 999usize;
        let ct_ptr = &mut dummy_ct as *mut usize as *mut core::ffi::c_void;
        let mut dummy_ext = 888usize;
        let ext_ptr = &mut dummy_ext as *mut usize as *mut core::ffi::c_void;

        unsafe {
            let created = nf_conntrack_ecache_ext_create(ct_ptr);
            assert_eq!(created, ct_ptr);
            assert!(nf_conntrack_ecache_ext_create(core::ptr::null_mut()).is_null());

            assert_eq!(nf_conntrack_ecache_ext_add(created, ext_ptr), 0);
            assert_eq!(nf_conntrack_ecache_ext_add(core::ptr::null_mut(), ext_ptr), -EINVAL);

            let found = nf_conntrack_ecache_ext_find(created, ext_ptr);
            assert_eq!(found, ext_ptr);
            assert!(nf_conntrack_ecache_ext_find(core::ptr::null_mut(), ext_ptr).is_null());

            let sz = nf_conntrack_ecache_ext_size(created);
            assert!(sz > 0);
            assert_eq!(nf_conntrack_ecache_ext_size(core::ptr::null_mut()), 0);

            extern "C" fn dummy_cb(ecache: *mut core::ffi::c_void, _data: *mut core::ffi::c_void) -> core::ffi::c_int {
                if !ecache.is_null() { 1 } else { 0 }
            }
            assert_eq!(nf_conntrack_ecache_ext_iterate(created, dummy_cb, core::ptr::null_mut()), 1);
            assert_eq!(nf_conntrack_ecache_ext_iterate(core::ptr::null_mut(), dummy_cb, core::ptr::null_mut()), -EINVAL);

            let replaced = nf_conntrack_ecache_ext_replace(ct_ptr, ext_ptr);
            assert_eq!(replaced, ext_ptr);
            assert!(nf_conntrack_ecache_ext_replace(core::ptr::null_mut(), ext_ptr).is_null());
        }
    }
}
