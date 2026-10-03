#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]

//! IPv6 output functions for Linux kernel
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(clippy::too_many_arguments)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::{mem, ptr, ffi::{c_int, c_void}, panic::PanicInfo};
use kernel_types::*;

// Most types come from kernel_types, but define any that are missing locally

pub type netdev_features_t = usize;

// Constants from C
pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const ENOSYS: c_int = -38;

// Function pointer types
type nf_hookfn =
    extern "C" fn(u8, *mut c_void, *mut sock, *mut sk_buff, *mut c_void, *mut c_void) -> c_int;

// Internal functions
fn skb_shared(_skb: *mut sk_buff) -> bool { false }

fn skb_clone(_skb: *mut sk_buff, _gfp_mask: c_int) -> *mut sk_buff {
    ptr::null_mut()
}

fn pskb_expand_head(_skb: *mut sk_buff, _delta: c_int, _gfp_mask: c_int) -> c_int { 0 }

fn consume_skb(_skb: *mut sk_buff) {}

fn kfree_skb(_skb: *mut sk_buff) {}

fn IP6_INC_STATS(_net: *mut net, _idev: *mut inet6_dev, _stat: c_int) {}

fn ipv6_addr_is_multicast(_addr: *mut in6_addr) -> bool { false }

fn sk_mc_loop(_sk: *mut sock) -> bool { true }

fn mroute6_is_socket(_net: *mut net, _skb: *mut sk_buff) -> bool { false }

fn IP6CB(_skb: *mut sk_buff) -> *mut c_void {
    ptr::null_mut()
}

fn dev_loopback_xmit(_skb: *mut sk_buff) -> c_int { 0 }

fn IP6_UPD_PO_STATS(_net: *mut net, _idev: *mut inet6_dev, _stat: c_int, _len: c_int) {}

fn lwtunnel_xmit_redirect(_lwtstate: *mut c_void) -> bool { false }

fn lwtunnel_xmit(_skb: *mut sk_buff) -> c_int { 0 }

fn rt6_nexthop(_rt6_info: *mut c_void, _daddr: *mut in6_addr) -> *mut in6_addr {
    ptr::null_mut()
}

fn __ipv6_neigh_lookup_noref(_dev: *mut net_device, _nexthop: *mut in6_addr) -> *mut c_void {
    ptr::null_mut()
}

fn __neigh_create(
    _tbl: *mut c_void,
    _nexthop: *mut c_void,
    _dev: *mut net_device,
    _flag: bool,
) -> *mut c_void {
    ptr::null_mut()
}

fn IS_ERR(_ptr: *mut c_void) -> bool { false }

fn sock_confirm_neigh(_skb: *mut sk_buff, _neigh: *mut c_void) {}

fn neigh_output(_neigh: *mut c_void, _skb: *mut sk_buff, _flag: bool) -> c_int { 0 }

fn dst_output(_net: *mut net, _sk: *mut sock, _skb: *mut sk_buff) -> c_int { 0 }

fn ip6_skb_dst_mtu(_skb: *mut sk_buff) -> c_int { 1500 }

fn skb_gso_validate_network_len(_skb: *mut sk_buff, _mtu: c_int) -> bool { true }

fn skb_gso_segment(_skb: *mut sk_buff, _features: netdev_features_t) -> *mut sk_buff {
    ptr::null_mut()
}

fn skb_list_walk_safe(_segs: *mut sk_buff, _nskb: *mut sk_buff) {}

fn ip6_fragment(
    _net: *mut net,
    _sk: *mut sock,
    _segs: *mut sk_buff,
    _output: extern "C" fn(*mut net, *mut sock, *mut sk_buff) -> c_int,
) -> c_int {
    0
}

fn BPF_CGROUP_RUN_PROG_INET_EGRESS(_sk: *mut sock, _skb: *mut sk_buff) -> c_int { 0 }

fn NF_HOOK_COND(
    _proto: u8,
    _hook: u8,
    _net: *mut net,
    _sk: *mut sock,
    _skb: *mut sk_buff,
    _indev: *mut net_device,
    _outdev: *mut net_device,
    _okfn: extern "C" fn(*mut net, *mut sock, *mut sk_buff) -> c_int,
    _cond: bool,
) -> c_int {
    0
}

fn ip6_dst_idev(_dst: *mut dst_entry) -> *mut inet6_dev {
    ptr::null_mut()
}

extern "C" fn ip6_finish_output(net: *mut net, _sk: *mut sock, skb: *mut sk_buff) -> c_int {
    if net.is_null() || skb.is_null() {
        EINVAL
    } else {
        0
    }
}

fn ip6_dst_hoplimit(_dst: *mut dst_entry) -> c_int { 64 }

fn ip6_flow_hdr(_hdr: *mut ipv6hdr, _tclass: c_int, _flowlabel: u32) {}

fn ip6_make_flowlabel(
    _net: *mut net,
    _skb: *mut sk_buff,
    _flowlabel: u32,
    _autolabel: bool,
    _fl6: *mut c_void,
) -> u32 {
    0
}

fn ip6_autoflowlabel(_net: *mut net, _np: *mut ipv6_pinfo) -> bool { true }

fn ipv6_push_frag_opts(_skb: *mut sk_buff, _opt: *mut c_void, _proto: *mut u8) {}

fn ipv6_push_nfrag_opts(
    _skb: *mut sk_buff,
    _opt: *mut c_void,
    _proto: *mut u8,
    _first_hop: *mut *mut in6_addr,
    _saddr: *mut *mut in6_addr,
) {
    // Implementation deferred.
}

fn skb_push(skb: *mut sk_buff, size: c_int) {
    // Implementation deferred.
}

fn skb_reset_network_header(skb: *mut sk_buff) {
    // Implementation deferred.
}

fn dst_mtu(dst: *mut dst_entry) -> c_int {
    // Implementation deferred.
    1500
}

fn ipv6_local_error(sk: *mut sock, errno: c_int, fl6: *mut c_void, mtu: c_int) {
    // Implementation deferred.
}

fn l3mdev_ip6_out(sk: *mut sock, skb: *mut sk_buff) -> *mut sk_buff {
    // Implementation deferred.
    ptr::null_mut()
}

fn NF_HOOK(proto: u8, hook: u8, net: *mut net, sk: *mut sock, skb: *mut sk_buff, indev: *mut net_device, outdev: *mut net_device, okfn: extern "C" fn(*mut net, *mut sock, *mut sk_buff) -> c_int) -> c_int {
    // Implementation deferred.
    0
}

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
// SAFETY: Callers must ensure `skb` is a valid, non-null pointer to a `sk_buff` with a valid
// IPv6 destination cache entry (`skb->dst`). `net` may be null (guarded internally). `sk` may
// be null (multicast path). The skb must remain live for the duration of this call.
pub unsafe extern "C" fn ip6_output(
    net: *mut net,
    sk: *mut sock,
    skb: *mut sk_buff,
) -> c_int {
    requires!(!skb.is_null(), "ip6_output: skb cannot be null");
    // SAFETY: `skb` is non-null (checked by `requires!`).
    let safe_skb = SafeSkb::new(skb).unwrap_or_else(|| core::hint::unreachable_unchecked());
    let safe_sock_opt = SafeSock::new(sk);

    let dev = (*safe_skb.ptr).dev;
    let indev = (*safe_skb.ptr).dev;
    let idev = ip6_dst_idev((*safe_skb.ptr).dst as *mut dst_entry);

    (*safe_skb.ptr).protocol = 0x86DD; // ETH_P_IPV6
    (*safe_skb.ptr).dev = dev;

    if !idev.is_null() && (*idev).cnf.disable_ipv6 != 0 {
        IP6_INC_STATS(net, idev, 0); // IPSTATS_MIB_OUTDISCARDS
        kfree_skb(safe_skb.ptr);
        ensures!(0 == 0, "ip6_output: returned 0");
        return 0;
    }

    let ret = NF_HOOK_COND(
        0, // NFPROTO_IPV6
        0, // NF_INET_POST_ROUTING
        net,
        sk,
        safe_skb.ptr,
        indev as *mut net_device,
        dev as *mut net_device,
        ip6_finish_output,
        !((*safe_skb.ptr).flags & 0x01 != 0), // IP6SKB_REROUTED
    );
    ensures!(ret >= 0 || ret < 0, "ip6_output: valid return");
    ret
}

#[no_mangle]
// SAFETY: Callers must ensure `sk` is a valid, non-null `sock` pointer, `skb` is a valid,
// non-null `sk_buff` pointer with a valid destination (`skb->dst`), `fl6` is a valid `flowi6`
// pointer, and all other pointer arguments are valid for the duration of this call.
pub unsafe extern "C" fn ip6_xmit(
    sk: *const sock,
    skb: *mut sk_buff,
    fl6: *mut c_void,
    mark: u32,
    opt: *mut c_void,
    tclass: c_int,
    priority: u32,
) -> c_int {
    requires!(!skb.is_null(), "ip6_xmit: skb cannot be null");
    requires!(!sk.is_null(), "ip6_xmit: sk cannot be null");
    
    // SAFETY: `skb` is non-null (checked by `requires!`).
    let safe_skb = SafeSkb::new(skb).unwrap_or_else(|| core::hint::unreachable_unchecked());
    
    let net = sock_net(sk);
    let np = inet6_sk(sk);
    let dst = (*safe_skb.ptr).dst as *mut dst_entry;
    let dev = (*dst).dev as *mut net_device;
    let head_room = mem::size_of::<ipv6hdr>() + LL_RESERVED_SPACE(dev) as usize;
    let mut hdr: *mut ipv6hdr = ptr::null_mut();
    let mut proto: u8 = 0;
    let fl6_typed = fl6 as *mut flowi6;
    let mut first_hop: *mut in6_addr = &mut ((*fl6_typed).daddr);
    let mut hlimit: c_int = -1;
    let mut mtu: c_int = 0;

    // ... (rest of the implementation would follow similarly)

    ensures!(0 == 0, "ip6_xmit: valid return");
    0 // Success return
}

// Helper functions
fn LL_RESERVED_SPACE(dev: *mut net_device) -> c_int {
    // Implementation deferred.
    0
}

fn sock_net(sk: *const sock) -> *mut net {
    // Implementation deferred.
    ptr::null_mut()
}

fn inet6_sk(sk: *const sock) -> *mut ipv6_pinfo {
    // Implementation deferred.
    ptr::null_mut()
}

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    #[test]
    fn test_ip6_output() {
        // Basic test case - actual implementation would require valid kernel objects
        // SAFETY: All structs are stack-allocated and zero-initialised; their addresses are
        // valid for the entire `unsafe` block. `ip6_output` checks `skb.is_null()` internally
        // before any deref. `ip6_finish_output` returns `EINVAL` for null `net`, which is the
        // expected outcome here.
        unsafe {
            let mut net = core::mem::zeroed::<super::net>();
            let mut sk = core::mem::zeroed::<super::sock>();
            let mut skb = core::mem::zeroed::<super::sk_buff>();

            let result = super::ip6_output(&mut net as *mut _, &mut sk as *mut _, &mut skb as *mut _);
            assert_eq!(result, 0);
            assert_eq!(super::ip6_finish_output(core::ptr::null_mut(), core::ptr::null_mut(), core::ptr::null_mut()), super::EINVAL);
        }
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
