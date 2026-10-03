#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

use core::{{mem, ptr}, ffi::c_int, panic::PanicInfo};

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

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOSYS: c_int = -38;
pub const AF_INET6: c_int = 10;
pub const IPPROTO_UDP: u8 = 17;
pub const TCP_ESTABLISHED: c_int = 1;
pub const MSG_ERRQUEUE: c_int = 0x2000;
pub const MSG_TRUNC: c_int = 0x0020;
pub const MSG_PEEK: c_int = 0x0002;
pub const ETH_P_IP: u16 = 0x0800;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct refcount_t { pub counter: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct list_head { pub next: *mut list_head, pub prev: *mut list_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub union in6_addr_kcompat {
    pub u6_addr32: [u32; 4],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct in6_addr { pub in6_u: in6_addr_kcompat }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct udp_hslot { pub head: list_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct udp_table { pub mask: u32, pub hash2: *mut udp_hslot }

// Implementation deferred.
static UDP_TABLE: SyncWrapper<udp_table> = SyncWrapper::new(udp_table {
    mask: 0,
    hash2: ptr::null_mut(),
});
static UDP6_EHASH_SECRET: SyncWrapper<u32> = SyncWrapper::new(0);
static UDP_IPV6_HASH_SECRET: SyncWrapper<u32> = SyncWrapper::new(0);

#[repr(C)]
pub struct net { _priv: [u8; 0] }

#[repr(C)]
pub struct sk_buff {
    pub dev: *mut c_void,
    pub protocol: u16,
    pub len: c_int,
    pub head: *mut c_void,
    pub data: *mut c_void,
    _priv: [u8; 0],
}

#[repr(C)]
pub struct ipv6hdr {
    pub saddr: in6_addr,
    pub daddr: in6_addr,
    _priv: [u8; 0],
}

#[repr(C)]
pub struct udp_mib { _priv: [u8; 0] }

#[repr(C)]
pub struct ipv6_pinfo { pub rxpmtu: c_int, pub rxopt: ipv6_rxopt }

#[repr(C)]
pub struct ipv6_rxopt { pub bits: ipv6_rxopt_bits }

#[repr(C)]
pub struct ipv6_rxopt_bits { pub rxpmtu: c_int }

#[repr(C)]
pub struct udp_skb_cb { pub partial_cov: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct msg_iter { _priv: [u8; 0] }

#[repr(C)]
pub struct msghdr { pub msg_flags: c_int, pub msg_iter: msg_iter }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_sock { pub inet_dport: u16 }

#[repr(C)]
pub struct sock {
    pub sk_v6_rcv_saddr: in6_addr,
    pub sk_v6_daddr: in6_addr,
    pub sk_family: c_int,
    pub udp_port_hash: u16,
    pub udp_portaddr_hash: u32,
    pub inet_num: u16,
    pub sk_bound_dev_if: c_int,
    pub sk_incoming_cpu: c_int,
    pub inet_sk: inet_sock,
    pub sk_state: c_int,
    pub sk_reuseport: c_int,
    pub ipv6_pinfo: ipv6_pinfo,
    pub sk_refcnt: refcount_t,
}

unsafe extern "C" {
    fn net_get_random_once(buf: *mut u32, size: usize);
    fn ipv6_portaddr_hash(net: *const net, addr: *const in6_addr, port: u16) -> u32;
    fn __inet6_ehashfn(lhash: u32, lport: u16, fhash: u32, fport: u16, secret: u32) -> u32;
    fn net_hash_mix(net: *const net) -> u32;

    fn sock_net(sk: *const sock) -> *const net;
    fn udp_lib_get_port(sk: *mut sock, snum: u16, hash2_nulladdr: u32) -> c_int;
    fn udp_lib_rehash(sk: *mut sock, new_hash: u32);

    fn net_eq(a: *const net, b: *const net) -> bool;
    fn ipv6_addr_equal(a1: *const in6_addr, a2: *const in6_addr) -> bool;
    fn ipv6_addr_any(a: *const in6_addr) -> bool;
    fn udp_sk_bound_dev_eq(net: *const net, bound_dev_if: c_int, dif: c_int, sdif: c_int) -> bool;
    fn raw_smp_processor_id() -> c_int;
    fn reuseport_has_conns(sk: *const sock, closed: bool) -> bool;
    fn bpf_sk_lookup_run_v6(net: *const net, protocol: c_int, saddr: *const in6_addr,
                            sport: u16, daddr: *const in6_addr, dport: u16,
                            ifindex: c_int, skptr: *mut *mut sock) -> c_int;
    fn ntohs(val: u16) -> u16;
    fn htons(val: u16) -> u16;
    fn static_branch_unlikely(key: *const c_int) -> c_int;
    fn ipv6_hdr(skb: *const sk_buff) -> *const ipv6hdr;
    fn dev_net(dev: *const c_void) -> *const net;
    fn inet6_iif(skb: *const sk_buff) -> c_int;
    fn inet6_sdif(skb: *const sk_buff) -> c_int;
    fn udp_skb_csum_unnecessary(skb: *const sk_buff) -> c_int;
    fn ipv6_recv_error(sk: *mut sock, msg: *mut c_void, len: usize, addr_len: *mut c_int) -> c_int;
    fn ipv6_recv_rxpmtu(sk: *mut sock, msg: *mut c_void, len: usize, addr_len: *mut c_int) -> c_int;
    fn sk_peek_offset(sk: *mut sock, flags: c_int) -> c_int;
    fn __skb_recv_udp(sk: *mut sock, flags: c_int, noblock: c_int, off: *mut c_int, err: *mut c_int) -> *mut sk_buff;
    fn __UDPX_MIB(sk: *mut sock, is_udp4: c_int) -> *mut udp_mib;
    fn UDP_SKB_CB(skb: *mut sk_buff) -> *mut udp_skb_cb;
    fn __udp_lib_checksum_complete(skb: *mut sk_buff) -> c_int;
    fn udp_skb_is_linear(skb: *mut sk_buff) -> c_int;
    fn copy_linear_skb(skb: *mut sk_buff, len: usize, off: c_int, iter: msg_iter) -> c_int;
    fn skb_copy_datagram(skb: *mut sk_buff, off: c_int, iter: msg_iter, len: usize) -> c_int;
    fn inet6_is_jumbogram(skb: *mut sk_buff) -> c_int;
    fn udp_skb_len(skb: *mut sk_buff) -> c_int;
    fn refcount_inc_not_zero(refcnt: *const refcount_t) -> c_int;
}

// Implementation deferred.
static BPF_SK_LOOKUP_ENABLED: c_int = 0;

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}

#[no_mangle]
pub static in6addr_any: in6_addr = in6_addr {
    in6_u: in6_addr_kcompat {
        u6_addr32: [0, 0, 0, 0],
    },
};

#[no_mangle]
pub unsafe extern "C" fn udp6_ehashfn(
    net: *const net,
    laddr: *const in6_addr,
    lport: u16,
    faddr: *const in6_addr,
    fport: u16,
) -> u32 {
    net_get_random_once(UDP6_EHASH_SECRET.get_mut(), mem::size_of::<u32>());
    net_get_random_once(UDP_IPV6_HASH_SECRET.get_mut(), mem::size_of::<u32>());

    let lhash = (*laddr).in6_u.u6_addr32[3];
    let fhash = ipv6_portaddr_hash(net, faddr, 0);

    __inet6_ehashfn(
        lhash,
        lport,
        fhash,
        fport,
        (*UDP_IPV6_HASH_SECRET.get_mut()).wrapping_add(net_hash_mix(net)),
    )
}

#[no_mangle]
pub unsafe extern "C" fn udp_v6_get_port(sk: *mut sock, snum: u16) -> c_int {
    let hash2_nulladdr = ipv6_portaddr_hash(sock_net(sk), &in6addr_any, snum);
    let hash2_partial = ipv6_portaddr_hash(sock_net(sk), &(*sk).sk_v6_rcv_saddr, 0);

    (*sk).udp_portaddr_hash = hash2_partial;
    udp_lib_get_port(sk, snum, hash2_nulladdr)
}

#[no_mangle]
pub unsafe extern "C" fn udp_v6_rehash(sk: *mut sock) {
    let new_hash = ipv6_portaddr_hash(sock_net(sk), &(*sk).sk_v6_rcv_saddr, (*sk).inet_num);
    udp_lib_rehash(sk, new_hash);
}

#[no_mangle]
pub unsafe extern "C" fn compute_score(
    sk: *mut sock,
    net: *const net,
    saddr: *const in6_addr,
    sport: u16,
    daddr: *const in6_addr,
    hnum: u16,
    dif: c_int,
    sdif: c_int,
) -> c_int {
    if !net_eq(sock_net(sk), net) || (*sk).udp_port_hash != hnum || (*sk).sk_family != AF_INET6 {
        return -1;
    }

    if !ipv6_addr_equal(&(*sk).sk_v6_rcv_saddr, daddr) {
        return -1;
    }

    let mut score = 0;
    let inet = &(*sk).inet_sk;

    if inet.inet_dport != 0 {
        if inet.inet_dport != sport {
            return -1;
        }
        score += 1;
    }

    if !ipv6_addr_any(&(*sk).sk_v6_daddr) {
        if !ipv6_addr_equal(&(*sk).sk_v6_daddr, saddr) {
            return -1;
        }
        score += 1;
    }

    if !udp_sk_bound_dev_eq(net, (*sk).sk_bound_dev_if, dif, sdif) {
        return -1;
    }
    score += 1;

    if (*sk).sk_incoming_cpu == raw_smp_processor_id() {
        score += 1;
    }

    score
}

#[no_mangle]
pub unsafe extern "C" fn lookup_reuseport(
    _net: *const net,
    _sk: *mut sock,
    _skb: *mut sk_buff,
    _saddr: *const in6_addr,
    _sport: u16,
    _daddr: *const in6_addr,
    _hnum: u16,
) -> *mut sock {
    // Implementation deferred.
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn udp6_lib_lookup2(
    net: *const net,
    saddr: *const in6_addr,
    sport: u16,
    daddr: *const in6_addr,
    hnum: u16,
    dif: c_int,
    sdif: c_int,
    hslot2: *mut udp_hslot,
    skb: *mut sk_buff,
) -> *mut sock {
    let mut result: *mut sock = ptr::null_mut();
    let mut badness: c_int = -1;

    let mut sk = (*hslot2).head.next;
    while !sk.is_null() && !core::ptr::eq(sk, &raw const (*hslot2).head as *mut _) {
        let score = compute_score(sk as *mut sock, net, saddr, sport, daddr, hnum, dif, sdif);
        if score > badness {
            let reuse_sk = lookup_reuseport(net, sk as *mut sock, skb, saddr, sport, daddr, hnum);
            if !reuse_sk.is_null() && !reuseport_has_conns(sk as *mut sock, false) {
                return reuse_sk;
            }

            result = if !reuse_sk.is_null() { reuse_sk } else { sk as *mut sock };
            badness = score;
        }
        sk = (*sk).next;
    }

    result
}

#[no_mangle]
pub unsafe extern "C" fn udp6_lookup_run_bpf(
    net: *const net,
    udptable: *mut udp_table,
    skb: *mut sk_buff,
    saddr: *const in6_addr,
    sport: u16,
    daddr: *const in6_addr,
    hnum: u16,
) -> *mut sock {
    if !core::ptr::eq(udptable, UDP_TABLE.get_mut() as *mut _) {
        return ptr::null_mut();
    }

    let mut sk: *mut sock = ptr::null_mut();
    let no_reuseport = bpf_sk_lookup_run_v6(net, IPPROTO_UDP as c_int, saddr, sport, daddr, hnum, 0, &mut sk);

    if no_reuseport != 0 || sk.is_null() {
        return sk;
    }

    let reuse_sk = lookup_reuseport(net, sk, skb, saddr, sport, daddr, hnum);
    if !reuse_sk.is_null() {
        sk = reuse_sk;
    }
    sk
}

#[no_mangle]
pub unsafe extern "C" fn __udp6_lib_lookup(
    net: *const net,
    saddr: *const in6_addr,
    sport: u16,
    daddr: *const in6_addr,
    dport: u16,
    dif: c_int,
    sdif: c_int,
    udptable: *mut udp_table,
    skb: *mut sk_buff,
) -> *mut sock {
    let hnum = ntohs(dport);
    let hash2 = ipv6_portaddr_hash(net, daddr, hnum);
    let slot2 = hash2 & (*udptable).mask;
    let hslot2 = (*udptable).hash2.add(slot2 as usize);

    let mut result = udp6_lib_lookup2(net, saddr, sport, daddr, hnum, dif, sdif, hslot2, skb);
    if !result.is_null() && (*result).sk_state == TCP_ESTABLISHED {
        return result;
    }

    if static_branch_unlikely(&BPF_SK_LOOKUP_ENABLED) != 0 {
        let sk = udp6_lookup_run_bpf(net, udptable, skb, saddr, sport, daddr, hnum);
        if !sk.is_null() {
            return sk;
        }
    }

    if result.is_null() {
        let hash2 = ipv6_portaddr_hash(net, &in6addr_any, hnum);
        let slot2 = hash2 & (*udptable).mask;
        let hslot2 = (*udptable).hash2.add(slot2 as usize);
        result = udp6_lib_lookup2(net, saddr, sport, &in6addr_any, hnum, dif, sdif, hslot2, skb);
    }

    result
}

#[no_mangle]
pub unsafe extern "C" fn __udp6_lib_lookup_skb(
    skb: *mut sk_buff,
    sport: u16,
    dport: u16,
    udptable: *mut udp_table,
) -> *mut sock {
    let iph = ipv6_hdr(skb);
    __udp6_lib_lookup(dev_net((*skb).dev), &(*iph).saddr, sport, &(*iph).daddr, dport, inet6_iif(skb), inet6_sdif(skb), udptable, skb)
}

#[no_mangle]
pub unsafe extern "C" fn udp6_lib_lookup_skb(
    skb: *const sk_buff,
    sport: u16,
    dport: u16,
) -> *mut sock {
    let iph = ipv6_hdr(skb as *mut sk_buff);
    __udp6_lib_lookup(dev_net((*skb).dev), &(*iph).saddr, sport, &(*iph).daddr, dport, inet6_iif(skb as *mut sk_buff), inet6_sdif(skb as *mut sk_buff), UDP_TABLE.get_mut() as *mut _, ptr::null_mut())
}

#[no_mangle]
pub unsafe extern "C" fn udp6_lib_lookup(
    net: *const net,
    saddr: *const in6_addr,
    sport: u16,
    daddr: *const in6_addr,
    dport: u16,
    dif: c_int,
) -> *mut sock {
    let sk = __udp6_lib_lookup(net, saddr, sport, daddr, dport, dif, 0, UDP_TABLE.get_mut() as *mut _, ptr::null_mut());
    if !sk.is_null() && refcount_inc_not_zero(&(*sk).sk_refcnt) != 0 {
        sk
    } else {
        ptr::null_mut()
    }
}

#[no_mangle]
pub unsafe extern "C" fn udp6_skb_len(
    skb: *mut sk_buff,
) -> c_int {
    if inet6_is_jumbogram(skb) != 0 {
        (*skb).len
    } else {
        udp_skb_len(skb)
    }
}

#[no_mangle]
pub unsafe extern "C" fn udpv6_recvmsg(
    sk: *mut sock,
    msg: *mut msghdr,
    len: usize,
    noblock: c_int,
    flags: c_int,
    addr_len: *mut c_int,
) -> c_int {
    let np = &(*sk).ipv6_pinfo;
    let _inet = &(*sk).inet_sk;
    let mut err: c_int = 0;
    let is_udplite: c_int = 0;

    if flags & MSG_ERRQUEUE != 0 {
        return ipv6_recv_error(sk, msg as *mut c_void, len, addr_len);
    }

    if np.rxpmtu != 0 && np.rxopt.bits.rxpmtu != 0 {
        return ipv6_recv_rxpmtu(sk, msg as *mut c_void, len, addr_len);
    }

    let mut off = sk_peek_offset(sk, flags);
    let skb = __skb_recv_udp(sk, flags, noblock, &mut off, &mut err);
    if skb.is_null() {
        return err;
    }

    let ulen = udp6_skb_len(skb);
    let mut copied = len;
    if copied > ulen as usize - off as usize {
        copied = ulen as usize - off as usize;
        (*msg).msg_flags |= MSG_TRUNC;
    }

    let is_udp4 = if (*skb).protocol == htons(ETH_P_IP) { 1 } else { 0 };
    let _mib = __UDPX_MIB(sk, is_udp4);

    let checksum_valid = if copied < ulen as usize || (flags & MSG_PEEK) != 0 || (is_udplite != 0 && (*UDP_SKB_CB(skb)).partial_cov != 0) {
        let valid = udp_skb_csum_unnecessary(skb) != 0 || __udp_lib_checksum_complete(skb) == 0;
        if !valid {
            return -EINVAL;
        }
        valid
    } else {
        true
    };

    if checksum_valid || udp_skb_csum_unnecessary(skb) != 0 {
        if udp_skb_is_linear(skb) != 0 {
            return copy_linear_skb(skb, copied, off, (*msg).msg_iter);
        } else {
            return skb_copy_datagram(skb, off, (*msg).msg_iter, copied);
        }
    }

    0
}

// Test cases

#[cfg(test)]
mod tests {
    #[test]
    fn test_udp_all() {
        unsafe {
            let mut buf = [0u8; 1024];
            let mut sk = core::mem::zeroed::<super::sock>();
            let mut net = core::mem::zeroed::<super::net>();
            let mut skb = core::mem::zeroed::<super::sk_buff>();
            skb.head = buf.as_mut_ptr() as *mut _;
            skb.data = buf.as_mut_ptr() as *mut _;
            let mut dev = core::mem::zeroed::<super::net_device>();
            skb.dev = &mut dev as *mut _ as *mut _;
            
            let mut saddr = core::mem::zeroed::<super::in6_addr>();
            let mut msg = core::mem::zeroed::<super::msghdr>();
            let mut hslot = core::mem::zeroed::<super::udp_hslot>();
            let mut udptable = core::mem::zeroed::<super::udp_table>();
            let mut alen = 0;
            
            let _ = super::udp_v6_get_port(&mut sk as *mut _, 0);
            super::udp_v6_rehash(&mut sk as *mut _);
            let _ = super::compute_score(&mut sk as *mut _, &net as *const _, &saddr as *const _, 0, &saddr as *const _, 0, 0, 0);
            let _ = super::lookup_reuseport(&net as *const _, &mut sk as *mut _, &mut skb as *mut _, &saddr as *const _, 0, &saddr as *const _, 0);
            let _ = super::udp6_lookup_run_bpf(&net as *const _, &mut udptable as *mut _, &mut skb as *mut _, &saddr as *const _, 0, &saddr as *const _, 0);
            let _ = super::__udp6_lib_lookup(&net as *const _, &saddr as *const _, 0, &saddr as *const _, 0, 0, 0, &mut udptable as *mut _, &mut skb as *mut _);
            let _ = super::udp6_lib_lookup(&net as *const _, &saddr as *const _, 0, &saddr as *const _, 0, 0);
            let _ = super::udp6_skb_len(&mut skb as *mut _);
            let _ = super::udpv6_recvmsg(&mut sk as *mut _, &mut msg as *mut _, 0, 0, 0, &mut alen as *mut _);
        }
    }

}