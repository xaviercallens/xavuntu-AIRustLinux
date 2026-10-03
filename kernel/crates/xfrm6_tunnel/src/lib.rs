#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]


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

use core::{ffi::{c_char, c_int, c_uint, c_void}, mem, ptr, sync::atomic::{AtomicU32, Ordering}};

// Opaque kernel objects (FFI-safe)
#[repr(C)]
pub struct net { _private: [u8; 0] }
#[repr(C)]
pub struct sk_buff { _private: [u8; 0] }
#[repr(C)]
pub struct xfrm_state { _private: [u8; 0] }
#[repr(C)]
pub struct spinlock_t { _private: u32 }

// Constants from C
const XFRM6_TUNNEL_SPI_BYADDR_HSIZE: c_uint = 256;
const XFRM6_TUNNEL_SPI_BYSPI_HSIZE: c_uint = 256;
const XFRM6_TUNNEL_SPI_MIN: u32 = 1;
const XFRM6_TUNNEL_SPI_MAX: u32 = 0xFFFF_FFFF;

// Type definitions
#[repr(C)]
struct hlist_head { first: *mut hlist_node }

#[repr(C)]
struct hlist_node { next: *mut hlist_node, pprev: *mut *mut hlist_node }

#[repr(C)]
pub struct xfrm_address_t { pub addr: [u8; 16] }

#[repr(C)]
struct rcu_head { func: Option<extern "C" fn(head: *mut rcu_head)> }

#[repr(C)]
struct xfrm6_tunnel_net {
    spi_byaddr: [hlist_head; XFRM6_TUNNEL_SPI_BYADDR_HSIZE as usize],
    spi_byspi: [hlist_head; XFRM6_TUNNEL_SPI_BYSPI_HSIZE as usize],
    spi: u32,
}

#[repr(C)]
struct xfrm6_tunnel_spi {
    list_byaddr: hlist_node,
    list_byspi: hlist_node,
    addr: xfrm_address_t,
    spi: u32,
    refcnt: AtomicU32,
    rcu_head: rcu_head,
}

#[repr(C)]
struct xfrm_state_props {
    mode: c_int,
    header_len: c_int,
    saddr: xfrm_address_t,
}

#[repr(C)]
struct xfrm_type {
    description: *const c_char,
    owner: *const c_void,
    proto: c_int,
    init_state: extern "C" fn(x: *mut xfrm_state) -> c_int,
    destructor: extern "C" fn(x: *mut xfrm_state),
    input: extern "C" fn(x: *mut xfrm_state, skb: *mut sk_buff) -> c_int,
    output: extern "C" fn(x: *mut xfrm_state, skb: *mut sk_buff) -> c_int,
}

#[repr(C)]
struct xfrm6_tunnel {
    handler: extern "C" fn(skb: *mut sk_buff) -> c_int,
    err_handler: extern "C" fn(
        skb: *mut sk_buff,
        opt: *mut c_void,
        type_: c_int,
        code: c_int,
        offset: c_int,
        info: u32,
    ) -> c_int,
    priority: c_int,
}

#[repr(C)]
struct pernet_operations {
    init: extern "C" fn(net: *mut net) -> c_int,
    exit: extern "C" fn(net: *mut net),
    id: *mut c_int,
    size: c_int,
}

// External kernel helpers
unsafe extern "C" {
    fn net_generic(net: *mut net, id: c_int) -> *mut c_void;
    fn rcu_read_lock_bh();
    fn rcu_read_unlock_bh();
    fn xfrm6_addr_equal(a: *const xfrm_address_t, b: *const xfrm_address_t) -> bool;
    fn spin_lock_bh(lock: *mut spinlock_t);
    fn spin_unlock_bh(lock: *mut spinlock_t);
    fn call_rcu(head: *mut rcu_head, func: extern "C" fn(*mut rcu_head));
    fn kmem_cache_alloc(cache: *mut c_void, flags: c_int) -> *mut c_void;
}

// Helper functions for hlist operations
unsafe fn hlist_del_rcu(_node: *mut hlist_node) {
    // Implementation deferred.
}

unsafe fn hlist_add_head_rcu(_node: *mut hlist_node, _head: *mut hlist_head) {
    // Implementation deferred.
}

// RCU callback
extern "C" fn x6spi_destroy_rcu(_head: *mut rcu_head) {
    // Implementation deferred.
}

// Pernet callbacks with parameter validation
extern "C" fn xfrm6_tunnel_net_init(net: *mut net) -> c_int {
    if net.is_null() {
        return -22; // -EINVAL
    }
    0
}
extern "C" fn xfrm6_tunnel_net_exit(_net: *mut net) {}

// Global variables
static XFRM6_TUNNEL_NET_ID: SyncWrapper<c_int> = SyncWrapper::new(0);
static XFRM6_TUNNEL_SPI_KMEM: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());
static XFRM6_TUNNEL_SPI_LOCK: SyncWrapper<spinlock_t> = SyncWrapper::new(spinlock_t { _private: 0 });
static XFRM6_TUNNEL_NET_OPS: SyncWrapper<pernet_operations> = SyncWrapper::new(pernet_operations {
    init: xfrm6_tunnel_net_init,
    exit: xfrm6_tunnel_net_exit,
    id: XFRM6_TUNNEL_NET_ID.0.get(),
    size: mem::size_of::<xfrm6_tunnel_net>() as c_int,
});

#[inline]
unsafe fn xfrm6_tunnel_pernet(n: *mut net) -> *mut xfrm6_tunnel_net {
    net_generic(n, *XFRM6_TUNNEL_NET_ID.get_mut()) as *mut xfrm6_tunnel_net
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn xfrm6_tunnel_spi_hash_byaddr(addr: *const xfrm_address_t) -> c_uint {
    let mut h: c_uint = 0;
    let p = (&(*addr).addr as *const [u8; 16]) as *const u8;
    let mut i = 0usize;
    while i < 16 {
        h = h.wrapping_add(*p.add(i) as c_uint);
        h = h.wrapping_mul(0x1e35_a7bd);
        i += 1;
    }
    h ^= h >> 16;
    h ^= h >> 8;
    h & (XFRM6_TUNNEL_SPI_BYADDR_HSIZE - 1)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn xfrm6_tunnel_spi_hash_byspi(spi: u32) -> c_uint {
    (spi as c_uint) % XFRM6_TUNNEL_SPI_BYSPI_HSIZE
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn xfrm6_tunnel_spi_lookup(n: *mut net, saddr: *const xfrm_address_t) -> u32 {
    let mut spi: u32 = 0;
    rcu_read_lock_bh();
    {
        let xfrm6_tn = xfrm6_tunnel_pernet(n);
        let h = xfrm6_tunnel_spi_hash_byaddr(saddr);

        let head = &(*xfrm6_tn).spi_byaddr[h as usize];
        let mut node = head.first;

        while !node.is_null() {
            let x6spi = (node as *mut xfrm6_tunnel_spi)
                .offset(-(mem::offset_of!(xfrm6_tunnel_spi, list_byaddr) as isize));

            if xfrm6_addr_equal(&(*x6spi).addr, saddr) {
                spi = (*x6spi).spi;
                break;
            }

            node = (*node).next;
        }
    }
    rcu_read_unlock_bh();

    spi
}

/// Look up or allocate SPI for tunnel
///
/// # Safety
/// - `net` must be a valid pointer to network namespace
/// - `saddr` must be a valid pointer to xfrm_address_t
#[no_mangle]
pub unsafe extern "C" fn xfrm6_tunnel_alloc_spi(net: *mut net, saddr: *mut xfrm_address_t) -> u32 {
    let mut spi: u32 = 0;

    // SAFETY: Spinlock held during critical section
    spin_lock_bh(XFRM6_TUNNEL_SPI_LOCK.get_mut());
    {
        let xfrm6_tn = xfrm6_tunnel_pernet(net);
        let h = xfrm6_tunnel_spi_hash_byaddr(saddr);

        let head = &(*xfrm6_tn).spi_byaddr[h as usize];
        let mut node = head.first;

        while !node.is_null() {
            let x6spi = (node as *mut xfrm6_tunnel_spi)
                .offset(-(mem::offset_of!(xfrm6_tunnel_spi, list_byaddr) as isize));

            if xfrm6_addr_equal(&(*x6spi).addr, saddr) {
                (*x6spi).refcnt.fetch_add(1, Ordering::Relaxed);
                spi = (*x6spi).spi;
                break;
            }

            node = (*node).next;
        }

        if spi == 0 {
            spi = __xfrm6_tunnel_alloc_spi(net, saddr);
        }
    }
    spin_unlock_bh(XFRM6_TUNNEL_SPI_LOCK.get_mut());

    spi
}

/// Free SPI reference
///
/// # Safety
/// - `net` must be a valid pointer to network namespace
/// - `saddr` must be a valid pointer to xfrm_address_t
#[no_mangle]
pub unsafe extern "C" fn xfrm6_tunnel_free_spi(net: *mut net, saddr: *mut xfrm_address_t) {
    // SAFETY: Spinlock held during critical section
    spin_lock_bh(XFRM6_TUNNEL_SPI_LOCK.get_mut());
    {
        let xfrm6_tn = xfrm6_tunnel_pernet(net);
        let h = xfrm6_tunnel_spi_hash_byaddr(saddr);

        let head = &(*xfrm6_tn).spi_byaddr[h as usize];
        let mut node = head.first;

        while !node.is_null() {
            let x6spi = (node as *mut xfrm6_tunnel_spi)
                .offset(-(mem::offset_of!(xfrm6_tunnel_spi, list_byaddr) as isize));

            if xfrm6_addr_equal(&(*x6spi).addr, saddr) {
                if (*x6spi).refcnt.fetch_sub(1, Ordering::Relaxed) == 1 {
                    // Remove from both hash tables
                    let list_byaddr = &mut (*x6spi).list_byaddr;
                    let list_byspi = &mut (*x6spi).list_byspi;

                    hlist_del_rcu(list_byaddr);
                    hlist_del_rcu(list_byspi);

                    call_rcu(&mut (*x6spi).rcu_head, x6spi_destroy_rcu);
                }
                break;
            }

            node = (*node).next;
        }
    }
    spin_unlock_bh(XFRM6_TUNNEL_SPI_LOCK.get_mut());
}

/// Check if SPI is already allocated
///
/// # Safety
/// - `net` must be a valid pointer to network namespace
/// - `spi` must be a valid SPI value
#[no_mangle]
pub unsafe extern "C" fn __xfrm6_tunnel_spi_check(net: *mut net, spi: u32) -> c_int {
    let xfrm6_tn = xfrm6_tunnel_pernet(net);
    let h = xfrm6_tunnel_spi_hash_byspi(spi);

    let head = &(*xfrm6_tn).spi_byspi[h as usize];
    let mut node = head.first;

    while !node.is_null() {
        let x6spi = (node as *mut xfrm6_tunnel_spi)
            .offset(-(mem::offset_of!(xfrm6_tunnel_spi, list_byspi) as isize));

        if (*x6spi).spi == spi {
            return -1;
        }

        node = (*node).next;
    }

    h as c_int
}

/// Allocate new SPI
///
/// # Safety
/// - `net` must be a valid pointer to network namespace
/// - `saddr` must be a valid pointer to xfrm_address_t
#[no_mangle]
pub unsafe extern "C" fn __xfrm6_tunnel_alloc_spi(
    net: *mut net,
    saddr: *mut xfrm_address_t,
) -> u32 {
    let xfrm6_tn = xfrm6_tunnel_pernet(net);
    let spi: u32 = 0;
    let mut index: c_int = -1;

    if (*xfrm6_tn).spi < XFRM6_TUNNEL_SPI_MIN || (*xfrm6_tn).spi >= XFRM6_TUNNEL_SPI_MAX {
        (*xfrm6_tn).spi = XFRM6_TUNNEL_SPI_MIN;
    } else {
        (*xfrm6_tn).spi += 1;
    }

    for spi in (*xfrm6_tn).spi..=XFRM6_TUNNEL_SPI_MAX {
        index = __xfrm6_tunnel_spi_check(net, spi);
        if index >= 0 {
            break;
        }
    }

    if index < 0 {
        for spi in XFRM6_TUNNEL_SPI_MIN..(*xfrm6_tn).spi {
            index = __xfrm6_tunnel_spi_check(net, spi);
            if index >= 0 {
                break;
            }
        }
    }

    if index >= 0 {
        (*xfrm6_tn).spi = spi;

        // Allocate new SPI entry
        let x6spi = kmem_cache_alloc(*XFRM6_TUNNEL_SPI_KMEM.get_mut(), 0) as *mut xfrm6_tunnel_spi;
        if !x6spi.is_null() {
            ptr::copy_nonoverlapping(saddr, &mut (*x6spi).addr, mem::size_of::<xfrm_address_t>());
            (*x6spi).spi = spi;
            (*x6spi).refcnt.store(1, Ordering::Relaxed);

            // Add to hash tables
            let h_byspi = xfrm6_tunnel_spi_hash_byspi(spi);
            hlist_add_head_rcu(
                &mut (*x6spi).list_byspi,
                &mut (*xfrm6_tn).spi_byspi[h_byspi as usize],
            );

            let h_byaddr = xfrm6_tunnel_spi_hash_byaddr(&(*x6spi).addr);
            hlist_add_head_rcu(
                &mut (*x6spi).list_byaddr,
                &mut (*xfrm6_tn).spi_byaddr[h_byaddr as usize],
            );
        }
    }

    spi
}

// Duplicate removed - main implementation at line 180
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_xfrm6_tunnel_net_init_null() {
        let ret = xfrm6_tunnel_net_init(ptr::null_mut());
        assert_eq!(ret, -22);
    }

    #[test]
    fn test_xfrm6_tunnel_spi_hash() {
        let addr = xfrm_address_t { addr: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16] };
        let h_addr = unsafe { xfrm6_tunnel_spi_hash_byaddr(&addr) };
        assert!(h_addr < XFRM6_TUNNEL_SPI_BYADDR_HSIZE);

        let h_spi = unsafe { xfrm6_tunnel_spi_hash_byspi(42) };
        assert_eq!(h_spi, 42 % XFRM6_TUNNEL_SPI_BYSPI_HSIZE);
    }
}
