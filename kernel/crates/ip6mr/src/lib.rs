#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
//! IPv6 multicast routing support for Linux kernel
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(unexpected_cfgs)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs)]

use core::{ptr, ffi::{c_int, c_void}, mem::{self, size_of}};
use kernel_types::*;

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const ENOSYS: c_int = -38;
pub const FR_ACT_TO_TBL: u8 = 1;

pub type size_t = usize;
pub type c_size_t = usize;
pub type socklen_t = u32;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct list_head { pub next: *mut list_head, pub prev: *mut list_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct rhltable { _priv: [u8; 128] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib_rules_ops { _priv: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct rhashtable_compare_arg { pub key: *const c_void }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct rhashtable_params {
    pub head_offset: usize,
    pub key_offset: usize,
    pub key_len: usize,
    pub nelem_hint: usize,
    pub obj_cmpfn:
        Option<unsafe extern "C" fn(arg: *const rhashtable_compare_arg, ptr: *const c_void) -> c_int>,
    pub automatic_shrinking: bool,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct mfc6_cache_cmp_arg { pub mf6c_origin: in6_addr, pub mf6c_mcastgrp: in6_addr }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct mfc6_cache {
    pub mf6c_origin: in6_addr,
    pub mf6c_mcastgrp: in6_addr,
    pub cmparg: mfc6_cache_cmp_arg,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct mr_table_ops {
    pub rht_params: *const rhashtable_params,
    pub cmparg_any: *const mfc6_cache_cmp_arg,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct mr_table {
    pub list: list_head,
    pub id: u32,
    pub mfc_hash: rhltable,
    pub ipmr_expire_timer: timer_list,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_net {
    #[cfg(CONFIG_IPV6_MROUTE_MULTIPLE_TABLES)]
    pub mr6_tables: list_head,
    #[cfg(not(CONFIG_IPV6_MROUTE_MULTIPLE_TABLES))]
    pub mrt6: *mut mr_table,
    pub mr6_rules_ops: *mut fib_rules_ops,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net { pub ipv6: ipv6_net }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct flowi6 { pub daddr: in6_addr, pub saddr: in6_addr }

pub const MRT6_FLUSH_MIFS: u32 = 0x0001;
pub const MRT6_FLUSH_MIFS_STATIC: u32 = 0x0002;
pub const MRT6_FLUSH_MFC: u32 = 0x0004;
pub const MRT6_FLUSH_MFC_STATIC: u32 = 0x0008;

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

static MRT_CACHEP: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());

#[cfg(CONFIG_IPV6_MROUTE_MULTIPLE_TABLES)]
static IP6MR_CMPARG_ANY: SyncWrapper<mfc6_cache_cmp_arg> = SyncWrapper::new(mfc6_cache_cmp_arg {
    mf6c_origin: in6_addr {
        in6_u: in6_addr_union { u6_addr8: [0; 16] },
    },
    mf6c_mcastgrp: in6_addr {
        in6_u: in6_addr_union { u6_addr8: [0; 16] },
    },
});

static IP6MR_RHT_PARAMS: SyncWrapper<rhashtable_params> = SyncWrapper::new(rhashtable_params {
    head_offset: 0,
    key_offset: 0,
    key_len: size_of::<mfc6_cache_cmp_arg>(),
    nelem_hint: 3,
    obj_cmpfn: Some(ip6mr_hash_cmp),
    automatic_shrinking: true,
});

#[cfg(CONFIG_IPV6_MROUTE_MULTIPLE_TABLES)]
static IP6MR_TABLE_OPS: SyncWrapper<mr_table_ops> = SyncWrapper::new(mr_table_ops {
    rht_params: IP6MR_RHT_PARAMS.0.get(),
    cmparg_any: core::ptr::null(), // Needs runtime init if used this way, or we can use UnsafeCell::get
});

#[cfg(not(CONFIG_IPV6_MROUTE_MULTIPLE_TABLES))]
static IP6MR_TABLE_OPS: SyncWrapper<mr_table_ops> = SyncWrapper::new(mr_table_ops {
    rht_params: IP6MR_RHT_PARAMS.0.get(),
    cmparg_any: ptr::null(),
});

#[no_mangle]
pub unsafe extern "C" fn ipv6_addr_equal(a: *const in6_addr, b: *const in6_addr) -> bool {
    let aa = (*a).in6_u.u6_addr8;
    let bb = (*b).in6_u.u6_addr8;
    aa == bb
}

#[no_mangle]
pub unsafe extern "C" fn ip6mr_hash_cmp(
    arg: *const rhashtable_compare_arg,
    ptr_obj: *const c_void,
) -> c_int {
    let cmparg = (*arg).key as *const mfc6_cache_cmp_arg;
    let c = ptr_obj as *const mfc6_cache;

    if !ipv6_addr_equal(
        core::ptr::addr_of!((*c).mf6c_origin),
        core::ptr::addr_of!((*cmparg).mf6c_origin),
    ) || !ipv6_addr_equal(
        core::ptr::addr_of!((*c).mf6c_mcastgrp),
        core::ptr::addr_of!((*cmparg).mf6c_mcastgrp),
    ) {
        return 1;
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn ip6mr_new_table(netp: *mut net, id: u32) -> *mut mr_table {
    let existing = ip6mr_get_table(netp as *const net, id);
    if !existing.is_null() {
        return existing;
    }

    mr_table_alloc(
        netp as *const net,
        id,
        IP6MR_TABLE_OPS.0.get(),
        Some(ipmr_expire_process),
        Some(ip6mr_new_table_set),
    )
}

#[no_mangle]
pub unsafe extern "C" fn ip6mr_free_table(mrt: *mut mr_table) {
    if mrt.is_null() {
        return;
    }

    del_timer_sync(&mut (*mrt).ipmr_expire_timer);
    mroute_clean_tables(
        mrt,
        MRT6_FLUSH_MIFS | MRT6_FLUSH_MIFS_STATIC | MRT6_FLUSH_MFC | MRT6_FLUSH_MFC_STATIC,
    );
    rhltable_destroy(&mut (*mrt).mfc_hash);
    ptr::write_volatile(mrt, mem::zeroed());
    free(mrt as *mut c_void);
}

#[no_mangle]
pub unsafe extern "C" fn ip6mr_get_table(net: *const net, _id: u32) -> *mut mr_table {
    #[cfg(CONFIG_IPV6_MROUTE_MULTIPLE_TABLES)]
    {
        let mut mrt: *mut mr_table = ptr::null_mut();
        let mut pos = ptr::null_mut();

        loop {
            pos = ip6mr_mr_table_iter(net, mrt);
            if pos.is_null() {
                break;
            }

            if (*pos).id == id {
                return pos;
            }

            mrt = pos;
        }

        return ptr::null_mut();
    }

    #[cfg(not(CONFIG_IPV6_MROUTE_MULTIPLE_TABLES))]
    {
        (*net).ipv6.mrt6
    }
}

#[no_mangle]
pub unsafe extern "C" fn ip6mr_mr_table_iter(net: *mut net, mrt: *mut mr_table) -> *mut mr_table {
    #[cfg(CONFIG_IPV6_MROUTE_MULTIPLE_TABLES)]
    {
        if mrt.is_null() {
            return (*(*net).ipv6.mr6_tables).next as *mut mr_table;
        }
        return (*mrt).list.next as *mut mr_table;
    }

    #[cfg(not(CONFIG_IPV6_MROUTE_MULTIPLE_TABLES))]
    {
        if mrt.is_null() {
            return (*net).ipv6.mrt6;
        }
        ptr::null_mut()
    }
}

#[no_mangle]
pub unsafe extern "C" fn fib_rule_matchall(rule: *const fib_rule) -> bool {
    (*rule).flags & 0x1 != 0
}

#[no_mangle]
pub unsafe extern "C" fn ip6mr_rule_default(rule: *const fib_rule) -> bool {
    let rule = &*rule;
    fib_rule_matchall(rule)
        && rule.action == FR_ACT_TO_TBL
        && rule.table == RT6_TABLE_DFLT
        && rule.l3mdev.is_null()
}

// Implementation deferred.
#[no_mangle]
pub unsafe extern "C" fn mr_table_alloc(
    net: *const net,
    id: u32,
    _ops: *const mr_table_ops,
    _expire_process: Option<unsafe extern "C" fn(t: *mut timer_list)>,
    new_table_set: Option<unsafe extern "C" fn(mrt: *mut mr_table, net: *mut net)>,
) -> *mut mr_table {
    // Implementation deferred.
    let mrt = alloc(size_of::<mr_table>()) as *mut mr_table;
    if mrt.is_null() {
        return ptr::null_mut();
    }

    // Initialize fields
    (*mrt).id = id;
    // ... initialize other fields

    if let Some(set) = new_table_set {
        set(mrt, net as *mut net);
    }

    mrt
}

#[no_mangle]
pub unsafe extern "C" fn del_timer_sync(_timer: *mut timer_list) {
    // Implementation deferred.
}

#[no_mangle]
pub unsafe extern "C" fn mroute_clean_tables(_mrt: *mut mr_table, _flags: u32) {
    // Implementation deferred.
}

#[no_mangle]
pub unsafe extern "C" fn rhltable_destroy(_table: *mut rhltable) {
    // Implementation deferred.
}

#[no_mangle]
pub unsafe extern "C" fn alloc(size: usize) -> *mut c_void {
    // Implementation deferred.
    static IP6MR_BUF: SyncWrapper<[u8; 4096]> = SyncWrapper::new([0; 4096]);
    if size <= 4096 {
        IP6MR_BUF.get_mut().as_mut_ptr().cast()
    } else {
        core::ptr::null_mut()
    }
}

#[no_mangle]
pub unsafe extern "C" fn free(_ptr: *mut c_void) {
    // Implementation deferred.
}

// Constants
pub const RT6_TABLE_DFLT: u32 = 254;

// Implementation deferred.
#[cfg(CONFIG_IPV6_MROUTE_MULTIPLE_TABLES)]
const _: () = {};

// SAFETY: These functions are called from the kernel and must be marked unsafe
#[no_mangle]
pub unsafe extern "C" fn ipmr_expire_process(_t: *mut timer_list) {
    // Implementation would handle timer expiration
}

#[no_mangle]
pub unsafe extern "C" fn ip6mr_new_table_set(_mrt: *mut mr_table, _net: *mut net) {
    #[cfg(CONFIG_IPV6_MROUTE_MULTIPLE_TABLES)]
    {
        list_add_tail_rcu(&(*mrt).list, &(*net).ipv6.mr6_tables);
    }
}

#[no_mangle]
pub unsafe extern "C" fn list_add_tail_rcu(_new: *mut list_head, _head: *mut list_head) {
    // Implementation deferred.
}

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    #[test]
    fn test_ip6mr_new_table() {
        // Basic test would require kernel environment
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
