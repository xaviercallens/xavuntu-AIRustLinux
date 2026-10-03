#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]

use core::{ptr, ffi::{c_int, c_void}, mem::size_of, panic::PanicInfo};
use kernel_types::*;

pub type socklen_t = u32;
pub type size_t = usize;
pub type c_size_t = usize;

pub const EINVAL: c_int = 22;
pub const ENOMEM: c_int = 12;
pub const ENODEV: c_int = 19;
pub const EADDRINUSE: c_int = 98;
pub const EADDRNOTAVAIL: c_int = 99;

#[repr(C)]
pub struct CacheKey {
    pub ifindex: c_int,
    pub group: in6_addr,
    pub source: in6_addr,
}

#[repr(C)]
pub struct CacheStatistics {
    pub joins: u64,
    pub leaves: u64,
    pub errors: u64,
}

#[repr(C)]
pub struct CacheManager { pub head: *mut c_void, pub stats: CacheStatistics }

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}

#[unsafe(no_mangle)]
pub extern "C" fn rust_eh_personality() {}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct work_struct { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net_device { pub ifindex: c_int, _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_devconf {
    pub mldv1_unsolicited_report_interval: c_int,
    pub mldv2_unsolicited_report_interval: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet6_dev {
    pub mc_list: *mut ifmcaddr6,
    pub mc_tomb: *mut ifmcaddr6,
    pub dead: c_int,
    pub cnf: ipv6_devconf,
    _private: [u8; 0],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ifmcaddr6 {
    pub next: *mut ifmcaddr6,
    pub mca_addr: in6_addr,
    pub mca_sfmode: c_int,
    pub mca_users: c_int,
    pub idev: *mut inet6_dev,
    _private: [u8; 0],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_mc_socklist {
    pub next: *mut ipv6_mc_socklist,
    pub addr: in6_addr,
    pub ifindex: c_int,
    pub sfmode: c_int,
    pub sflist: *mut c_void,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct group_source_req {
    pub gsr_interface: c_int,
    pub gsr_group: in6_addr,
    pub gsr_source: in6_addr,
}

#[repr(C)]
pub struct ipv6_pinfo { pub ipv6_mc_list: *mut ipv6_mc_socklist }

#[repr(C)]
pub struct mcast_sock {
    pub sk: sock,
    pub pinet6: *mut ipv6_pinfo,
    pub sk_omem_alloc: c_int,
}

unsafe extern "C" {
    fn kmalloc(size: c_size_t, flags: c_int) -> *mut c_void;
    fn kfree(ptr: *mut c_void);
}

unsafe fn ipv6_addr_equal(a: *const in6_addr, b: *const in6_addr) -> bool {
    if a.is_null() || b.is_null() {
        return false;
    }
    // SAFETY: validated non-null above; plain value read for POD FFI type.
    unsafe { ptr::read(a).in6_u.u6_addr8 == ptr::read(b).in6_u.u6_addr8 }
}

unsafe fn ipv6_addr_is_multicast(addr: *const in6_addr) -> bool {
    if addr.is_null() {
        return false;
    }
    // SAFETY: validated non-null above; plain value read for POD FFI type.
    let bytes = unsafe { ptr::read(addr) };
    bytes.in6_u.u6_addr8[0] == 0xff
}

unsafe fn __dev_get_by_index(_net: *mut c_void, _ifindex: c_int) -> *mut net_device {
    ptr::null_mut()
}

unsafe fn __in6_dev_get(_dev: *mut net_device) -> *mut inet6_dev {
    ptr::null_mut()
}

unsafe fn __ipv6_dev_mc_dec(_idev: *mut inet6_dev, _addr: *const in6_addr) {}

unsafe fn __ipv6_dev_mc_inc(_idev: *mut inet6_dev, _addr: *const in6_addr, _mode: c_int) -> c_int {
    0
}

unsafe fn atomic_sub(v: c_int, a: *mut c_int) {
    if !a.is_null() {
        // SAFETY: caller provides valid pointer in kernel context.
        unsafe { *a -= v };
    }
}

unsafe fn alloc_mc_socklist() -> *mut ipv6_mc_socklist {
    // SAFETY: FFI allocator call.
    let p = unsafe { kmalloc(size_of::<ipv6_mc_socklist>() as c_size_t, 0) } as *mut ipv6_mc_socklist;
    if !p.is_null() {
        // SAFETY: allocated block is at least size_of::<ipv6_mc_socklist>() bytes.
        unsafe { ptr::write_bytes(p as *mut u8, 0, size_of::<ipv6_mc_socklist>()) };
    }
    p
}

unsafe fn free_mc_socklist(p: *mut ipv6_mc_socklist) {
    if !p.is_null() {
        // SAFETY: pointer originated from kmalloc.
        unsafe { kfree(p as *mut c_void) };
    }
}

unsafe fn __ipv6_sock_mc_join(
    sk: *mut sock,
    ifindex: c_int,
    addr: *const in6_addr,
    mode: c_int,
) -> c_int {
    if sk.is_null() || addr.is_null() {
        return -EINVAL;
    }
    // SAFETY: validated addr above.
    if unsafe { !ipv6_addr_is_multicast(addr) } {
        return -EINVAL;
    }

    let msk = sk as *mut mcast_sock;
    // SAFETY: raw pointer checks before dereference.
    if msk.is_null() || unsafe { (*msk).pinet6.is_null() } {
        return -EINVAL;
    }

    // SAFETY: pinet6 checked non-null above.
    let mut cur = unsafe { (*(*msk).pinet6).ipv6_mc_list };
    while !cur.is_null() {
        // SAFETY: cur non-null in loop.
        if (ifindex == 0 || unsafe { (*cur).ifindex == ifindex })
            // SAFETY: cur non-null and addr checked.
            && unsafe { ipv6_addr_equal(&(*cur).addr, addr) }
        {
            return -EADDRINUSE;
        }
        // SAFETY: cur non-null in loop.
        cur = unsafe { (*cur).next };
    }

    // SAFETY: allocator wrapper.
    let mc = unsafe { alloc_mc_socklist() };
    if mc.is_null() {
        return -ENOMEM;
    }

    // SAFETY: all pointers validated above.
    unsafe {
        (*mc).addr = ptr::read(addr);
        (*mc).ifindex = ifindex;
        (*mc).sfmode = mode;
        (*mc).sflist = ptr::null_mut();
        (*mc).next = (*(*msk).pinet6).ipv6_mc_list;
        (*(*msk).pinet6).ipv6_mc_list = mc;
        (*msk).sk_omem_alloc += size_of::<ipv6_mc_socklist>() as c_int;
    }

    let net = ptr::null_mut();
    // SAFETY: stubbed helper.
    let dev = unsafe { __dev_get_by_index(net, ifindex) };
    if !dev.is_null() {
        // SAFETY: dev non-null.
        let idev = unsafe { __in6_dev_get(dev) };
        if !idev.is_null() {
            // SAFETY: idev and mc valid.
            let ret = unsafe { __ipv6_dev_mc_inc(idev, &(*mc).addr, mode) };
            if ret < 0 {
                // SAFETY: rollback list/accounting and free allocation.
                unsafe {
                    (*(*msk).pinet6).ipv6_mc_list = (*mc).next;
                    atomic_sub(size_of::<ipv6_mc_socklist>() as c_int, &mut (*msk).sk_omem_alloc);
                    free_mc_socklist(mc);
                }
                return ret;
            }
        }
    }

    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ipv6_sock_mc_join(
    sk: *mut sock,
    ifindex: c_int,
    addr: *const in6_addr,
) -> c_int {
    // SAFETY: FFI boundary forwards raw pointers unchanged.
    unsafe { __ipv6_sock_mc_join(sk, ifindex, addr, 0) }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ipv6_sock_mc_join_ssm(
    sk: *mut sock,
    ifindex: c_int,
    gsr: *const group_source_req,
) -> c_int {
    if gsr.is_null() {
        return -EINVAL;
    }
    // SAFETY: validated gsr above.
    let addr = unsafe { &(*gsr).gsr_group };
    let mode = 1; // SSM mode
    unsafe { __ipv6_sock_mc_join(sk, ifindex, addr, mode) }
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_sock_mc_drop(
    sk: *mut sock,
    ifindex: c_int,
    addr: *const in6_addr,
) -> c_int {
    // Validate inputs
    if sk.is_null() || addr.is_null() {
        return -EINVAL;
    }

    let msk = sk as *mut mcast_sock;
    if msk.is_null() || unsafe { (*msk).pinet6.is_null() } {
        return -EINVAL;
    }

    let net = ptr::null_mut(); // Network namespace pointer

    // SAFETY: pinet6 validated above.
    let mut mc_ptr = unsafe { &mut (*(*msk).pinet6).ipv6_mc_list };
    while !unsafe { ptr::read(mc_ptr) }.is_null() {
        let mc_lst = unsafe { ptr::read(mc_ptr) };
        // SAFETY: mc_lst is non-null in loop.
        if (ifindex == 0 || unsafe { (*mc_lst).ifindex } == ifindex)
            && unsafe { ipv6_addr_equal(&(*mc_lst).addr, addr) }
        {
            // Remove from list
            // SAFETY: mc_lst non-null.
            unsafe { ptr::write(mc_ptr, (*mc_lst).next) };

            // SAFETY: helper function calls.
            let dev = unsafe { __dev_get_by_index(net, (*mc_lst).ifindex) };
            if !dev.is_null() {
                let idev = unsafe { __in6_dev_get(dev) };
                if !idev.is_null() {
                    unsafe { __ipv6_dev_mc_dec(idev, &(*mc_lst).addr) };
                }
            }

            // Free memory
            unsafe {
                atomic_sub(
                    size_of::<ipv6_mc_socklist>() as c_int,
                    &mut (*msk).sk_omem_alloc,
                );
                free_mc_socklist(mc_lst);
            }
            return 0;
        }
        // SAFETY: mc_lst non-null.
        mc_ptr = unsafe { &mut (*mc_lst).next };
    }

    -EADDRNOTAVAIL
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_dev_mc_inc(
    _dev: *mut net_device,
    _addr: *const in6_addr,
    _mode: c_int,
) -> c_int {
    // Implementation deferred.
    0
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_dev_mc_dec(_dev: *mut net_device, _addr: *const in6_addr) {
    // Implementation deferred.
}

// Tests
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ipv6_addr_is_multicast() {
        let mut addr = in6_addr { in6_u: in6_addr_union { u6_addr8: [0; 16] } };
        addr.in6_u.u6_addr8[0] = 0xFF; // Multicast
        unsafe {
            assert_eq!(ipv6_addr_is_multicast(&addr), 1);
        }

        addr.in6_u.u6_addr8[0] = 0x00; // Unicast
        unsafe {
            assert_eq!(ipv6_addr_is_multicast(&addr), 0);
        }
    }

    #[test]
    fn test_ipv6_addr_equal() {
        let a = in6_addr { in6_u: in6_addr_union { u6_addr8: [0; 16] } };
        let b = in6_addr { in6_u: in6_addr_union { u6_addr8: [0; 16] } };
        unsafe {
            assert_eq!(ipv6_addr_equal(&a, &b), 1);
        }

        let mut c = in6_addr { in6_u: in6_addr_union { u6_addr8: [0; 16] } };
        c.in6_u.u6_addr8[0] = 1;
        unsafe {
            assert_eq!(ipv6_addr_equal(&a, &c), 0);
        }
    }
}
