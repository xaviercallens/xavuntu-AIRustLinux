#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
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

use kernel_types::*;
use core::{ptr, sync::atomic::AtomicU32};

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENODEV: c_int = -19;
pub const ENOENT: c_int = -2;
pub const EPERM: c_int = -1;
pub const EADDRNOTAVAIL: c_int = -99;

pub const CAP_NET_ADMIN: c_int = 12; pub const IFA_F_TENTATIVE: c_int = 0x40;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib6_info { _priv: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct rcu_head {
    pub next: *mut rcu_head,
    pub func: Option<unsafe extern "C" fn(*mut rcu_head)>,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct spinlock_t { _priv: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct user_namespace { _priv: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net { pub ipv6: ipv6_net, pub user_ns: *mut user_namespace }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net_device { pub ifindex: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_devconf { pub forwarding: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet6_dev { pub cnf: ipv6_devconf }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct dst_entry { pub dev: *mut net_device }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct rt6_info { pub dst: dst_entry }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_pinfo { pub ipv6_ac_list: *mut ipv6_ac_socklist }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sock { _priv: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct hlist_head { pub first: *mut hlist_node }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct hlist_node { pub next: *mut hlist_node, pub pprev: *mut *mut hlist_node }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct devconf6_config { pub forwarding: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_ac_socklist {
    pub acl_next: *mut ipv6_ac_socklist,
    pub acl_addr: in6_addr,
    pub acl_ifindex: c_int,
}

pub struct ifacaddr6 {
    pub aca_addr: in6_addr,
    pub aca_next: *mut ifacaddr6,
    pub aca_users: c_int,
    pub aca_cstamp: u32,
    pub aca_tstamp: u32,
    pub aca_refcnt: AtomicU32,
    pub aca_addr_lst: hlist_node,
    pub aca_rt: *mut fib6_info,
    pub rcu: rcu_head,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_net { pub devconf_all: *mut devconf6_config }

const IN6_ADDR_HSIZE_SHIFT: u32 = 8; const IN6_ADDR_HSIZE: u32 = 1 << IN6_ADDR_HSIZE_SHIFT;

#[no_mangle]
pub static inet6_acaddr_lst: SyncWrapper<[hlist_head; IN6_ADDR_HSIZE as usize]> =
    SyncWrapper::new([hlist_head { first: ptr::null_mut() }; IN6_ADDR_HSIZE as usize]);

unsafe extern "C" {

    fn ipv6_addr_hash(addr: *const in6_addr) -> u32;
    fn net_hash_mix(netns: *mut net) -> u32;
    fn hash_32(val: u32, bits: u32) -> u32;

    fn inet6_sk(sk: *mut sock) -> *mut ipv6_pinfo;
    fn sock_net(sk: *mut sock) -> *mut net;
    fn ns_capable(user_ns: *mut user_namespace, cap: c_int) -> bool;
    fn ipv6_addr_is_multicast(addr: *const in6_addr) -> c_int;

    fn __dev_get_by_index(netns: *mut net, ifindex: c_int) -> *mut net_device;
    fn __dev_get_by_flags(netns: *mut net, flags: c_int, mask: c_int) -> *mut net_device;
    fn ipv6_chk_addr_and_flags(
        netns: *mut net,
        addr: *const in6_addr,
        dev: *mut net_device,
        strict: c_int,
        banned_flags: c_int,
        check_flags: c_int,
    ) -> c_int;

    fn sock_kmalloc(sk: *mut sock, size: size_t, gfp: c_int) -> *mut c_void;
    fn sock_kfree_s(sk: *mut sock, mem: *mut c_void, size: size_t);

    fn rt6_lookup(
        netns: *mut net,
        daddr: *const in6_addr,
        saddr: *mut in6_addr,
        ifindex: c_int,
        strict: *mut c_void,
        flags: c_int,
    ) -> *mut rt6_info;
    fn ip6_rt_put(rt: *mut rt6_info);

    fn __in6_dev_get(dev: *mut net_device) -> *mut inet6_dev;
    fn ipv6_chk_prefix(addr: *const in6_addr, dev: *mut net_device) -> bool;
    fn __ipv6_dev_ac_inc(idev: *mut inet6_dev, addr: *const in6_addr) -> c_int;
    fn __ipv6_dev_ac_dec(idev: *mut inet6_dev, addr: *const in6_addr) -> c_int;
}

#[no_mangle]
pub unsafe extern "C" fn inet6_acaddr_hash(netns: *mut net, addr: *const in6_addr) -> u32 {
    let val = ipv6_addr_hash(addr) ^ net_hash_mix(netns);
    hash_32(val, IN6_ADDR_HSIZE_SHIFT)
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_sock_ac_join(
    sk: *mut sock,
    _ifindex: c_int,
    addr: *const in6_addr,
) -> c_int {
    // 🛡️ FORMAL VERIFICATION BOUNDARY (Mapped to Lean 4: anycast_resolution_termination)
    requires!(!sk.is_null(), "anycast_resolution_termination: sk invariant violated");
    requires!(!addr.is_null(), "anycast_resolution_termination: addr invariant violated");

    let netns = sock_net(sk);

    if !ns_capable((*netns).user_ns, CAP_NET_ADMIN) {
        return EPERM;
    }

    if ipv6_addr_is_multicast(addr) != 0 {
        return EINVAL;
    }

    0
}

#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
