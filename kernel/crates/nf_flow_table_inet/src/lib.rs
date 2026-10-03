#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

use kernel_types::*;
use core::sync::atomic::{AtomicUsize, Ordering};
use core::panic::PanicInfo;

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}

// Error constants
pub const ENOSPC: c_int = -28; pub const ENOENT: c_int = -2;

/// Flow table entry for IPv4/IPv6
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_flow_table_inet_entry {
    pub key: nf_flow_table_inet_key,
    pub data: nf_flow_table_inet_data,
}

/// Flow table key for IPv4/IPv6
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_flow_table_inet_key {
    pub saddr: nf_inet_addr,
    pub daddr: nf_inet_addr,
    pub l4proto: u8,
    pub l3proto: u8,
    pub zone: u16,
}

/// Flow table data for IPv4/IPv6
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_flow_table_inet_data {
    pub bytes: u64,
    pub packets: u64,
    pub last_used: u64,
    pub timeout: u32,
}

/// Flow table for IPv4/IPv6
#[repr(C)]
pub struct nf_flow_table_inet {
    pub entries: *mut nf_flow_table_inet_entry,
    pub size: AtomicUsize,
    pub used: AtomicUsize,
    pub timeout: u32,
}

/// Initialize a flow table
#[no_mangle]
pub unsafe extern "C" fn nf_flow_table_inet_init(
    table: *mut nf_flow_table_inet,
    size: usize,
    timeout: u32,
) -> c_int {
    if table.is_null() || size == 0 {
        return -EINVAL;
    }

    let table = &mut *table;

    table.entries = core::ptr::null_mut();
    table.size.store(size, Ordering::Relaxed);
    table.used.store(0, Ordering::Relaxed);
    table.timeout = timeout;

    0
}

/// Add an entry to the flow table
#[no_mangle]
pub unsafe extern "C" fn nf_flow_table_inet_add(
    table: *mut nf_flow_table_inet,
    key: *const nf_flow_table_inet_key,
    data: *const nf_flow_table_inet_data,
) -> c_int {
    if table.is_null() || key.is_null() || data.is_null() {
        return -EINVAL;
    }

    let table = &mut *table;
    let key = &*key;
    let data = &*data;

    let used = table.used.load(Ordering::Relaxed);
    let size = table.size.load(Ordering::Relaxed);

    if used >= size {
        return -ENOSPC;
    }

    let entry = &mut *table.entries.add(used);
    entry.key = *key;
    entry.data = *data;

    table.used.store(used + 1, Ordering::Relaxed);

    0
}

/// Find an entry in the flow table
#[no_mangle]
pub unsafe extern "C" fn nf_flow_table_inet_find(
    table: *const nf_flow_table_inet,
    key: *const nf_flow_table_inet_key,
    data: *mut nf_flow_table_inet_data,
) -> c_int {
    if table.is_null() || key.is_null() || data.is_null() {
        return -EINVAL;
    }

    let table = &*table;
    let key = &*key;
    let data = &mut *data;

    let used = table.used.load(Ordering::Relaxed);

    for i in 0..used {
        let entry = &*table.entries.add(i);
        if entry.key.saddr.all == key.saddr.all
            && entry.key.daddr.all == key.daddr.all
            && entry.key.l4proto == key.l4proto
            && entry.key.l3proto == key.l3proto
            && entry.key.zone == key.zone
        {
            *data = entry.data;
            return 0;
        }
    }

    -ENOENT
}

/// Update an entry in the flow table
#[no_mangle]
pub unsafe extern "C" fn nf_flow_table_inet_update(
    table: *mut nf_flow_table_inet,
    key: *const nf_flow_table_inet_key,
    data: *const nf_flow_table_inet_data,
) -> c_int {
    if table.is_null() || key.is_null() || data.is_null() {
        return -EINVAL;
    }

    let table = &mut *table;
    let key = &*key;
    let data = &*data;

    let used = table.used.load(Ordering::Relaxed);

    for i in 0..used {
        let entry = &mut *table.entries.add(i);
        if entry.key.saddr.all == key.saddr.all
            && entry.key.daddr.all == key.daddr.all
            && entry.key.l4proto == key.l4proto
            && entry.key.l3proto == key.l3proto
            && entry.key.zone == key.zone
        {
            entry.data = *data;
            return 0;
        }
    }

    -ENOENT
}

/// Delete an entry from the flow table
#[no_mangle]
pub unsafe extern "C" fn nf_flow_table_inet_delete(
    table: *mut nf_flow_table_inet,
    key: *const nf_flow_table_inet_key,
) -> c_int {
    if table.is_null() || key.is_null() {
        return -EINVAL;
    }

    let table = &mut *table;
    let key = &*key;

    let used = table.used.load(Ordering::Relaxed);

    for i in 0..used {
        let entry = &mut *table.entries.add(i);
        if entry.key.saddr.all == key.saddr.all
            && entry.key.daddr.all == key.daddr.all
            && entry.key.l4proto == key.l4proto
            && entry.key.l3proto == key.l3proto
            && entry.key.zone == key.zone
        {
            if i < used - 1 {
                let last_entry = &*table.entries.add(used - 1);
                *entry = *last_entry;
            }
            table.used.store(used - 1, Ordering::Relaxed);
            return 0;
        }
    }

    -ENOENT
}

/// Clean up the flow table
#[no_mangle]
pub unsafe extern "C" fn nf_flow_table_inet_cleanup(table: *mut nf_flow_table_inet) {
    if table.is_null() {
        return;
    }

    let table = &mut *table;

    if !table.entries.is_null() {
        // Assuming the entries were allocated with kmalloc or similar
        // In a real implementation, you would free the memory here
        // For example: kfree(table.entries as *mut c_void);
    }

    table.entries = core::ptr::null_mut();
    table.size.store(0, Ordering::Relaxed);
    table.used.store(0, Ordering::Relaxed);
}
