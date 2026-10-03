#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(clippy::not_unsafe_ptr_arg_deref)]

use core::panic::PanicInfo;
use core::ptr::null_mut;
use core::sync::atomic::{AtomicPtr, Ordering};
use kernel_types::*;

pub type size_t = usize;
pub type c_size_t = usize;
pub type socklen_t = u32;

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}

#[repr(C)]
pub struct hlist_node { pub next: *mut hlist_node, pub pprev: *mut *mut hlist_node }

#[repr(C)]
pub struct hlist_head { pub first: *mut hlist_node }

#[repr(C)]
pub struct net_device { pub ifindex: c_int, pub name: [c_char; 16] }

#[repr(C)]
pub struct in_ifaddr {
    pub ifa_local: u32,
    pub ifa_address: u32,
    pub ifa_mask: u32,
    pub ifa_label: [c_char; 16],
    pub ifa_dev: *mut in_device,
    pub ifa_next: *mut in_ifaddr,
    pub hash: hlist_node,
}

#[repr(C)]
pub struct in_device {
    pub dev: *mut net_device,
    pub ifa_list: *mut in_ifaddr,
    pub refcnt: c_int,
}

#[repr(C)]
pub struct CacheKey { pub ifindex: c_int, pub addr: u32 }

#[repr(C)]
pub struct CacheStatistics {
    pub lookups: c_ulong,
    pub hits: c_ulong,
    pub misses: c_ulong,
}

#[repr(C)]
pub struct CacheManager {
    pub buckets: *mut hlist_head,
    pub nbuckets: c_uint,
    pub stats: CacheStatistics,
}

static GLOBAL_IDEV: AtomicPtr<in_device> = AtomicPtr::new(null_mut());

#[inline(always)]
unsafe fn hlist_add_head(node: *mut hlist_node, head: *mut hlist_head) {
    (*node).next = (*head).first;
    if !(*head).first.is_null() {
        (*(*head).first).pprev = &mut (*node).next;
    }
    (*head).first = node;
    (*node).pprev = &mut (*head).first;
}

#[inline(always)]
unsafe fn hlist_del(node: *mut hlist_node) {
    let next = (*node).next;
    let pprev = (*node).pprev;
    if !pprev.is_null() {
        *pprev = next;
    }
    if !next.is_null() {
        (*next).pprev = pprev;
    }
    (*node).next = null_mut();
    (*node).pprev = null_mut();
}

#[inline(always)]
fn hash_u32(v: u32, nbuckets: c_uint) -> c_uint {
    if nbuckets == 0 {
        return 0;
    }
    (v.wrapping_mul(2654435761) % nbuckets as u32) as c_uint
}

#[no_mangle]
pub extern "C" fn devinet_init(idev: *mut in_device) -> c_int {
    if idev.is_null() {
        return -22;
    }
    unsafe {
        (*idev).ifa_list = null_mut();
        (*idev).refcnt = 1;
        GLOBAL_IDEV.store(idev, Ordering::Release);
    }
    0
}

#[no_mangle]
pub extern "C" fn devinet_cleanup() {
    GLOBAL_IDEV.store(null_mut(), Ordering::Release);
}

#[no_mangle]
pub extern "C" fn in_dev_get(dev: *mut net_device) -> *mut in_device {
    let idev = GLOBAL_IDEV.load(Ordering::Acquire);
    if idev.is_null() {
        return null_mut();
    }
    unsafe {
        if (*idev).dev == dev {
            (*idev).refcnt += 1;
            idev
        } else {
            null_mut()
        }
    }
}

#[no_mangle]
pub extern "C" fn in_dev_put(idev: *mut in_device) {
    if idev.is_null() {
        return;
    }
    unsafe {
        if (*idev).refcnt > 0 {
            (*idev).refcnt -= 1;
        }
    }
}

#[no_mangle]
pub extern "C" fn inet_insert_ifa(idev: *mut in_device, ifa: *mut in_ifaddr) -> c_int {
    if idev.is_null() || ifa.is_null() {
        return -22;
    }
    unsafe {
        (*ifa).ifa_dev = idev;
        (*ifa).ifa_next = (*idev).ifa_list;
        (*idev).ifa_list = ifa;
    }
    0
}

#[no_mangle]
pub extern "C" fn inet_remove_ifa(idev: *mut in_device, ifa: *mut in_ifaddr) -> c_int {
    if idev.is_null() || ifa.is_null() {
        return -22;
    }
    unsafe {
        let mut prev: *mut in_ifaddr = null_mut();
        let mut cur = (*idev).ifa_list;
        while !cur.is_null() {
            if cur == ifa {
                if prev.is_null() {
                    (*idev).ifa_list = (*cur).ifa_next;
                } else {
                    (*prev).ifa_next = (*cur).ifa_next;
                }
                (*cur).ifa_next = null_mut();
                return 0;
            }
            prev = cur;
            cur = (*cur).ifa_next;
        }
    }
    -2
}

#[no_mangle]
pub extern "C" fn inet_lookup_ifaddr(idev: *const in_device, local: u32) -> *mut in_ifaddr {
    if idev.is_null() {
        return null_mut();
    }
    unsafe {
        let mut cur = (*idev).ifa_list;
        while !cur.is_null() {
            if (*cur).ifa_local == local {
                return cur;
            }
            cur = (*cur).ifa_next;
        }
    }
    null_mut()
}

#[no_mangle]
pub extern "C" fn cache_manager_init(
    cm: *mut CacheManager,
    buckets: *mut hlist_head,
    nbuckets: c_uint,
) -> c_int {
    if cm.is_null() || buckets.is_null() || nbuckets == 0 {
        return -22;
    }

    unsafe {
        (*cm).buckets = buckets;
        (*cm).nbuckets = nbuckets;
        (*cm).stats.lookups = 0;
        (*cm).stats.hits = 0;
        (*cm).stats.misses = 0;

        let mut i: c_uint = 0;
        while i < nbuckets {
            (*buckets.add(i as usize)).first = null_mut();
            i += 1;
        }
    }

    0
}

#[no_mangle]
pub extern "C" fn cache_insert(cm: *mut CacheManager, ifa: *mut in_ifaddr) -> c_int {
    if cm.is_null() || ifa.is_null() {
        return -22;
    }

    unsafe {
        let key = CacheKey {
            ifindex: if (*ifa).ifa_dev.is_null() || (*(*ifa).ifa_dev).dev.is_null() {
                0
            } else {
                (*(*(*ifa).ifa_dev).dev).ifindex
            },
            addr: (*ifa).ifa_local,
        };

        let idx = hash_u32(key.addr ^ (key.ifindex as u32), (*cm).nbuckets);
        let head = (*cm).buckets.add(idx as usize);
        hlist_add_head(&mut (*ifa).hash, head);
    }

    0
}

#[no_mangle]
pub extern "C" fn cache_remove(_cm: *mut CacheManager, ifa: *mut in_ifaddr) -> c_int {
    if ifa.is_null() {
        return -22;
    }
    unsafe {
        hlist_del(&mut (*ifa).hash);
    }
    0
}

#[no_mangle]
pub extern "C" fn cache_lookup(cm: *mut CacheManager, key: *const CacheKey) -> *mut in_ifaddr {
    if cm.is_null() || key.is_null() {
        return null_mut();
    }

    unsafe {
        (*cm).stats.lookups = (*cm).stats.lookups.wrapping_add(1);

        let idx = hash_u32((*key).addr ^ ((*key).ifindex as u32), (*cm).nbuckets);
        let mut node = (*(*cm).buckets.add(idx as usize)).first;

        while !node.is_null() {
            let ifa = node as *mut in_ifaddr;
            if !(*ifa).ifa_dev.is_null() && !(*(*ifa).ifa_dev).dev.is_null() {
                let ifindex = (*(*(*ifa).ifa_dev).dev).ifindex;
                if ifindex == (*key).ifindex && (*ifa).ifa_local == (*key).addr {
                    (*cm).stats.hits = (*cm).stats.hits.wrapping_add(1);
                    return ifa;
                }
            }
            node = (*node).next;
        }

        (*cm).stats.misses = (*cm).stats.misses.wrapping_add(1);
    }

    null_mut()
}
