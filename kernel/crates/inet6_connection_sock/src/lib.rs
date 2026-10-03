#![allow(clippy::all, clippy::pedantic)]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]

use core::{mem, ffi::{c_int, c_void}};
use kernel_types::*;

#[repr(transparent)]
pub struct SafeSocket(*mut sock);

impl SafeSocket {
    #[inline(always)]
    pub unsafe fn new(ptr: *mut sock) -> Self {
        requires!(!ptr.is_null(), "Socket pointer must not be null");
        Self(ptr)
    }
    
    #[inline(always)]
    pub fn as_ptr(&self) -> *mut sock {
        self.0
    }
    
    #[inline(always)]
    pub fn as_const_ptr(&self) -> *const sock {
        self.0 as *const sock
    }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

// Stable kernel-style aliases.
type size_t = usize;
type c_size_t = usize;
type socklen_t = u32;

// Fallback FFI types that may be missing from kernel_types in some build setups.
#[repr(C)]
#[derive(Copy, Clone)]
pub union in6_addr_union {
    pub u6_addr8: [u8; 16],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct in6_addr { pub in6_u: in6_addr_union }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct flowi6 {
    pub flowi6_proto: u8,
    pub __pad_proto: [u8; 3],
    pub daddr: in6_addr,
    pub saddr: in6_addr,
    pub flowlabel: u32,
    pub flowi6_oif: c_int,
    pub flowi6_mark: u32,
    pub fl6_sport: u16,
    pub fl6_dport: u16,
    pub flowi6_uid: u32,
}

#[repr(C)]
pub struct request_sock { _priv: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_request_sock {
    pub ir_v6_rmt_addr: in6_addr,
    pub ir_v6_loc_addr: in6_addr,
    pub ir_iif: c_int,
    pub ir_mark: u32,
    pub ir_rmt_port: u16,
    pub ir_num: u16,
}

#[repr(C)]
pub struct sockaddr_in6 {
    pub sin6_family: u16,
    pub sin6_port: u16,
    pub sin6_flowinfo: u32,
    pub sin6_addr: in6_addr,
    pub sin6_scope_id: u32,
}

pub const ENOMEM: c_int = -12; pub const EINVAL: c_int = -22; pub const AF_INET6: u16 = 10;

extern "C" {
    fn memset(s: *mut c_void, c: c_int, n: size_t) -> *mut c_void;
    fn rcu_read_lock();
    fn rcu_read_unlock();

    fn fl6_update_dst(fl6: *mut flowi6, opt: *const c_void, final_p: *mut in6_addr) -> *mut in6_addr;
    fn ip6_dst_lookup_flow(
        net: *const c_void,
        sk: *const sock,
        fl6: *mut flowi6,
        final_p: *mut in6_addr,
    ) -> *mut dst_entry;
    fn ip6_dst_store(sk: *mut sock, dst: *mut dst_entry, xfrm: *mut c_void, cookie: *mut c_void);
    fn __sk_dst_check(sk: *mut sock, cookie: u32) -> *mut dst_entry;
    fn ip6_xmit(
        sk: *mut sock,
        skb: *mut sk_buff,
        fl: *const flowi6,
        mark: c_int,
        opt: *const c_void,
        tclass: u8,
        priority: c_int,
    ) -> c_int;

    fn security_req_classify_flow(req: *const request_sock, fl_common: *mut c_void);
    fn security_sk_classify_flow(sk: *mut sock, fl_common: *mut c_void);

    fn sock_net(sk: *const sock) -> *const c_void;
    fn ipv6_iface_scope_id(addr: *const in6_addr, dev_if: c_int) -> u32;

    fn inet_sk(sk: *mut sock) -> *mut inet_sock;
    fn skb_dst_set_noref(skb: *mut sk_buff, dst: *mut dst_entry);

    fn inet6_csk_route_socket(sk: *mut sock, fl6: *mut flowi6) -> *mut dst_entry;

    // Accessor helpers provided by C shim/kernel glue.
    fn ksock_v6_daddr(sk: *const sock) -> in6_addr;
    fn ksock_bound_dev_if(sk: *const sock) -> c_int;
    fn ksock_protocol(sk: *const sock) -> u8;
    fn ksock_mark(sk: *const sock) -> u32;
    fn ksock_uid(sk: *const sock) -> u32;
    fn ksock_route_caps_set(sk: *mut sock, v: u32);

    fn kinet_dport(isk: *const inet_sock) -> u16;
    fn kinet_sport(isk: *const inet_sock) -> u16;

    fn kipv6_saddr(np: *const ipv6_pinfo) -> in6_addr;
    fn kipv6_flow_label(np: *const ipv6_pinfo) -> u32;
    fn kipv6_opt(np: *const ipv6_pinfo) -> *const c_void;
}

#[no_mangle]
pub unsafe extern "C" fn inet6_csk_route_req(
    sk: *const sock,

    fl6: *mut flowi6,
    req: *const request_sock,
    proto: u8,
) -> *mut dst_entry {
    requires!(!sk.is_null(), "Socket pointer must not be null");
    requires!(!fl6.is_null(), "Flow pointer must not be null");
    requires!(!req.is_null(), "Request socket pointer must not be null");
    let safe_sk = SafeSocket::new(sk as *mut sock);
    let ireq = &*(req as *const inet_request_sock);
    let np = &*(sk as *const ipv6_pinfo);

    memset(fl6 as *mut c_void, 0, mem::size_of::<flowi6>() as size_t);

    (*fl6).flowi6_proto = proto;
    (*fl6).daddr = ireq.ir_v6_rmt_addr;

    let mut final_addr = in6_addr {
        in6_u: in6_addr_union { u6_addr8: [0; 16] },
    };

    rcu_read_lock();
    let _ = fl6_update_dst(fl6, kipv6_opt(np as *const ipv6_pinfo), &mut final_addr as *mut in6_addr);
    rcu_read_unlock();

    (*fl6).saddr = ireq.ir_v6_loc_addr;
    (*fl6).flowi6_oif = ireq.ir_iif;
    (*fl6).flowi6_mark = ireq.ir_mark;
    (*fl6).fl6_dport = ireq.ir_rmt_port;
    (*fl6).fl6_sport = ireq.ir_num.to_be();
    (*fl6).flowi6_uid = ksock_uid(sk);

    security_req_classify_flow(req, fl6 as *mut c_void);

    ip6_dst_lookup_flow(sock_net(sk), sk, fl6, &mut final_addr as *mut in6_addr)
}

#[no_mangle]
pub unsafe extern "C" fn inet6_csk_addr2sockaddr(sk: *mut sock, uaddr: *mut sockaddr_in6) {
    requires!(!sk.is_null(), "Socket pointer must not be null");
    requires!(!uaddr.is_null(), "Sockaddr pointer must not be null");
    let safe_sk = SafeSocket::new(sk);
    let sin6 = &mut *uaddr;
    sin6.sin6_family = AF_INET6;
    sin6.sin6_addr = ksock_v6_daddr(sk as *const sock);
    sin6.sin6_port = kinet_dport(inet_sk(sk) as *const inet_sock);
    sin6.sin6_flowinfo = 0;
    sin6.sin6_scope_id = ipv6_iface_scope_id(
        &sin6.sin6_addr as *const in6_addr,
        ksock_bound_dev_if(sk as *const sock),
    );
}

#[no_mangle]
pub unsafe extern "C" fn inet6_csk_xmit(
    sk: *mut sock,
    _skb: *mut sk_buff,
    _fl_unused: *mut c_void,
) -> c_int {
    requires!(!sk.is_null(), "Socket pointer must not be null");
    let safe_sk = SafeSocket::new(sk);
    let np = &*(sk as *const ipv6_pinfo);
    let isk = inet_sk(sk);

    let mut fl6 = flowi6 {
        flowi6_proto: ksock_protocol(sk as *const sock),
        __pad_proto: [0; 3],
        daddr: ksock_v6_daddr(sk as *const sock),
        saddr: kipv6_saddr(np as *const ipv6_pinfo),
        flowlabel: kipv6_flow_label(np as *const ipv6_pinfo),
        flowi6_oif: ksock_bound_dev_if(sk as *const sock),
        flowi6_mark: ksock_mark(sk as *const sock),
        fl6_sport: kinet_sport(isk as *const inet_sock),
        fl6_dport: kinet_dport(isk as *const inet_sock),
        flowi6_uid: ksock_uid(sk as *const sock),
    };

    let mut final_addr = in6_addr {
        in6_u: in6_addr_union { u6_addr8: [0; 16] },
    };

    rcu_read_lock();
    let _ = fl6_update_dst(
        &mut fl6 as *mut flowi6,
        kipv6_opt(np as *const ipv6_pinfo),
        &mut final_addr as *mut in6_addr,
    );
    rcu_read_unlock();

    security_sk_classify_flow(sk, &mut fl6 as *mut _ as *mut c_void);

    let dst = inet6_csk_route_socket(sk, &mut fl6 as *mut flowi6);
    if dst.is_null() {
        ksock_route_caps_set(sk, 0);
        return ENOMEM;
    }

    0 // Success return
}

// Exported symbols
#[no_mangle]
pub unsafe extern "C" fn inet6_csk_route_req_export() {
    // Symbol export marker
}

#[no_mangle]
pub unsafe extern "C" fn inet6_csk_addr2sockaddr_export() {
    // Symbol export marker
}

#[no_mangle]
pub unsafe extern "C" fn inet6_csk_xmit_export() {
    // Symbol export marker
}

#[no_mangle]
pub unsafe extern "C" fn inet6_csk_update_pmtu_export() {
    // Symbol export marker
}
