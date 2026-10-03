#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]

use core::{ptr, ffi::c_int};

pub const RT_TABLE_MAIN: u32 = 254;
pub const RT_TABLE_LOCAL: u32 = 253;
pub const RT_TABLE_DEFAULT: u32 = 252;
pub const FIB_TABLE_HASHSZ: u32 = 255;

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12;

#[repr(C)]
pub struct fib_info { _priv: [u8; 0] }

#[repr(C)]
pub struct net_device { _priv: [u8; 0] }

#[repr(C)]
pub struct hlist_node { pub next: *mut hlist_node }

#[repr(C)]
pub struct hlist_head { pub first: *mut hlist_node }

#[repr(C)]
pub struct fib_table { pub tb_id: u32, pub tb_hlist: hlist_node }

#[repr(C)]
pub struct ipv4_net {
    pub fib_table_hash: [hlist_head; FIB_TABLE_HASHSZ as usize],
    pub fib_main: *mut fib_table,
    pub fib_default: *mut fib_table,
    pub fib_has_custom_rules: u8,
}

#[repr(C)]
pub struct net { pub ipv4: ipv4_net }

#[repr(C)]
pub struct fib_result { pub type_: u8, pub fi: *mut fib_info }

unsafe fn hlist_add_head_rcu(n: *mut hlist_node, h: *mut hlist_head) {
    unsafe {
        (*n).next = (*h).first;
        (*h).first = n;
    }
}

unsafe extern "C" {
    fn fib_trie_table(id: u32, alias: *mut fib_table) -> *mut fib_table;
    fn fib_trie_unmerge(old: *mut fib_table) -> *mut fib_table;
    fn fib_replace_table(net: *mut net, old: *mut fib_table, new: *mut fib_table);
    fn fib_free_table(tb: *mut fib_table);
    fn fib_table_flush_external(tb: *mut fib_table);
    fn fib_table_flush(net: *mut net, tb: *mut fib_table, flush_all: u8) -> c_int;
    fn rt_cache_flush(net: *mut net);
    fn __inet_dev_addr_type(net: *mut net, dev: *mut net_device, addr: u32, tb_id: u32) -> u32;
    fn l3mdev_fib_table(dev: *mut net_device) -> u32;
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rust_eh_personality() {}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn fib_new_table(net: *mut net, id: u32) -> *mut fib_table {
    if net.is_null() {
        return ptr::null_mut();
    }

    let mut alias: *mut fib_table = ptr::null_mut();
    let mut id_local = id;
    if id_local == 0 {
        id_local = RT_TABLE_MAIN;
    }

    let existing = unsafe { fib_get_table(net, id_local) };
    if !existing.is_null() {
        return existing;
    }

    if id_local == RT_TABLE_LOCAL && unsafe { (*net).ipv4.fib_has_custom_rules } == 0 {
        alias = unsafe { fib_new_table(net, RT_TABLE_MAIN) };
    }

    let tb = unsafe { fib_trie_table(id_local, alias) };
    if tb.is_null() {
        return ptr::null_mut();
    }

    unsafe {
        match id_local {
            RT_TABLE_MAIN => (*net).ipv4.fib_main = tb,
            RT_TABLE_DEFAULT => (*net).ipv4.fib_default = tb,
            _ => {}
        }

        let h = id_local & (FIB_TABLE_HASHSZ - 1);
        hlist_add_head_rcu(
            &mut (*tb).tb_hlist as *mut hlist_node,
            &mut (*net).ipv4.fib_table_hash[h as usize] as *mut hlist_head,
        );
    }

    tb
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn fib_get_table(net: *mut net, id: u32) -> *mut fib_table {
    if net.is_null() {
        return ptr::null_mut();
    }

    let mut id_local = id;
    if id_local == 0 {
        id_local = RT_TABLE_MAIN;
    }

    let h = id_local & (FIB_TABLE_HASHSZ - 1);
    let head = unsafe { &mut (*net).ipv4.fib_table_hash[h as usize] };

    let mut node = head.first;
    while !node.is_null() {
        let tb = node as *mut fib_table;
        if unsafe { (*tb).tb_id } == id_local {
            return tb;
        }
        node = unsafe { (*node).next };
    }

    ptr::null_mut()
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn fib_unmerge(net: *mut net) -> c_int {
    if net.is_null() {
        return EINVAL;
    }

    let old = unsafe { fib_get_table(net, RT_TABLE_LOCAL) };
    if old.is_null() {
        return 0;
    }

    let new = unsafe { fib_trie_unmerge(old) };
    if new.is_null() {
        return ENOMEM;
    }

    if new == old {
        return 0;
    }

    unsafe {
        fib_replace_table(net, old, new);
        fib_free_table(old);

        let main_table = fib_get_table(net, RT_TABLE_MAIN);
        if !main_table.is_null() {
            fib_table_flush_external(main_table);
        }
    }

    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn fib_flush(net: *mut net) -> c_int {
    if net.is_null() {
        return EINVAL;
    }

    let mut flushed: c_int = 0;
    for h in 0..FIB_TABLE_HASHSZ {
        let head = unsafe { &mut (*net).ipv4.fib_table_hash[h as usize] };
        let mut node = head.first;

        while !node.is_null() {
            let next = unsafe { (*node).next };
            let tb = node as *mut fib_table;
            flushed += unsafe { fib_table_flush(net, tb, 0) };
            node = next;
        }
    }

    if flushed > 0 {
        unsafe { rt_cache_flush(net) };
    }

    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn inet_addr_type(
    net: *mut net,
    dev: *mut net_device,
    addr: u32,
) -> u32 {
    if net.is_null() {
        return 0;
    }

    let tb_id = if dev.is_null() {
        RT_TABLE_LOCAL
    } else {
        let id = unsafe { l3mdev_fib_table(dev) };
        if id == 0 { RT_TABLE_LOCAL } else { id }
    };

    unsafe { __inet_dev_addr_type(net, dev, addr, tb_id) }
}
