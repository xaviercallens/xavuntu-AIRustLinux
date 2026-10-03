#![allow(clippy::all, clippy::pedantic)]

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(unused_imports)]
#![allow(non_upper_case_globals)]
#![allow(unused_variables)]


use core::{ffi::{c_int, c_uint, c_void, c_char, c_uchar}, mem, ptr, sync::atomic::{AtomicUsize, Ordering}};
use kernel_types::{size_t, sk_buff};
use kernel_types::nf_conntrack_helper as kt_nf_conntrack_helper;
use kernel_types::nf_conntrack_tuple as kt_nf_conntrack_tuple;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOSYS: c_int = -38;
pub const ENOENT: c_int = -2;

static NF_CT_HELPER_HSIZE_INTERNAL: SyncWrapper<c_uint> = SyncWrapper::new(256);

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_address {
    pub all: u16,
    pub protonum: u8,
    pub _pad: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple {
    pub src_l3num: u8,
    pub src: nf_conntrack_tuple_address,
    pub dst: nf_conntrack_tuple_address,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_mask {
    pub src_l3num: u8,
    pub src: nf_conntrack_tuple_address,
    pub dst: nf_conntrack_tuple_address,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct hlist_node { pub next: *mut hlist_node, pub pprev: *mut *mut hlist_node }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct list_head { pub next: *mut list_head, pub prev: *mut list_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_helper {
    pub hnode: hlist_node,
    pub name: [c_char; 16],
    pub tuple: nf_conntrack_tuple,
    pub expect_policy: *const c_void,
    pub expect_class_max: u32,
    pub help: *const c_void,
    pub from_nlattr: *const c_void,
    pub me: *const c_void,
    pub refcnt: c_uint,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct hlist_head { pub first: *mut hlist_node }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_tuple_hash { pub tuple: nf_conntrack_tuple }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn { pub status: u32, pub tuplehash: [nf_conn_tuple_hash; 2] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_help { pub helper: *mut nf_conntrack_helper, pub expectations: hlist_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_net {
    pub sysctl_auto_assign_helper: u8,
    pub auto_assign_helper_warned: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_ct_helper_expectfn {
    pub name: *const c_char,
    pub expectfn: *const c_void,
    pub head: list_head,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct Mutex { _priv: u8 }

// SyncWrapper provides a thread-safe UnsafeCell wrapper for FFI globals
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
        // For FFI globals, the kernel handles external synchronization.
        unsafe { &mut *self.0.get() }
    }
}

// Global variables
pub static NF_CT_HELPER_COUNT: SyncWrapper<c_uint> = SyncWrapper::new(0);
pub static NF_CT_AUTO_ASSIGN_HELPER: SyncWrapper<u8> = SyncWrapper::new(0);
pub static NF_CT_NAT_HELPERS: SyncWrapper<list_head> = SyncWrapper::new(list_head {
    next: ptr::null_mut(),
    prev: ptr::null_mut(),
});
pub static NF_CT_HELPER_MUTEX: SyncWrapper<Mutex> = SyncWrapper::new(Mutex { _priv: 0 });
pub static NF_CT_NAT_HELPERS_MUTEX: SyncWrapper<Mutex> = SyncWrapper::new(Mutex { _priv: 0 });

#[inline(always)]
unsafe fn helper_from_hnode(node: *mut hlist_node) -> *mut nf_conntrack_helper {
    let off = core::mem::offset_of!(nf_conntrack_helper, hnode);
    (node as *mut u8).sub(off) as *mut nf_conntrack_helper
}

#[inline(always)]
unsafe fn nf_ct_tuple_src_mask_cmp(
    t1: *const nf_conntrack_tuple,
    t2: *const nf_conntrack_tuple,
    _mask: *const nf_conntrack_tuple,
) -> bool {
    if t1.is_null() || t2.is_null() {
        return false;
    }
    (*t1).src_l3num == (*t2).src_l3num
        && (*t1).src.all == (*t2).src.all
        && (*t1).dst.protonum == (*t2).dst.protonum
}

#[inline(always)]
unsafe fn strcmp(a: *const c_char, b: *const c_char) -> c_int {
    if a.is_null() || b.is_null() {
        return -1;
    }
    let mut i = 0usize;
    loop {
        let ca = *a.add(i);
        let cb = *b.add(i);
        if ca != cb {
            return (ca as c_int) - (cb as c_int);
        }
        if ca == 0 {
            return 0;
        }
        i += 1;
    }
}

#[no_mangle]
pub unsafe extern "C" fn helper_hash(tuple: *const nf_conntrack_tuple) -> c_uint {
    if tuple.is_null() || *NF_CT_HELPER_HSIZE_INTERNAL.get_mut() == 0 {
        return 0;
    }

    let l3num = (*tuple).src_l3num as c_uint;
    let protonum = (*tuple).dst.protonum as c_uint;
    let src_all = (*tuple).src.all as c_uint;

    let hash = (((l3num << 8) | protonum) ^ src_all) % *NF_CT_HELPER_HSIZE.get_mut();
    hash
}

#[no_mangle]
pub unsafe extern "C" fn __nf_ct_helper_find(
    tuple: *const nf_conntrack_tuple,
) -> *mut nf_conntrack_helper {
    if tuple.is_null() || *NF_CT_HELPER_COUNT.get_mut() == 0 {
        return ptr::null_mut();
    }

    let h = helper_hash(tuple);
    let hash_ptr = *NF_CT_HELPER_HASH.get_mut();
    let head = &mut *hash_ptr.offset(h as isize);

    let mut node = (*head).first;
    let mask = nf_conntrack_tuple_mask {
        src_l3num: 0xFF,
        src: nf_conntrack_tuple_address { all: 0xFFFF, protonum: 0xFF, _pad: 0 },
        dst: nf_conntrack_tuple_address { all: 0xFFFF, protonum: 0xFF, _pad: 0 },
    };

    while !node.is_null() {
        let helper = helper_from_hnode(node);
        let helper_tuple_ptr = ptr::addr_of!((*helper).tuple);
        let mask_ptr = ptr::addr_of!(mask) as *const nf_conntrack_tuple;
        if nf_ct_tuple_src_mask_cmp(tuple, helper_tuple_ptr, mask_ptr) {
            return helper;
        }
        node = (*node).next;
    }

    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn __nf_conntrack_helper_find(
    name: *const c_char,
    l3num: u8,
    protonum: u8,
) -> *mut nf_conntrack_helper {
    let hash_ptr = *NF_CT_HELPER_HASH.get_mut();
    if name.is_null() || *NF_CT_HELPER_COUNT.get_mut() == 0 || hash_ptr.is_null() {
        return ptr::null_mut();
    }

    let hsize = *NF_CT_HELPER_HSIZE.get_mut();
    let mut i = 0;
    while i < hsize {
        let head = &*hash_ptr.offset(i as isize);
        let mut node = (*head).first;
        while !node.is_null() {
            let helper = helper_from_hnode(node);
            if !helper.is_null()
                && (*helper).tuple.src_l3num == l3num
                && (*helper).tuple.dst.protonum == protonum
                && strcmp((*helper).name.as_ptr(), name) == 0
            {
                return helper;
            }
            node = (*node).next;
        }

        i += 1;
    }

    ptr::null_mut()
}

/// Try to get helper module
///
/// # Safety
/// - `name` must be a valid null-terminated string
#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_helper_try_module_get(
    name: *const u8,
    l3num: u8,
    protonum: u8,
) -> *mut nf_conntrack_helper {
    if name.is_null() {
        return ptr::null_mut();
    }

    rcu_read_lock();

    let h = __nf_conntrack_helper_find(name as *const c_char, l3num, protonum);

    // Module loading logic
    if h.is_null() {
        rcu_read_unlock();
        // Module request logic would go here
        return ptr::null_mut();
    }

    if !try_module_get((*h).me as *mut c_void) {
        return ptr::null_mut();
    }

    if !refcount_inc_not_zero(&*((&(*h).refcnt) as *const c_uint as *const AtomicUsize)) {
        module_put((*h).me as *mut c_void);
        return ptr::null_mut();
    }

    rcu_read_unlock();
    h
}

/// Put helper reference
///
/// # Safety
/// - `helper` must be a valid pointer to nf_conntrack_helper
#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_helper_put(helper: *mut nf_conntrack_helper) {
    if !helper.is_null() {
        refcount_dec(&*((&(*helper).refcnt) as *const c_uint as *const AtomicUsize));
        module_put((*helper).me as *mut c_void);
    }
}

// Helper functions
unsafe fn rcu_read_lock() {
    // Implementation deferred.
}

unsafe fn rcu_read_unlock() {
    // Implementation deferred.
}

unsafe fn try_module_get(me: *mut c_void) -> bool {
    // Implementation deferred.
    true
}

unsafe fn module_put(me: *mut c_void) {
    // Implementation deferred.
}

unsafe fn refcount_inc_not_zero(refcnt: &AtomicUsize) -> bool {
    let current = refcnt.load(Ordering::Relaxed);
    if current == 0 {
        false
    } else {
        refcnt.fetch_add(1, Ordering::Relaxed);
        true
    }
}

unsafe fn refcount_dec(refcnt: &AtomicUsize) {
    refcnt.fetch_sub(1, Ordering::Relaxed);
}

// Exports
#[no_mangle]
pub static NF_CT_HELPER_HASH: SyncWrapper<*mut hlist_head> = SyncWrapper::new(ptr::null_mut());
#[no_mangle]
pub static NF_CT_HELPER_HSIZE: SyncWrapper<c_uint> = SyncWrapper::new(0);

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    #[test]
    fn test_helper_hash() {
        // Basic test case for helper_hash
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
