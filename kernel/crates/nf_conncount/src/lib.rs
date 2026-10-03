#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clashing_extern_declarations)]

use core::{{ptr, slice}, ffi::{c_int, c_uint, c_ulong, c_void}};

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

pub const CONNCOUNT_SLOTS: usize = 256;
pub const CONNCOUNT_GC_MAX_NODES: c_uint = 8;
pub const MAX_KEYLEN: usize = 5;
pub const IPPROTO_TCP: c_int = 6;
pub const TCP_CONNTRACK_TIME_WAIT: c_int = 12;
pub const TCP_CONNTRACK_CLOSE: c_int = 13;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const EAGAIN: c_int = -11;
pub const ENOENT: c_int = -2;
pub const EOVERFLOW: c_int = -75;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct list_head { pub next: *mut list_head, pub prev: *mut list_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct rb_node {
    pub rb_parent_color: c_ulong,
    pub rb_left: *mut rb_node,
    pub rb_right: *mut rb_node,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct rb_root { pub rb_node: *mut rb_node }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_hash { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conncount_tuple {
    pub node: list_head,
    pub tuple: nf_conntrack_tuple,
    pub zone: nf_conntrack_zone,
    pub cpu: c_int,
    pub jiffies32: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conncount_list {
    pub list_lock: *mut c_void,
    pub head: list_head,
    pub count: c_uint,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conncount_rb {
    pub node: rb_node,
    pub list: nf_conncount_list,
    pub key: [u32; MAX_KEYLEN],
    pub rcu_head: *mut c_void,
}

const BITS_PER_CULONG: usize = core::mem::size_of::<c_ulong>() * 8;
const PENDING_TREES_LEN: usize = CONNCOUNT_SLOTS.div_ceil(BITS_PER_CULONG);

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conncount_data {
    pub keylen: c_uint,
    pub root: [rb_root; CONNCOUNT_SLOTS],
    pub net: *mut c_void,
    pub gc_work: *mut c_void,
    pub pending_trees: [c_ulong; PENDING_TREES_LEN],
    pub gc_tree: c_uint,
}

unsafe extern "C" {
    fn nf_ct_protonum(conn: *const nf_conn) -> c_int;
    fn nf_ct_tcp_state(conn: *const nf_conn) -> c_int;
    fn nf_conntrack_find_get(
        net: *mut c_void,
        zone: *const nf_conntrack_zone,
        tuple: *const nf_conntrack_tuple,
    ) -> *const nf_conntrack_tuple_hash;
    fn nf_ct_tuple_equal(a: *const nf_conntrack_tuple, b: *const nf_conntrack_tuple) -> bool;
    fn nf_ct_zone_id(zone: *const nf_conntrack_zone, dir: c_int) -> c_int;
    fn nf_ct_zone_equal(a: *const nf_conn, zone: *const nf_conntrack_zone, dir: c_int) -> bool;
    fn nf_ct_tuplehash_to_ctrack(h: *const nf_conntrack_tuple_hash) -> *mut nf_conn;
    fn nf_ct_put(ct: *mut nf_conn);
    fn kmem_cache_alloc(cachep: *mut c_void, flags: c_uint) -> *mut c_void;
    fn kmem_cache_free(cachep: *mut c_void, objp: *mut c_void);
    fn jiffies() -> c_ulong;
    fn raw_smp_processor_id() -> c_int;
    fn spin_lock_bh(lock: *mut c_void);
    fn spin_unlock_bh(lock: *mut c_void);
    fn spin_lock_init(lock: *mut c_void);
    fn spin_trylock(lock: *mut c_void) -> c_int;
    fn spin_unlock(lock: *mut c_void);
    fn list_del(pos: *mut list_head);
    fn list_add_tail(pos: *mut list_head, head: *mut list_head);
    fn list_add(pos: *mut list_head, head: *mut list_head);
    fn call_rcu(head: *mut c_void, func: *mut c_void);
    fn schedule_work(work: *mut c_void);
    fn set_bit(nr: c_ulong, addr: *mut c_ulong);
}

// Removed - duplicates defined at lines 325-326

#[unsafe(no_mangle)]
pub unsafe extern "C" fn already_closed(conn: *const nf_conn) -> c_int {
    if nf_ct_protonum(conn) == IPPROTO_TCP {
        let state = nf_ct_tcp_state(conn);
        (state == TCP_CONNTRACK_TIME_WAIT || state == TCP_CONNTRACK_CLOSE) as c_int
    } else {
        0
    }
}

/// Compare two keys
///
/// # Safety
/// - `a` and `b` must be valid pointers to u32 arrays of length `klen`
#[no_mangle]
pub unsafe extern "C" fn key_diff(a: *const u32, b: *const u32, klen: c_uint) -> c_int {
    let a_slice = slice::from_raw_parts(a, klen as usize);
    let b_slice = slice::from_raw_parts(b, klen as usize);
    a_slice.cmp(b_slice) as c_int
}

/// Free a connection entry
///
/// # Safety
/// - `list` must be a valid pointer to nf_conncount_list with held lock
/// - `conn` must be a valid pointer to nf_conncount_tuple in list
#[no_mangle]
pub unsafe extern "C" fn conn_free(list: *mut nf_conncount_list, conn: *mut nf_conncount_tuple) {
    (*list).count = (*list).count.checked_sub(1).unwrap_or(0);
    list_del(&mut (*conn).node);
    kmem_cache_free(conncount_conn_cachep(), conn as *mut c_void);
}

/// Find or evict a connection entry
///
/// # Safety
/// - All pointer parameters must be valid
#[no_mangle]
pub unsafe extern "C" fn find_or_evict(
    net: *mut c_void,
    list: *mut nf_conncount_list,
    conn: *mut nf_conncount_tuple,
) -> *const nf_conntrack_tuple_hash {
    let found = nf_conntrack_find_get(net, &(*conn).zone, &(*conn).tuple);
    if !found.is_null() {
        return found;
    }

    let b = (*conn).jiffies32;
    let a = jiffies() as u32;
    let age = a.wrapping_sub(b);

    if (*conn).cpu == raw_smp_processor_id() || age >= 2 {
        conn_free(list, conn);
        return ptr::null();
    }

    ptr::null()
}

/// Add a connection to the count
///
/// # Safety
/// - All pointer parameters must be valid
#[no_mangle]
pub unsafe extern "C" fn __nf_conncount_add(
    net: *mut c_void,
    list: *mut nf_conncount_list,
    tuple: *const nf_conntrack_tuple,
    zone: *const nf_conntrack_zone,
) -> c_int {
    let mut collect = 0;
    let mut conn: *mut nf_conncount_tuple = ptr::null_mut();

    // Iterate through list entries
    while !conn.is_null() && collect < CONNCOUNT_GC_MAX_NODES {
        let found = find_or_evict(net, list, conn);
        if found.is_null() {
            if nf_ct_tuple_equal(&(*conn).tuple, tuple)
                && nf_ct_zone_id(&(*conn).zone, 0) == nf_ct_zone_id(zone, 0)
            {
                return 0;
            }
            collect += 1;
            continue;
        }

        let found_ct = nf_ct_tuplehash_to_ctrack(found);
        if nf_ct_tuple_equal(&(*conn).tuple, tuple) && nf_ct_zone_equal(found_ct, zone, 0) {
            nf_ct_put(found_ct);
            return 0;
        }

        if already_closed(found_ct) != 0 {
            nf_ct_put(found_ct);
            conn_free(list, conn);
            collect += 1;
            continue;
        }

        nf_ct_put(found_ct);
    }

    if (*list).count > core::u32::MAX as c_uint {
        return -EOVERFLOW;
    }

    conn = kmem_cache_alloc(conncount_conn_cachep(), 1) as *mut nf_conncount_tuple;
    if conn.is_null() {
        return -ENOMEM;
    }

    (*conn).tuple = *tuple;
    (*conn).zone = *zone;
    (*conn).cpu = raw_smp_processor_id();
    (*conn).jiffies32 = jiffies() as u32;
    list_add_tail(&mut (*conn).node, &mut (*list).head);
    (*list).count += 1;

    0
}

/// Add a connection to the count
///
/// # Safety
/// - All pointer parameters must be valid
#[no_mangle]
pub unsafe extern "C" fn nf_conncount_add(
    net: *mut c_void,
    list: *mut nf_conncount_list,
    tuple: *const nf_conntrack_tuple,
    zone: *const nf_conntrack_zone,
) -> c_int {
    spin_lock_bh((*list).list_lock);
    let ret = __nf_conncount_add(net, list, tuple, zone);
    spin_unlock_bh((*list).list_lock);
    ret
}

/// Initialize a connection count list
///
/// # Safety
/// - `list` must be a valid pointer to nf_conncount_list
#[no_mangle]
pub unsafe extern "C" fn nf_conncount_list_init(list: *mut nf_conncount_list) {
    spin_lock_init((*list).list_lock);
    (*list).head.next = &mut (*list).head as *mut _ as *mut list_head;
    (*list).head.prev = &mut (*list).head as *mut _ as *mut list_head;
    (*list).count = 0;
}

/// Garbage collect a connection count list
///
/// # Safety
/// - `net` must be a valid pointer to net
/// - `list` must be a valid pointer to nf_conncount_list
#[no_mangle]
pub unsafe extern "C" fn nf_conncount_gc_list(
    net: *mut c_void,
    list: *mut nf_conncount_list,
) -> c_int {
    let mut collected = 0;
    let conn: *mut nf_conncount_tuple = ptr::null_mut();

    if spin_trylock((*list).list_lock) == 0 {
        return 0;
    }

    while !conn.is_null() && collected < CONNCOUNT_GC_MAX_NODES {
        let found = find_or_evict(net, list, conn);
        if found.is_null() {
            collected += 1;
            continue;
        }

        let found_ct = nf_ct_tuplehash_to_ctrack(found);
        if already_closed(found_ct) != 0 {
            nf_ct_put(found_ct);
            conn_free(list, conn);
            collected += 1;
            continue;
        }

        nf_ct_put(found_ct);
    }

    let ret = (*list).count == 0;
    spin_unlock((*list).list_lock);
    ret as c_int
}

// Global variables
static CONNCOUNT_RND: SyncWrapper<u32> = SyncWrapper::new(0);
static CONNCOUNT_RB_CACHEP: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());
static CONNCOUNT_CONN_CACHEP: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());

// Helper functions for memory management
#[no_mangle]
pub unsafe extern "C" fn conncount_rb_cachep() -> *mut c_void {
    *CONNCOUNT_RB_CACHEP.get_mut()
}

#[no_mangle]
pub unsafe extern "C" fn conncount_conn_cachep() -> *mut c_void {
    *CONNCOUNT_CONN_CACHEP.get_mut()
}

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    #[test]
    fn basic_test() {
        // This would need actual test implementation
        // Implementation deferred.
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
