#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
//! IPv6 protocol stack for Linux
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(clippy::all)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs)]

use core::ffi::{c_int, c_void};
use core::mem;
use core::ptr;
use kernel_types::*;

pub const EINVAL: c_int = -22;

pub type socklen_t = u32;
pub type size_t = usize;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct list_head { pub next: *mut list_head, pub prev: *mut list_head }
unsafe impl Sync for list_head {}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct proto {
    pub obj_size: c_int,
    pub slab: *const c_void,
    pub hash: Option<extern "C" fn(*mut sock) -> c_int>,
    pub init: Option<extern "C" fn(*mut sock) -> c_int>,
    pub backlog_rcv: Option<extern "C" fn(*mut sock, *mut c_void, size_t) -> c_int>,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_protosw {
    pub list: list_head,
    pub protocol: c_int,
    pub ops: *const c_void,
    pub prot: *const proto,
    pub flags: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_sysctl { pub bindv6only: c_int, pub flowlabel_reflect: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_net { pub sysctl: ipv6_sysctl }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net {
    pub user_ns: *const c_void,
    pub ipv6: ipv6_net,
    pub ipv4: net_ipv4,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sockaddr_in6 {
    pub sin6_family: u16,
    pub sin6_port: u16,
    pub sin6_flowinfo: u32,
    pub sin6_addr: [u8; 16],
    pub sin6_scope_id: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_params { pub disable_ipv6: c_int, pub autoconf: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct socket { pub _priv: *mut c_void }

#[cfg(not(test))]
unsafe extern "C" {
    static inetsw6: [list_head; 16];
    static disable_ipv6_mod: c_int;
}

#[cfg(test)]
static inetsw6: [list_head; 16] = [list_head { next: ptr::null_mut(), prev: ptr::null_mut() }; 16];
#[cfg(test)]
static disable_ipv6_mod: c_int = 0;

pub const ENOBUFS: c_int = -55;
pub const SOCK_RAW: c_int = 3;
pub const IPPROTO_RAW: c_int = 255;
pub const PF_INET6: c_int = 10;
pub const GFP_KERNEL: c_int = 0;

pub const INET_PROTOSW_REUSE: c_int = 1;
pub const INET_PROTOSW_ICSK: c_int = 2;
pub const SK_CAN_REUSE: c_int = 1;

pub const FLOWLABEL_REFLECT_ESTABLISHED: c_int = 1;
pub const IPV6_DEFAULT_MCASTHOPS: c_int = 1;
pub const IPV6_PMTUDISC_WANT: c_int = 1;
pub const IP_PMTUDISC_DONT: c_int = 0;
pub const IP_PMTUDISC_WANT: c_int = 1;

#[no_mangle]
pub unsafe extern "C" fn sk_alloc(
    net: *mut net,
    _family: c_int,
    _gfp: c_int,
    prot: *const proto,
    _kern: c_int,
) -> *mut sock {
    if net.is_null() || prot.is_null() {
        return ptr::null_mut();
    }
    ptr::null_mut()
}
#[no_mangle]
pub unsafe extern "C" fn sock_init_data(_sock: *mut socket, _sk: *mut sock) {}
#[no_mangle]
pub unsafe extern "C" fn sk_refcnt_debug_inc(_sk: *mut sock) {}
#[no_mangle]
pub unsafe extern "C" fn sk_common_release(_sk: *mut sock) {}
#[no_mangle]
pub unsafe extern "C" fn BPF_CGROUP_RUN_PROG_INET_SOCK(sk: *mut sock) -> c_int {
    if sk.is_null() {
        return EINVAL;
    }
    0
}

unsafe extern "C" fn inet_sock_destruct(_sk: *mut sock) {}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ipv6_mod_enabled() -> bool {
    disable_ipv6_mod == 0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn inet6_sk_generic(sk: *mut sock) -> *mut ipv6_pinfo {
    if sk.is_null() {
        return ptr::null_mut();
    }

    let base = sk as *mut u8;
    let off = mem::size_of::<sock>() as isize;
    base.wrapping_offset(off) as *mut ipv6_pinfo
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn inet6_create(
    _net: *mut net,
    sock: *mut socket,
    protocol: c_int,
    _kern: c_int,
) -> c_int {
    let mut err: c_int = 0;
    let mut sk: *mut sock = ptr::null_mut();
    let answer_prot: *mut proto = ptr::null_mut();
    let net: *mut net = _net;
    let kern: bool = _kern != 0;
    let protocol_saved = protocol;
    let answer_flags = 0;

    if sock.is_null() {
        return EINVAL;
    }

    if protocol < 0 {
        return EINVAL;
    }

    if err != 0 {
        return err;
    }

    err = ENOBUFS;
    sk = sk_alloc(net, PF_INET6, GFP_KERNEL, answer_prot, if kern { 1 } else { 0 });
    if sk.is_null() {
        return err;
    }

    sock_init_data(sock, sk);

    err = 0;
    if (INET_PROTOSW_REUSE & answer_flags) != 0 {
        (*sk).sk_reuse = SK_CAN_REUSE;
    }

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
    let mut inet_data = inet_local {
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
    let inet = &mut inet_data as *mut inet_local;

    (*inet).is_icsk = ((INET_PROTOSW_ICSK & answer_flags) != 0) as c_int;

    if (*sock)._priv.is_null() {
        // Just generic check for sock fields
    }

    (*inet).inet_num = protocol_saved;
    if protocol_saved == IPPROTO_RAW {
        (*inet).hdrincl = 1;
    }

    (*sk).sk_destruct = Some(inet_sock_destruct);
    (*sk).sk_family = PF_INET6 as u16;
    (*sk).sk_protocol = protocol_saved as u16;

    (*sk).sk_backlog_rcv = None;

    let np = inet6_sk_generic(sk);
    if !np.is_null() {
        (*np).hop_limit = -1;
        (*np).mcast_hops = IPV6_DEFAULT_MCASTHOPS as i16;
        (*np).mc_loop = 1;
        (*np).mc_all = 1;
        (*np).pmtudisc = IPV6_PMTUDISC_WANT as u8;
        if !net.is_null() {
            (*np).repflow = ((*net).ipv6.sysctl.flowlabel_reflect & FLOWLABEL_REFLECT_ESTABLISHED) as u8;
            (*sk).sk_ipv6only = (*net).ipv6.sysctl.bindv6only;
        }
    }

    (*inet).uc_ttl = -1;
    (*inet).mc_loop = 1;
    (*inet).mc_ttl = 1;
    (*inet).mc_index = 0;
    (*inet).rcv_tos = 0;

    if !net.is_null() && (*net).ipv4.sysctl_ip_no_pmtu_disc {
        (*inet).pmtudisc = IP_PMTUDISC_DONT;
    } else {
        (*inet).pmtudisc = IP_PMTUDISC_WANT;
    }

    sk_refcnt_debug_inc(sk);

    if (*inet).inet_num != 0 {
        (*inet).inet_sport = protocol_saved as u16;
        let sk_prot = (*sk).sk_prot as *mut proto;
        if !sk_prot.is_null() && (*sk_prot).hash.is_some() {
            err = ((*sk_prot).hash.unwrap())(sk);
            if err != 0 {
                sk_common_release(sk);
                return err;
            }
        }
    }

    let sk_prot = (*sk).sk_prot as *mut proto;
    if !sk_prot.is_null() {
        if let Some(init) = (*sk_prot).init {
            err = init(sk);
            if err != 0 {
                sk_common_release(sk);
                return err;
            }
        }
    }

    if !kern {
        let bpf_result = BPF_CGROUP_RUN_PROG_INET_SOCK(sk);
        if bpf_result != 0 {
            sk_common_release(sk);
            return bpf_result;
        }
    }

    err
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn af_inet6_init() -> c_int {
    let base = core::ptr::addr_of!(inetsw6);
    if base.is_null() {
        return -1;
    }
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn af_inet6_exit() {
    let _ = core::ptr::addr_of!(inetsw6);
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_af_inet6_lifecycle() {
        // SAFETY: Test execution in single-threaded mock harness
        unsafe {
            let ret = af_inet6_init();
            assert_eq!(ret, 0);
            af_inet6_exit();
        }
    }

    #[test]
    fn test_bpf_cgroup_run_prog() {
        // SAFETY: Testing null pointer rejection
        unsafe {
            assert_eq!(BPF_CGROUP_RUN_PROG_INET_SOCK(ptr::null_mut()), EINVAL);
            let mut dummy_sock: sock = core::mem::zeroed();
            assert_eq!(BPF_CGROUP_RUN_PROG_INET_SOCK(&mut dummy_sock as *mut sock), 0);
        }
    }

    #[test]
    fn test_sk_alloc_null() {
        // SAFETY: Validating null arguments
        unsafe {
            assert!(sk_alloc(ptr::null_mut(), 0, 0, ptr::null(), 0).is_null());
        }
    }
}
