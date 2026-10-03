#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(dead_code)]

use kernel_types::*;
use core::ptr;
use core::mem;

pub type size_t = usize;
pub type c_size_t = usize;
pub type socklen_t = u32;

// Constants from C
pub const EINVAL: c_int = 22;
pub const ENOMEM: c_int = 12;
pub const ENETUNREACH: c_int = 101;
pub const EAFNOSUPPORT: c_int = 97;

// Local definitions shadowing or augmenting kernel_types to avoid clutter
#[repr(C)]
#[derive(Copy, Clone)]
pub struct proto {
    pub rehash: Option<unsafe extern "C" fn(*mut sock)>,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sock {
    pub sk_family: c_ushort,
    pub sk_type: c_ushort,
    pub sk_protocol: c_ushort,
    pub sk_state: c_uint,
    pub sk_refcnt: c_int,
    pub sk_reuseport_cb: *mut c_void,
    pub sk_reuse: c_int,
    pub sk_reuseport: *mut c_void,
    pub sk_rcv_saddr: *mut c_void,
    pub sk_bound_dev_if: c_int,
    pub sk_v6_rcv_saddr: in6_addr,
    pub sk_v6_daddr: in6_addr,
    pub sk_user_data: *mut c_void,
    pub sk_ipv6only: c_int,
    pub sk_prot: *mut proto,
    pub sk_destruct: Option<unsafe extern "C" fn(*mut sock)>,
    pub sk_backlog_rcv: Option<extern "C" fn(*mut sock, *mut c_void, usize) -> c_int>,
    pub sk_mark: u32,
    pub sk_uid: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_pinfo {
    pub saddr: in6_addr,
    pub daddr: in6_addr,
    pub flow_label: __be32,
    pub frag_size: __u32,
    pub hop_limit: __s16,
    pub mcast_hops: __s16,
    pub mcast_oif: c_int,
    pub rxopt: ip6cb,
    pub mc_loop: u8,
    pub mc_all: u8,
    pub pmtudisc: u8,
    pub repflow: u8,
    pub sticky_pktinfo: pktinfo,
    pub sndflow: u8,
    pub opt: *mut ipv6_txoptions,
    pub dst_cookie: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_sock {
    pub sk: *mut c_void,
    pub pinet6: *mut c_void,
    pub inet_saddr: __be32,
    pub uc_ttl: __s16,
    pub cmsg_flags: __u16,
    pub inet_sport: __be16,
    pub inet_dport: __be16,
    pub inet_rcv_saddr: __be32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct dst_ops {
    pub check: Option<unsafe extern "C" fn(*mut dst_entry, u32) -> c_int>,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct dst_entry {
    pub obsolete: c_int,
    pub ops: *mut dst_ops,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct flowi6 {
    pub flowi6_proto: u8,
    pub daddr: in6_addr,
    pub saddr: in6_addr,
    pub flowi6_oif: c_int,
    pub flowi6_mark: c_int,
    pub fl6_dport: u16,
    pub fl6_sport: u16,
    pub flowlabel: u32,
    pub flowi6_uid: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct pktinfo { pub ipi6_ifindex: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct rxopt_bits { pub rxpmtu: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_flowlabel { pub opt: *mut ipv6_txoptions }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_txoptions { _unused: [u8; 0] }

unsafe extern "C" {
    fn ipv6_addr_v4mapped(a: *const in6_addr) -> bool;
    fn ipv6_addr_is_multicast(a: *const in6_addr) -> bool;
    fn ipv6_addr_any(a: *const in6_addr) -> bool;

    fn security_sk_classify_flow(sk: *mut sock, fl6: *mut flowi6);

    fn fl6_sock_lookup(sk: *mut sock, label: u32) -> *mut ip6_flowlabel;
    fn rcu_dereference(p: *mut ipv6_txoptions) -> *mut ipv6_txoptions;

    fn sock_net(sk: *mut sock) -> *mut c_void;
    fn ip6_dst_lookup_flow(
        net: *mut c_void,
        sk: *mut sock,
        fl6: *mut flowi6,
        final_p: *mut in6_addr,
    ) -> *mut c_void;

    fn inet_sk(sk: *mut sock) -> *mut inet_sock;
    fn inet6_sk(sk: *mut sock) -> *mut ipv6_pinfo;
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

#[no_mangle]
pub unsafe extern "C" fn rust_eh_personality() {}

#[no_mangle]
pub unsafe extern "C" fn ipv6_mapped_addr_any(a: *const in6_addr) -> bool {
    if a.is_null() {
        return false;
    }
    let a_ref = &*a;
    ipv6_addr_v4mapped(a) && (a_ref.in6_u.u6_addr32[3] == 0)
}

#[no_mangle]
pub unsafe extern "C" fn ip6_datagram_flow_key_init(fl6: *mut flowi6, sk: *mut sock) {
    if fl6.is_null() || sk.is_null() {
        return;
    }

    let inet = inet_sk(sk);
    let np = inet6_sk(sk);

    ptr::write_bytes(fl6, 0, 1);
    (*fl6).flowi6_proto = (*sk).sk_protocol as u8;
    (*fl6).daddr = (*sk).sk_v6_daddr;
    (*fl6).saddr = (*np).saddr;
    (*fl6).flowi6_oif = (*sk).sk_bound_dev_if;
    (*fl6).flowi6_mark = (*sk).sk_mark as c_int;
    (*fl6).fl6_dport = (*inet).inet_dport;
    (*fl6).fl6_sport = (*inet).inet_sport;
    (*fl6).flowlabel = (*np).flow_label;
    (*fl6).flowi6_uid = (*sk).sk_uid;

    if (*fl6).flowi6_oif == 0 {
        (*fl6).flowi6_oif = (*np).sticky_pktinfo.ipi6_ifindex;
    }

    if (*fl6).flowi6_oif == 0 && ipv6_addr_is_multicast(&(*fl6).daddr) {
        (*fl6).flowi6_oif = (*np).mcast_oif;
    }

    security_sk_classify_flow(sk, fl6);
}

#[no_mangle]
pub unsafe extern "C" fn ip6_datagram_dst_update(
    sk: *mut sock,
    fix_sk_saddr: c_int
) -> c_int {
    let np = inet6_sk(sk);
    let mut flowlabel: *mut ip6_flowlabel = ptr::null_mut();

    if (*np).sndflow != 0 && ((*np).flow_label & 0x0FFFFFFF) != 0 {
        flowlabel = fl6_sock_lookup(sk, (*np).flow_label);
        if flowlabel.is_null() {
            return -EINVAL;
        }
    }

    let mut fl6: flowi6 = mem::zeroed();
    ip6_datagram_flow_key_init(&mut fl6, sk);

    let _opt: *mut ipv6_txoptions = if !flowlabel.is_null() {
        (*flowlabel).opt
    } else {
        rcu_dereference((*np).opt)
    };

    let final_p: *mut in6_addr = ptr::null_mut();

    let dst = ip6_dst_lookup_flow(sock_net(sk), sk, &mut fl6, final_p) as *mut dst_entry;
    if dst.is_null() {
        if !flowlabel.is_null() {
            fl6_sock_release(flowlabel);
        }
        return -ENETUNREACH;
    }

    if fix_sk_saddr != 0 {
        if ipv6_addr_any(&(*np).saddr) {
            (*np).saddr = fl6.saddr;
        }

        if ipv6_addr_any(&(*sk).sk_v6_rcv_saddr) {
            (*sk).sk_v6_rcv_saddr = fl6.saddr;
            let inet = inet_sk(sk);
            (*inet).inet_rcv_saddr = 0x7F000001; // LOOPBACK4_IPV6
            let prot = (*sk).sk_prot;
            if !prot.is_null() {
                if let Some(rehash) = (*prot).rehash {
                    rehash(sk);
                }
            }
        }
    }

    ip6_sk_dst_store_flow(sk, dst, &mut fl6);

    if !flowlabel.is_null() {
        fl6_sock_release(flowlabel);
    }
    0
}

/// Release callback for IPv6 datagram
///
/// # Safety
/// - `sk` must be a valid pointer to sock
#[no_mangle]
pub unsafe extern "C" fn ip6_datagram_release_cb(
    sk: *mut sock
) {
    if ipv6_addr_v4mapped(&(*sk).sk_v6_daddr) {
        return;
    }

    rcu_read_lock();
    let dst = __sk_dst_get(sk);
    let np = inet6_sk(sk);
    if !dst.is_null() && !(*dst).ops.is_null() && ((*dst).obsolete == 0 || (*(*dst).ops).check.map_or(false, |check| check(dst, (*np).dst_cookie) != 0)) {
        rcu_read_unlock();
        return;
    }
    rcu_read_unlock();

    ip6_datagram_dst_update(sk, 0);
}

#[inline]
unsafe fn rcu_read_lock() {}

#[inline]
unsafe fn rcu_read_unlock() {}

#[inline]
unsafe fn __sk_dst_get(_sk: *mut sock) -> *mut dst_entry {
    ptr::null_mut()
}

#[inline]
unsafe fn ip6_sk_dst_store_flow(_sk: *mut sock, _dst: *mut dst_entry, _fl6: *mut flowi6) {
    // Implementation deferred.
}

#[inline]
unsafe fn fl6_sock_release(_flowlabel: *mut ip6_flowlabel) {
    // Implementation deferred.
}
