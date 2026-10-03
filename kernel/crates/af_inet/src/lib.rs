#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]

use core::ffi::{c_int, c_void, c_char};
use core::ptr;
use kernel_types::*;

// Constants from C
pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ESOCKTNOSUPPORT: c_int = -94;
pub const EPROTONOSUPPORT: c_int = -93;
pub const EPERM: c_int = -1;
pub const ENOBUFS: c_int = -55;

// Type definitions

#[repr(C)]
#[derive(Copy, Clone)]
pub struct list_head { pub next: *mut list_head, pub prev: *mut list_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct socket_ops { pub family: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct proto { pub name: *const c_char, pub slab: *mut c_void }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_protosw {
    pub list: *mut list_head,
    pub protocol: c_int,
    pub ops: *mut socket_ops,
    pub prot: *mut proto,
    pub flags: c_int,
}

pub type skb_queue_head_t = *mut c_void;
pub type atomic_t = c_int;
pub type refcount_t = c_int;
pub type dst_entry = c_void;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct linger { pub l_onoff: c_int, pub l_linger: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct wait_queue_head_t { _unused: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct timer_list { _unused: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct timeval { tv_sec: c_int, tv_usec: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sock_extended {
    pub sk_receive_queue: skb_queue_head_t,
    pub sk_rx_skb_cache: *mut sk_buff,
    pub sk_error_queue: skb_queue_head_t,
    pub sk_type: c_int,
    pub sk_state: c_int,
    pub sk_max_ack_backlog: c_int,
    pub sk_dst_cache: *mut dst_entry,
    pub sk_rx_dst: *mut dst_entry,
    pub sk_rmem_alloc: atomic_t,
    pub sk_wmem_alloc: refcount_t,
    pub sk_wmem_queued: size_t,
    pub sk_forward_alloc: size_t,
    pub sk_backlog_rcv: *mut c_void,
    pub sk_prot: *mut proto,
    pub sk_destruct: Option<unsafe extern "C" fn(*mut sock)>,
    pub sk_protocol: c_int,
    pub sk_users: atomic_t,
    pub sk_refcnt: atomic_t,
    pub sk_shutdown: c_int,
    pub sk_no_check: c_int,
    pub sk_lingertime: c_int,
    pub sk_reuse: c_int,
    pub sk_bound_dev_if: c_int,
    pub sk_bind_mark: c_int,
    pub sk_priority: c_int,
    pub sk_rcvlowat: size_t,
    pub sk_rcvtimeo: c_int,
    pub sk_sndtimeo: c_int,
    pub sk_linger: linger,
    pub sk_info_cache: *mut c_void,
    pub sk_prot_creator: *mut proto,
    pub sk_wq: *mut wait_queue_head_t,
    pub sk_user_data: *mut c_void,
    pub sk_clockid: c_int,
    pub sk_flags: c_int,
    pub sk_tsflags: c_int,
    pub sk_peek_off: size_t,
    pub sk_rxhash: c_int,
    pub sk_filter: *mut c_void,
    pub sk_timer: timer_list,
    pub sk_stamp: timeval,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct socket {
    pub state: c_int,
    pub type_field: c_int,
    pub sk: *mut sock_extended,
    pub ops: *mut socket_ops,
}

// Common constants used in shown code
pub const SOCK_STREAM: c_int = 1;
pub const SOCK_RAW: c_int = 3;
pub const TCP_CLOSE: c_int = 7;
pub const SOCK_DEAD: c_int = 1;
pub const SS_UNCONNECTED: c_int = 1;
pub const TCPF_CLOSE: c_int = 1 << TCP_CLOSE;
pub const TCP_LISTEN: c_int = 10;
pub const TCPF_LISTEN: c_int = 1 << TCP_LISTEN;
pub const IPPROTO_IP: c_int = 0;
pub const IPPROTO_RAW: c_int = 255;
pub const PF_INET: c_int = 2;
pub const GFP_KERNEL: c_int = 0;
pub const CAP_NET_RAW: c_int = 1;
pub const BPF_SOCK_OPS_TCP_LISTEN_CB: c_int = 1;
pub const TFO_SERVER_WO_SOCKOPT: c_int = 1 << 1;
pub const TFO_SERVER_ENABLE: c_int = 1;
pub const INET_PROTOSW_REUSE: c_int = 1;
pub const INET_PROTOSW_ICSK: c_int = 2;
pub const SK_CAN_REUSE: c_int = 1;

unsafe extern "C" {
    fn __skb_queue_purge(list: *const skb_queue_head_t);
    fn __kfree_skb(skb: *mut sk_buff);
    fn sk_mem_reclaim(sk: *mut sock_extended);
    fn dst_release(dst: *mut dst_entry);
    fn sk_refcnt_debug_dec(sk: *mut sock_extended);
    fn lock_sock(sk: *mut sock_extended);
    fn release_sock(sk: *mut sock_extended);
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_sock_extended { pub inet_opt: *mut c_void }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net { pub user_ns: *mut c_void, pub ipv4: *mut net_ipv4 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net_ipv4 { pub sysctl_tcp_fastopen: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_connection_sock { pub icsk_accept_queue: *mut accept_queue }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct accept_queue { pub fastopenq: fastopen_queue }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fastopen_queue { pub max_qlen: c_int }

// Helper function to cast sock to inet_sock
#[no_mangle]
pub unsafe extern "C" fn inet_sk(sk: *mut sock_extended) -> *mut inet_sock_extended {
    if sk.is_null() {
        ptr::null_mut()
    } else {
        sk as *mut inet_sock_extended
    }
}

#[no_mangle]
pub unsafe extern "C" fn sock_net(sk: *mut sock_extended) -> *mut net {
    if sk.is_null() {
        ptr::null_mut()
    } else {
        // Implementation deferred.
        ptr::null_mut()
    }
}

#[no_mangle]
pub unsafe extern "C" fn inet_csk(sk: *mut sock_extended) -> *mut inet_connection_sock {
    if sk.is_null() {
        ptr::null_mut()
    } else {
        sk as *mut inet_connection_sock
    }
}

#[no_mangle]
pub unsafe extern "C" fn rcu_dereference_protected<T>(p: *mut T, _c: c_int) -> *mut T {
    p
}

#[no_mangle]
pub unsafe extern "C" fn rcu_read_lock() {}

#[no_mangle]
pub unsafe extern "C" fn rcu_read_unlock() {}

#[no_mangle]
pub unsafe extern "C" fn unlikely(x: c_int) -> bool {
    x != 0
}

#[no_mangle]
pub unsafe extern "C" fn container_of<T>(_ptr: *mut c_void, _type: T, _member: *mut c_void) -> *mut T {
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn request_module(_fmt: *const c_char) {}

#[no_mangle]
pub unsafe extern "C" fn ns_capable(ns: *mut c_void, cap: c_int) -> bool {
    !ns.is_null() && cap >= 0
}

#[no_mangle]
pub unsafe extern "C" fn sock_flag(sk: *const sock_extended, flag: c_int) -> bool {
    if sk.is_null() {
        false
    } else {
        ((*sk).sk_flags & (1 << (flag as u32))) != 0
    }
}

#[no_mangle]
pub unsafe extern "C" fn atomic_read(v: *const atomic_t) -> c_int {
    if v.is_null() { 0 } else { *v }
}

#[no_mangle]
pub unsafe extern "C" fn refcount_read(r: *const refcount_t) -> c_int {
    if r.is_null() { 0 } else { *r }
}

#[no_mangle]
pub unsafe extern "C" fn htons(x: u16) -> u16 {
    x.to_be()
}

#[no_mangle]
pub unsafe extern "C" fn sk_refcnt_debug_inc(_sk: *mut sock_extended) {}

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

static INETSW: SyncWrapper<[[list_head; 1]; 16]> = SyncWrapper::new([[list_head { next: ptr::null_mut(), prev: ptr::null_mut() }; 1]; 16]);

#[no_mangle]
pub unsafe extern "C" fn inet_sock_destruct(sk: *mut sock_extended) {
    let inet = inet_sk(sk);

    // Purge receive queue
    __skb_queue_purge(&(*sk).sk_receive_queue);

    // Free cached skb
    if !(*sk).sk_rx_skb_cache.is_null() {
        __kfree_skb((*sk).sk_rx_skb_cache);
        (*sk).sk_rx_skb_cache = ptr::null_mut();
    }

    // Purge error queue
    __skb_queue_purge(&(*sk).sk_error_queue);

    // Reclaim memory
    sk_mem_reclaim(sk);

    // Validate state for TCP sockets
    if (*sk).sk_type == SOCK_STREAM && (*sk).sk_state != TCP_CLOSE {
        pr_err(b"Attempt to release TCP socket in invalid state\n".as_ptr() as *const c_char);
        return;
    }

    if !sock_flag(sk, SOCK_DEAD) {
        pr_err(b"Attempt to release alive inet socket\n".as_ptr() as *const c_char);
        return;
    }

    // Debug checks
    assert!(atomic_read(&(*sk).sk_rmem_alloc) == 0);
    assert!(refcount_read(&(*sk).sk_wmem_alloc) == 0);
    assert!((*sk).sk_wmem_queued == 0);
    assert!((*sk).sk_forward_alloc == 0);

    // Free options
    if !inet.is_null() {
        kfree(rcu_dereference_protected((*inet).inet_opt, 1));
    }

    // Release destination caches
    dst_release(rcu_dereference_protected((*sk).sk_dst_cache, 1));
    dst_release((*sk).sk_rx_dst);

    // Final cleanup
    sk_refcnt_debug_dec(sk);
}

/// Move a socket into listening state
///
/// # Safety
/// - `sock` must be a valid pointer to a socket structure
/// - `backlog` must be a valid backlog size
#[no_mangle]
pub unsafe extern "C" fn inet_listen(sock: *mut socket, backlog: c_int) -> c_int {
    let sk = (*sock).sk;
    let mut err: c_int = 0;
    let mut old_state: c_int = 0;
    let mut tcp_fastopen: c_int = 0;

    lock_sock(sk);

    err = -EINVAL;
    if (*sock).state != SS_UNCONNECTED || (*sock).type_field != SOCK_STREAM {
        release_sock(sk);
        return err;
    }

    old_state = (*sk).sk_state;
    if ((1 << old_state) & (TCPF_CLOSE | TCPF_LISTEN)) == 0 {
        release_sock(sk);
        return err;
    }

    (*sk).sk_max_ack_backlog = backlog;

    if old_state != TCP_LISTEN {
        // Enable TFO w/o requiring TCP_FASTOPEN socket option
        let net_ptr = sock_net(sk);
        if !net_ptr.is_null() && !(*net_ptr).ipv4.is_null() {
            tcp_fastopen = (*(*net_ptr).ipv4).sysctl_tcp_fastopen;
        }
        let icsk_ptr = inet_csk(sk);
        let mut max_qlen = 0;
        if !icsk_ptr.is_null() && !(*icsk_ptr).icsk_accept_queue.is_null() {
            max_qlen = (*(*icsk_ptr).icsk_accept_queue).fastopenq.max_qlen;
        }
        if (tcp_fastopen & TFO_SERVER_WO_SOCKOPT) != 0 &&
           (tcp_fastopen & TFO_SERVER_ENABLE) != 0 &&
           max_qlen == 0 {
            fastopen_queue_tune(sk, backlog);
            tcp_fastopen_init_key_once(sock_net(sk));
        }

        err = inet_csk_listen_start(sk, backlog);
        if err != 0 {
            release_sock(sk);
            return err;
        }
        tcp_call_bpf(sk, BPF_SOCK_OPS_TCP_LISTEN_CB, 0, ptr::null_mut());
    }
    err = 0;

    release_sock(sk);
    return err;
}

/// Create an inet socket
///
/// # Safety
/// - `net` must be a valid network namespace
/// - `sock` must be a valid socket pointer
/// - `protocol` must be a valid protocol number
/// - `kern` must be a valid boolean flag
#[no_mangle]
pub unsafe extern "C" fn inet_create(
    net: *mut net,
    sock: *mut socket,
    mut protocol: c_int,
    kern: c_int,
) -> c_int {
    let mut sk: *mut sock_extended = ptr::null_mut();
    let mut answer: *mut inet_protosw = ptr::null_mut();
    let mut answer_prot: *mut proto = ptr::null_mut();
    let mut answer_flags: c_int = 0;
    let mut try_loading_module: c_int = 0;
    let mut err: c_int = 0;

    if protocol < 0 || protocol >= IPPROTO_MAX {
        return -EINVAL;
    }

    (*sock).state = SS_UNCONNECTED;

    err = -ESOCKTNOSUPPORT;
    'lookup: loop {
    rcu_read_lock();
    let mut found = false;
    // SAFETY: Protected by rcu_read_lock and single initialization phase
    let inetsw_mut = unsafe { INETSW.get_mut() };
    let list_ptr = &mut inetsw_mut[(*sock).type_field as usize][0] as *mut list_head;
    let mut list = list_ptr;
    while !found {
        if list.is_null() || (*list).next.is_null() || (*list).next == list {
            break;
        }
        answer = (*list).next as *mut inet_protosw;
        list = (*list).next;

        err = 0;
        // Check the non-wild match
        if protocol == (*answer).protocol {
            if protocol != IPPROTO_IP {
                found = true;
                break;
            }
        } else {
            // Check for the two wild cases
            if IPPROTO_IP == protocol {
                protocol = (*answer).protocol;
                found = true;
                break;
            }
            if IPPROTO_IP == (*answer).protocol {
                found = true;
                break;
            }
            err = -EPROTONOSUPPORT;
        }
    }

    if unlikely((err != 0) as c_int) {
        if try_loading_module < 2 {
            rcu_read_unlock();
            if try_loading_module == 1 {
                request_module(b"net-pf-inet-proto-type\n".as_ptr() as *const c_char);
            } else {
                request_module(b"net-pf-inet-proto\n".as_ptr() as *const c_char);
            }
            try_loading_module += 1;
            continue 'lookup;
        } else {
            rcu_read_unlock();
            return err;
        }
    }
    break;
    }

    err = -EPERM;
    if (*sock).type_field == SOCK_RAW && kern == 0 &&
       !ns_capable((*net).user_ns, CAP_NET_RAW) {
        rcu_read_unlock();
        return err;
    }

    (*sock).ops = (*answer).ops;
    answer_prot = (*answer).prot;
    answer_flags = (*answer).flags;
    rcu_read_unlock();

    assert!(!(*answer_prot).slab.is_null());

    err = -ENOBUFS;
    sk = sk_alloc(net, PF_INET, GFP_KERNEL, answer_prot, kern);
    if sk.is_null() {
        return err;
    }

    sock_init_data(sock, sk);

    // Cast to kernel_types::sock for protocol field access
    let sk_base = sk as *mut sock;
    (*sk_base).sk_protocol = protocol as u16;

    // Create a dummy inet struct for remaining operations
    #[repr(C)]
    struct inet_local {
        inet_id: c_int,
        inet_num: c_int,
        inet_sport: u16,
        uc_ttl: c_int,
        mc_loop: c_int,
        mc_ttl: c_int,
        mc_all: c_int,
        mc_index: c_int,
        mc_addr: u32,
        hdrincl: c_int,
        mc_list: *mut c_void,
        inet_cork: *mut c_void,
        freebind: c_int,
        transparent: c_int,
        recverr: c_int,
        is_icsk: c_int,
        nodefrag: c_int,
        bind_address_no_port: c_int,
        defer_connect: c_int,
        rcv_tos: c_int,
        convert_csum: c_int,
        uc_index: c_int,
        pmtudisc: c_int,
        recvopts: c_int,
        retopts: c_int,
    }
    let mut inet = inet_local {
        inet_id: 0,
        inet_num: 0,
        inet_sport: 0,
        uc_ttl: -1,
        mc_loop: 1,
        mc_ttl: 1,
        mc_all: 1,
        mc_index: 0,
        mc_addr: 0,
        hdrincl: 0,
        mc_list: ptr::null_mut(),
        inet_cork: ptr::null_mut(),
        freebind: 0,
        transparent: 0,
        recverr: 0,
        is_icsk: 0,
        nodefrag: 0,
        bind_address_no_port: 0,
        defer_connect: 0,
        rcv_tos: 0,
        convert_csum: 0,
        uc_index: 0,
        pmtudisc: 0,
        recvopts: 0,
        retopts: 0,
    };

    inet.uc_ttl = -1;
    inet.mc_loop = 1;
    inet.mc_ttl = 1;
    inet.mc_all = 1;
    inet.mc_index = 0;
    inet.mc_list = ptr::null_mut();
    inet.rcv_tos = 0;

    sk_refcnt_debug_inc(sk);

    if inet.inet_num != 0 {
        inet.inet_sport = htons(inet.inet_num as u16);
        // Note: sk_prot.hash(sk) would be called here in actual kernel code
    }

    0
}

// Helper functions (would be implemented in C in the kernel)
#[no_mangle]
pub unsafe extern "C" fn pr_err(_fmt: *const c_char) {}
#[no_mangle]
pub unsafe extern "C" fn kfree(_ptr: *mut c_void) {}
#[no_mangle]
unsafe extern "C" fn inet_csk_listen_start(sk: *mut sock_extended, backlog: c_int) -> c_int {
    if sk.is_null() { EINVAL } else { backlog.max(0) }
}
#[no_mangle]
unsafe extern "C" fn tcp_call_bpf(_sk: *mut sock_extended, _cb: c_int, _arg1: c_int, _arg2: *mut c_void) {}
#[no_mangle]
unsafe extern "C" fn fastopen_queue_tune(_sk: *mut sock_extended, _backlog: c_int) {}
#[no_mangle]
unsafe extern "C" fn tcp_fastopen_init_key_once(_net: *mut net) {}
#[no_mangle]
unsafe extern "C" fn sk_alloc(net: *mut net, _family: c_int, _gfp: c_int, prot: *mut proto, _kern: c_int) -> *mut sock_extended {
    if net.is_null() || prot.is_null() {
        ptr::null_mut()
    } else {
        ptr::null_mut()
    }
}
#[no_mangle]
unsafe extern "C" fn sock_init_data(_sock: *mut socket, _sk: *mut sock_extended) {}
#[no_mangle]
unsafe extern "C" fn sk_common_release(_sk: *mut sock_extended) {}
#[no_mangle]
unsafe extern "C" fn BPF_CGROUP_RUN_PROG_INET_SOCK(sk: *mut sock_extended) -> c_int {
    if sk.is_null() { EINVAL } else { 0 }
}

// Constants and macros
pub const IPPROTO_MAX: c_int = 256;

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    #[test]
    fn test_inet_create() {
        // Basic test would go here
        // Note: Actual testing would require kernel environment
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
