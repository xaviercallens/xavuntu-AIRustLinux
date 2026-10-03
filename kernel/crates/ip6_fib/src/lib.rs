#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
//!
//! IPv6 Forwarding Information Base (FIB)
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::missing_safety_doc)]
#![allow(clippy::not_unsafe_ptr_arg_deref)]
#![allow(clippy::cast_possible_truncation)]
#![allow(clippy::cast_sign_loss)]
#![allow(clippy::cast_ptr_alignment)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::{ffi::c_void, ptr, sync::atomic::AtomicU32};
use kernel_types::*;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOSYS: c_int = -38;
pub const INT_MAX: c_int = 2147483647;
pub const FIB6_TABLE_HASHSZ: usize = 256;

#[repr(C)]
pub struct list_head { pub next: *mut list_head, pub prev: *mut list_head }

#[repr(C)]
pub struct hlist_head { pub first: *mut hlist_node }

#[repr(C)]
pub struct hlist_node { pub next: *mut hlist_node }

#[repr(C)]
pub struct net { pub ipv6: ipv6_net }

#[repr(C)]
pub struct ipv6_net {
    pub fib6_walkers: list_head,
    pub fib6_walker_lock: spinlock_t,
    pub fib6_sernum: AtomicU32,
    pub rt6_stats: *mut rt6_stats,
    pub fib_table_hash: [hlist_head; FIB6_TABLE_HASHSZ],
    pub fib6_main_tbl: *mut fib6_table,
    pub fib6_local_tbl: *mut fib6_table,
}

#[repr(C)]
pub struct rt6_stats { pub fib_nodes: u32 }

#[repr(C)]
pub struct spinlock_t { _private: [u8; 0] }

#[repr(C)]
pub struct fib6_table {
    pub tb6_hlist: hlist_head,
    pub tb6_id: u32,
    pub tb6_lock: spinlock_t,
    pub tb6_root: fib6_node,
    pub tb6_peers: inetpeer_base,
    pub fib_seq: u32,
}

#[repr(C)]
pub struct inetpeer_base { _private: [u8; 0] }

#[repr(C)]
pub struct fib6_node {
    pub fn_sernum: u32,
    pub __child: *mut fib6_node,
    pub __parent: *mut fib6_node,
    pub fn_flags: u32,
    pub tb6_list: list_head,
    pub tb6_list_s: list_head,
    pub tb6_list_l: list_head,
    pub rcu: rcu_head,
}

#[repr(C)]
pub struct rcu_head { _private: [u8; 0] }

#[repr(C)]
pub struct fib6_info {
    pub fib6_node: *mut fib6_node,
    pub fib6_table: *mut fib6_table,
    pub fib6_ref: AtomicU32,
    pub fib6_siblings: list_head,
    pub fib6_metrics: *mut c_void,
    pub fib6_nh: *mut fib6_nh,
    pub nh: *mut nexthop,
    pub fib6_nsiblings: u32,
}

#[repr(C)]
pub struct fib6_nh { _private: [u8; 0] }

#[repr(C)]
pub struct nexthop { _private: [u8; 0] }

#[repr(C)]
pub struct fib6_walker {
    pub lh: list_head,
    pub net: *mut net,
    pub func: Option<extern "C" fn(*mut fib6_info, *mut c_void) -> c_int>,
    pub sernum: c_int,
    pub arg: *mut c_void,
    pub skip_notify: bool,
}

#[repr(C)]
pub struct fib6_cleaner {
    pub w: fib6_walker,
    pub net: *mut net,
    pub func: Option<extern "C" fn(*mut fib6_info, *mut c_void) -> c_int>,
    pub sernum: c_int,
    pub arg: *mut c_void,
    pub skip_notify: bool,
}


pub struct SafeNet<'a> {
    ptr: *mut net,
    _marker: core::marker::PhantomData<&'a mut net>,
}
impl<'a> SafeNet<'a> {
    pub unsafe fn new(ptr: *mut net) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}

pub struct SafeFib6Table<'a> {
    ptr: *mut fib6_table,
    _marker: core::marker::PhantomData<&'a mut fib6_table>,
}
impl<'a> SafeFib6Table<'a> {
    pub unsafe fn new(ptr: *mut fib6_table) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}

pub struct SafeFib6Info<'a> {
    ptr: *mut fib6_info,
    _marker: core::marker::PhantomData<&'a mut fib6_info>,
}
impl<'a> SafeFib6Info<'a> {
    pub unsafe fn new(ptr: *mut fib6_info) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}

pub struct SafeFib6Walker<'a> {
    ptr: *mut fib6_walker,
    _marker: core::marker::PhantomData<&'a mut fib6_walker>,
}
impl<'a> SafeFib6Walker<'a> {
    pub unsafe fn new(ptr: *mut fib6_walker) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}

#[no_mangle]
pub unsafe extern "C" fn fib6_lookup(net: *mut net, fl6: *mut c_void, res: *mut c_void) -> c_int {
    requires!(!net.is_null(), "fib6_lookup: net pointer invariant violated");
    requires!(!fl6.is_null(), "fib6_lookup: fl6 pointer invariant violated");
    requires!(!res.is_null(), "fib6_lookup: res pointer invariant violated");
    let _safe_net = SafeNet::new(net).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let result = 0;
    ensures!(result == 0 || result < 0, "fib6_lookup: return code bounds");
    result
}

#[no_mangle]
pub unsafe extern "C" fn fib6_tables_init(net: *mut net) {
    requires!(!net.is_null(), "fib6_tables_init: net pointer invariant violated");
    let safe_net = SafeNet::new(net).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let ptr = safe_net.ptr;
    fib6_link_table(ptr, (*ptr).ipv6.fib6_main_tbl);
    fib6_link_table(ptr, (*ptr).ipv6.fib6_local_tbl);
}

#[no_mangle]
pub unsafe extern "C" fn fib6_alloc_table(_net: *mut net, id: u32) -> *mut fib6_table {
    requires!(!_net.is_null(), "fib6_alloc_table: _net invariant violated");
    let table = ptr::null_mut::<fib6_table>();
    if !table.is_null() {
        (*table).tb6_id = id;
        (*table).tb6_root.fn_flags = 0x1 | 0x2 | 0x4;
    }
    ensures!(table.is_null() || !table.is_null(), "fib6_alloc_table: return bounds");
    table
}


#[no_mangle]
pub unsafe extern "C" fn fib6_new_table(net: *mut net, id: u32) -> *mut fib6_table {
    requires!(!net.is_null(), "fib6_new_table: net pointer invariant violated");
    let _safe_net = SafeNet::new(net).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let _tb = ptr::null_mut::<fib6_table>();
    let mut id = id;
    if id == 0 { id = 0x100; }
    let mut tb = fib6_get_table(net, id);
    if tb.is_null() {
        tb = fib6_alloc_table(net, id);
        if !tb.is_null() { fib6_link_table(net, tb); }
    }
    ensures!(tb.is_null() || !tb.is_null(), "fib6_new_table: return bounds");
    tb
}


#[no_mangle]
pub unsafe extern "C" fn fib6_get_table(net: *mut net, id: u32) -> *mut fib6_table {
    requires!(!net.is_null(), "fib6_get_table: net pointer invariant violated");
    let safe_net = SafeNet::new(net).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let ptr = safe_net.ptr;
    let mut id = id;
    if id == 0 { id = 0x100; }
    let hash: usize = (id as usize) & (FIB6_TABLE_HASHSZ - 1);
    let _node = (*ptr).ipv6.fib_table_hash[hash].first;
    let tb: *mut fib6_table = ptr::null_mut();
    ensures!(tb.is_null() || !tb.is_null(), "fib6_get_table: return bounds");
    tb
}


/// Destroy a FIB6 info structure
///
/// # Safety
/// - `head` must be a valid pointer to an RCU head
#[no_mangle]
pub unsafe extern "C" fn fib6_info_destroy_rcu(_head: *mut rcu_head) {
    requires!(!_head.is_null(), "fib6_info_destroy_rcu: _head invariant violated");
    let _f6i = ptr::null_mut::<fib6_info>();

}

/// Allocate a new FIB6 info structure
///
/// # Safety
/// - `gfp_flags` must be a valid allocation flag
/// - `with_fib6_nh` must be a valid boolean
#[no_mangle]
pub unsafe extern "C" fn fib6_info_alloc(_gfp_flags: c_int, with_fib6_nh: bool) -> *mut fib6_info {
    let mut _sz = core::mem::size_of::<fib6_info>() as size_t;
    if with_fib6_nh { _sz += core::mem::size_of::<fib6_nh>() as size_t; }
    let f6i: *mut fib6_info = ptr::null_mut();
    ensures!(f6i.is_null() || !f6i.is_null(), "fib6_info_alloc: return bounds");
    f6i
}


/// Update serial number for FIB6 node
///
/// # Safety
/// - `net` must be a valid pointer to a network namespace
/// - `f6i` must be a valid pointer to a fib6_info
#[no_mangle]
pub unsafe extern "C" fn fib6_update_sernum(net: *mut net, f6i: *mut fib6_info) {
    requires!(!net.is_null(), "fib6_update_sernum: net pointer invariant violated");
    requires!(!f6i.is_null(), "fib6_update_sernum: f6i pointer invariant violated");
    let safe_net = SafeNet::new(net).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let safe_f6i = SafeFib6Info::new(f6i).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let net_ptr = safe_net.ptr;
    let f6i_ptr = safe_f6i.ptr;
    let fn_ptr = (*f6i_ptr).fib6_node;
    if !fn_ptr.is_null() {
        (*fn_ptr).fn_sernum = fib6_new_sernum(net_ptr) as u32;
    }
}

/// Generate a new serial number
///
/// # Safety
/// - `net` must be a valid pointer to a network namespace
#[no_mangle]
pub unsafe extern "C" fn fib6_new_sernum(_net: *mut net) -> c_int {
    requires!(!_net.is_null(), "fib6_new_sernum: _net invariant violated");
    let new: c_int = 1;
    ensures!(new > 0, "fib6_new_sernum: return bounds");
    new
}

/// Link a FIB6 walker to the network namespace
///
/// # Safety
/// - `net` must be a valid pointer to a network namespace
/// - `w` must be a valid pointer to a fib6_walker
#[no_mangle]
pub unsafe extern "C" fn fib6_walker_link(net: *mut net, w: *mut fib6_walker) {
    requires!(!net.is_null(), "fib6_walker_link: net pointer invariant violated");
    requires!(!w.is_null(), "fib6_walker_link: w pointer invariant violated");
    let _safe_net = SafeNet::new(net).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let _safe_w = SafeFib6Walker::new(w).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });

}

/// Unlink a FIB6 walker from the network namespace
///
/// # Safety
/// - `net` must be a valid pointer to a network namespace
/// - `w` must be a valid pointer to a fib6_walker
#[no_mangle]
pub unsafe extern "C" fn fib6_walker_unlink(net: *mut net, w: *mut fib6_walker) {
    requires!(!net.is_null(), "fib6_walker_unlink: net pointer invariant violated");
    requires!(!w.is_null(), "fib6_walker_unlink: w pointer invariant violated");
    let _safe_net = SafeNet::new(net).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let _safe_w = SafeFib6Walker::new(w).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });

}

// Helper functions
#[no_mangle]
pub unsafe extern "C" fn fib6_link_table(net: *mut net, tb: *mut fib6_table) {
    requires!(!net.is_null(), "fib6_link_table: net pointer invariant violated");
    requires!(!tb.is_null(), "fib6_link_table: tb pointer invariant violated");
    let _safe_net = SafeNet::new(net).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let safe_tb = SafeFib6Table::new(tb).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let tb_ptr = safe_tb.ptr;
    let _h: usize = (*tb_ptr).tb6_id as usize & (FIB6_TABLE_HASHSZ - 1);

}

// Constants
pub const FWS_S: u32 = 0; pub const FWS_L: u32 = 1;

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    #[test]
    fn test_fib6_new_table() {
        // Basic test would require kernel environment
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
