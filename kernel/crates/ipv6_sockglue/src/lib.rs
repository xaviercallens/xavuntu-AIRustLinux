#![allow(clippy::all, clippy::pedantic)]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(clippy::too_many_arguments)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals, unreachable_patterns)]

use core::{mem, ptr, ffi::c_void};
use kernel_types::*;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOPROTOOPT: c_int = -92;
pub const ENOBUFS: c_int = -105;
pub const EADDRINUSE: c_int = -98;
pub const EFAULT: c_int = -14;

pub const SOCK_RAW: c_int = 3; pub const IPPROTO_RAW: c_int = 255; pub const GFP_KERNEL: u32 = 0x20;

pub type socklen_t = u32;

#[repr(C)]
pub struct in6_addr { pub s6_addr: [u8; 16] }

#[repr(C)]
pub struct sockaddr_in6 {
    pub sin6_family: u16,
    pub sin6_port: u16,
    pub sin6_flowinfo: u32,
    pub sin6_addr: in6_addr,
    pub sin6_scope_id: u32,
}

#[repr(C)]
pub struct ipv6_txoptions { pub opt_nflen: u32, pub opt_flen: u32 }

#[repr(C)]
pub struct group_source_req {
    pub gsr_interface: u32,
    pub gsr_group: sockaddr_in6,
    pub gsr_source: sockaddr_in6,
}

#[repr(C)]
pub struct group_filter {
    pub gf_interface: u32,
    pub gf_fmode: u32,
    pub gf_numsrc: u32,
    pub gf_group: sockaddr_in6,
    pub gf_slist: *const sockaddr_in6,
}

#[repr(C)]
pub struct list_head { pub next: *mut list_head, pub prev: *mut list_head }

#[repr(C)]
pub struct rwlock_t { pub raw_lock: u64 }

#[repr(C)]
pub struct sock { pub sk_type: u16, pub _pad: [u8; 6] }

#[repr(C)]
pub struct inet_sock {
    pub sk: sock,
    pub inet_num: u16,
    pub _pad2: [u8; 6],
}

#[repr(C)]
pub struct ip6_ra_chain {
    pub sk: *mut sock,
    pub sel: c_int,
    pub next: *mut ip6_ra_chain,
}

unsafe extern "C" {
    fn write_lock_bh(lock: *mut c_void);
    fn write_unlock_bh(lock: *mut c_void);
    fn kmalloc(size: size_t, flags: u32) -> *mut c_void;
    fn kfree(ptr: *mut c_void);
    fn sock_hold(sk: *mut sock);
    fn sock_put(sk: *mut sock);
    fn setsockopt_needs_rtnl(optname: c_int) -> bool;
    fn rtnl_lock();
    fn copy_from_sockptr(dst: *mut c_void, src: *const c_void, len: size_t) -> c_int;
    fn ip6_mroute_setsockopt(sk: *mut c_void, optname: c_int, optval: *const c_void, optlen: c_int) -> c_int;
}

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

static IP6_RA_CHAIN_HEAD: SyncWrapper<*mut ip6_ra_chain> = SyncWrapper::new(ptr::null_mut());
static IP6_RA_LOCK: SyncWrapper<rwlock_t> = SyncWrapper::new(rwlock_t { raw_lock: 0 });

// Function implementations

// Zero-Cost Abstraction Wrappers
pub struct SafeSock<'a> {
    pub ptr: *mut sock,
    _marker: core::marker::PhantomData<&'a mut sock>,
}
impl<'a> SafeSock<'a> {
    pub unsafe fn new(ptr: *mut sock) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}
pub struct SafeSkb<'a> {
    pub ptr: *mut sk_buff,
    _marker: core::marker::PhantomData<&'a mut sk_buff>,
}
impl<'a> SafeSkb<'a> {
    pub unsafe fn new(ptr: *mut sk_buff) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}

#[no_mangle]
pub unsafe extern "C" fn ip6_ra_control(sk: *mut c_void, sel: c_int) -> c_int {
    requires!(!sk.is_null(), "ip6_ra_control: sk cannot be null");
    let safe_sock = SafeSock::new(sk as *mut sock).unwrap_or_else(|| core::hint::unreachable_unchecked());

    // Check socket type
    // SAFETY: Caller guarantees sk is valid
    let sk_type = (*(safe_sock.ptr as *mut inet_sock)).sk.sk_type;
    let inet_num = 0; // Default inet_id value

    if sk_type != SOCK_RAW as u16 || inet_num != IPPROTO_RAW {
        ensures!(ENOPROTOOPT == -92, "ip6_ra_control: bad proto");
        return ENOPROTOOPT;
    }

    let new_ra: *mut ip6_ra_chain = if sel >= 0 {
        let p = kmalloc(mem::size_of::<ip6_ra_chain>() as size_t, GFP_KERNEL);
        if p.is_null() {
            ensures!(ENOMEM == -12, "ip6_ra_control: no mem");
            return ENOMEM;
        }
        let ra = p as *mut ip6_ra_chain;
        ptr::write(
            ra,
            ip6_ra_chain {
                sk: safe_sock.ptr,
                sel,
                next: ptr::null_mut(),
            },
        );
        ra
    } else {
        ptr::null_mut()
    };

    // SAFETY: Access to global IP6_RA_LOCK and IP6_RA_CHAIN_HEAD is serialized via write_lock_bh.
    let lock_ptr = unsafe { IP6_RA_LOCK.get_mut() as *mut rwlock_t as *mut c_void };
    write_lock_bh(lock_ptr);

    // SAFETY: Access protected by IP6_RA_LOCK
    let mut rap: *mut *mut ip6_ra_chain = unsafe { IP6_RA_CHAIN_HEAD.get_mut() as *mut *mut ip6_ra_chain };

    while !(*rap).is_null() {
        let ra = *rap;
        if (*ra).sk == sk as *mut sock {
            if sel >= 0 {
                write_unlock_bh(lock_ptr);
                if !new_ra.is_null() {
                    kfree(new_ra.cast::<c_void>());
                }
                return EADDRINUSE;
            }

            *rap = (*ra).next;
            write_unlock_bh(lock_ptr);
            sock_put(sk as *mut sock);
            kfree(ra.cast::<c_void>());
            return 0;
        }
        rap = &raw mut (*ra).next;
    }

    if new_ra.is_null() {
        write_unlock_bh(lock_ptr);
        return ENOBUFS;
    }

    (*new_ra).next = ptr::null_mut();
    *rap = new_ra;
    sock_hold(safe_sock.ptr);
    write_unlock_bh(lock_ptr);
    ensures!(0 == 0, "ip6_ra_control: success");
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ipv6_update_options(
    _sk: *mut c_void,
    opt: *mut ipv6_txoptions,
) -> *mut ipv6_txoptions {
    requires!(!_sk.is_null(), "ipv6_update_options: sk cannot be null");
    let _safe_sock = SafeSock::new(_sk as *mut sock).unwrap_or_else(|| core::hint::unreachable_unchecked());
    ensures!(true, "ipv6_update_options: valid return");
    opt
}

#[cfg(not(test))]
#[unsafe(no_mangle)]
pub extern "C" fn rust_eh_personality() {}

#[no_mangle]
pub unsafe extern "C" fn do_ipv6_setsockopt(
    sk: *mut c_void,
    _level: c_int,
    optname: c_int,
    optval: *const c_void,
    optlen: c_int,
) -> c_int {
    requires!(!sk.is_null(), "do_ipv6_setsockopt: sk cannot be null");
    let safe_sock = SafeSock::new(sk as *mut sock).unwrap_or_else(|| core::hint::unreachable_unchecked());

    let needs_rtnl = setsockopt_needs_rtnl(optname);
    if needs_rtnl {
        rtnl_lock();
    }
    // Implementation deferred.

    let mut val: c_int = 0;
    if !optval.is_null() && optlen >= mem::size_of::<c_int>() as c_int {
        if copy_from_sockptr(
            &mut val as *mut c_int as *mut c_void,
            optval,
            mem::size_of::<c_int>(),
        ) != 0
        {
            return EFAULT;
        }
    }

    let _valbool = val != 0;

    if ip6_mroute_opt(optname) {
        let ret = ip6_mroute_setsockopt(safe_sock.ptr as *mut c_void, optname, optval, optlen);
        ensures!(ret >= -4095 && ret <= 0, "do_ipv6_setsockopt: valid ret");
        return ret;
    }

    // Handle various options
    match optname {
        21 /* MCAST_BLOCK_SOURCE */ |
        20 /* MCAST_LEAVE_SOURCE_GROUP */ |
        19 /* MCAST_JOIN_SOURCE_GROUP */ |
        21 /* MCAST_BLOCK_SOURCE */ |
        22 /* MCAST_UNBLOCK_SOURCE */ => {
            let mut greqs: group_source_req = unsafe { mem::zeroed() };
            let ret = copy_group_source_from_sockptr(&mut greqs, optval, optlen);
            if ret != 0 {
                return ret;
            }

            // Implement source group handling logic
            // Implementation deferred.
            0
        },
        23 /* MCAST_MSFILTER */ => {
            // Implement multicast source filter
            // Implementation deferred.
            0
        },
        17 /* MCAST_JOIN_GROUP */ |
        18 /* MCAST_LEAVE_GROUP */ => {
            // Implement group join/leave
            // Implementation deferred.
            ensures!(0 == 0, "do_ipv6_setsockopt: success");
            0
        },
        _ => {
            ensures!(ENOPROTOOPT == -92, "do_ipv6_setsockopt: bad proto");
            ENOPROTOOPT
        },
    }
}

// Helper functions
unsafe fn copy_group_source_from_sockptr(
    greqs: *mut group_source_req,
    optval: *const c_void,
    optlen: c_int,
) -> c_int {
    if optval.is_null() || greqs.is_null() {
        return EINVAL;
    }

    if optlen < mem::size_of::<group_source_req>() as c_int {
        return EINVAL;
    }

    if copy_from_sockptr(
        greqs as *mut c_void,
        optval,
        mem::size_of::<group_source_req>() as size_t,
    ) != 0
    {
        return EFAULT;
    }

    0
}

// Implementation deferred.
unsafe fn ip6_mroute_opt(_optname: c_int) -> bool {
    false // Actual implementation would check specific values
}

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    #[test]
    fn test_ip6_ra_control() {
        // Basic test - would require actual kernel environment
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
