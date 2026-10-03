#![allow(clippy::all, clippy::pedantic)]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(clippy::needless_return)]
#![allow(clippy::not_unsafe_ptr_arg_deref)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::{ptr, ffi::{c_int, c_void}, cell::UnsafeCell};
use kernel_types::*;

pub const EINVAL: c_int = 22;
pub const ENOMEM: c_int = 12;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct flowi6 {
    pub flowi6_oif: u32,
    pub flowi6_mark: u32,
    pub flowi6_uid: u32,
    pub daddr: [u8; 16],
    pub saddr: [u8; 16],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_rt_info {
    pub daddr: [u8; 16],
    pub saddr: [u8; 16],
    pub mark: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_bridge_frag_data { pub _priv: u8 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_queue_entry_state {
    pub hook: u32,
    pub net: *mut c_void,
    pub sk: *mut c_void,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_queue_entry { pub state: nf_queue_entry_state }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_ipv6_ops {
    pub route_me_harder:
        unsafe extern "C" fn(net: *mut c_void, sk_partial: *mut c_void, skb: *mut c_void) -> c_int,
    pub route: unsafe extern "C" fn(
        net: *mut c_void,
        dst: *mut *mut c_void,
        fl: *mut c_void,
        strict: c_int,
    ) -> c_int,
    pub fragment: extern "C" fn(
        net: *mut c_void,
        sk: *mut c_void,
        skb: *mut c_void,
        data: *mut nf_bridge_frag_data,
        output: extern "C" fn(
            net: *mut c_void,
            sk: *mut c_void,
            data: *mut nf_bridge_frag_data,
            skb: *mut c_void,
        ) -> c_int,
    ) -> c_int,
    pub reroute: unsafe extern "C" fn(skb: *mut c_void, entry: *const nf_queue_entry) -> c_int,
    pub route_input: extern "C" fn(skb: *mut c_void) -> c_int,
    pub br_fragment: extern "C" fn(
        net: *mut c_void,
        sk: *mut c_void,
        skb: *mut c_void,
        data: *mut nf_bridge_frag_data,
        output: extern "C" fn(
            net: *mut c_void,
            sk: *mut c_void,
            data: *mut nf_bridge_frag_data,
            skb: *mut c_void,
        ) -> c_int,
    ) -> c_int,
}

// Removed duplicate - see extern block at end of file

// Helper functions to access fields from opaque types
unsafe fn get_sk_bound_dev_if(sk: *const sock) -> u32 {
    if sk.is_null() {
        return 0;
    }
    let bound_dev = (*sk).sk_bound_dev_if as usize;
    bound_dev as u32
}

unsafe fn get_skb_mark(skb: *const sk_buff) -> u32 {
    if skb.is_null() {
        return 0;
    }
    let mark = (*skb).mark as usize;
    mark as u32
}

unsafe fn get_skb_dev(skb: *const sk_buff) -> *mut c_void {
    if skb.is_null() {
        return ptr::null_mut();
    }
    (*skb).dev
}

unsafe fn get_skb_dst(skb: *const sk_buff) -> *mut dst_entry {
    if skb.is_null() {
        return ptr::null_mut();
    }
    (*skb).dst as *mut dst_entry
}

unsafe fn get_dst_error(dst: *const dst_entry) -> c_int {
    if dst.is_null() {
        return -EINVAL;
    }
    let error = (*dst).error as usize;
    error as c_int
}

unsafe fn get_net_device_mtu(_dev: *const net_device) -> u32 {
    1500 // Default MTU
}

unsafe fn get_net_device_hard_header_len(_dev: *const net_device) -> u32 {
    14 // Default ethernet header length
}

unsafe fn get_net_device_needed_tailroom(_dev: *const net_device) -> u32 {
    0 // Default tailroom
}

// Wrapper for in6_addr to [u8; 16] conversion
unsafe fn in6_addr_to_bytes(addr: &in6_addr) -> [u8; 16] {
    let mut bytes = [0u8; 16];
    let src = addr as *const in6_addr as *const u8;
    for i in 0..16 {
        bytes[i] = *src.add(i);
    }
    bytes
}

#[no_mangle]
pub unsafe extern "C" fn ip6_route_me_harder(
    net: *mut c_void,
    sk_partial: *mut c_void,
    skb: *mut c_void,
) -> c_int {
    if net.is_null() || sk_partial.is_null() || skb.is_null() {
        return -EINVAL;
    }

    let iph = ipv6_hdr(skb);
    let sk = sk_to_full_sk(sk_partial) as *const sock;
    let skb_ref = skb as *const sk_buff;

    let sk_bound_dev = get_sk_bound_dev_if(sk);
    let skb_mark = get_skb_mark(skb_ref);
    let skb_dev = get_skb_dev(skb_ref);

    let mut fl6 = flowi6 {
        flowi6_oif: if !sk.is_null() && sk_bound_dev != 0 {
            sk_bound_dev
        } else if (ipv6_addr_type(&mut (*iph).daddr as *mut _) & (1 << 19 | 1 << 31)) != 0 {
            let dev_ptr = skb_dev as *const net_device;
            if !dev_ptr.is_null() {
                (*dev_ptr).ifindex as u32
            } else {
                0
            }
        } else {
            0
        },
        flowi6_mark: skb_mark,
        flowi6_uid: sock_net_uid(net, sk as *mut _),
        daddr: in6_addr_to_bytes(&(*iph).daddr),
        saddr: in6_addr_to_bytes(&(*iph).saddr),
    };

    let mut dst: *mut c_void = ptr::null_mut();
    let _strict = (ipv6_addr_type(&mut (*iph).daddr as *mut _) & (1 << 19 | 1 << 31)) != 0;

    fib6_rules_early_flow_dissect(net, skb, &mut fl6, ptr::null_mut());

    dst = ip6_route_output(net, sk as *mut _, &mut fl6);
    let dst_entry = dst as *const dst_entry;
    let err = get_dst_error(dst_entry);

    if err != 0 {
        IP6_INC_STATS(net, ip6_dst_idev(dst), 3); // IPSTATS_MIB_OUTNOROUTES
        net_dbg_ratelimited(b"ip6_route_me_harder: No more route\n".as_ptr());
        dst_release(dst);
        return err;
    }

    skb_dst_drop(skb);
    skb_dst_set(skb, dst);

    // XFRM handling
    let ip6cb = IP6CB(skb) as *const ip6cb;
    if !ip6cb.is_null() && ((*ip6cb).flags & 1 << 0) == 0 {
        let fl = flowi6_to_flowi(&mut fl6 as *mut _);
        if xfrm_decode_session(skb, fl, 10) == 0 {
            skb_dst_set(skb, ptr::null_mut());
            dst = xfrm_lookup(net, dst, fl, sk as *mut _, 0);
            if dst.is_null() {
                return -ENOMEM;
            }
            skb_dst_set(skb, dst);
        }
    }

    let dst_ptr = get_skb_dst(skb_ref);
    if !dst_ptr.is_null() {
        let dev = (*dst_ptr).dev as *const net_device;
        if !dev.is_null() {
            let hh_len = get_net_device_hard_header_len(dev);
            let headroom = skb_headroom(skb);
            if headroom < hh_len {
                if pskb_expand_head(skb, HH_DATA_ALIGN(hh_len - headroom), 0, 1) != 0 {
                    return -ENOMEM;
                }
            }
        }
    }

    0
}

#[no_mangle]
pub unsafe extern "C" fn nf_ip6_reroute(skb: *mut c_void, entry: *const nf_queue_entry) -> c_int {
    if skb.is_null() || entry.is_null() {
        return -EINVAL;
    }

    let rt_info = nf_queue_entry_reroute(entry);
    if rt_info.is_null() {
        return 0;
    }

    if (*entry).state.hook == 3 {
        return ip6_route_me_harder((*entry).state.net, (*entry).state.sk, skb);
    }

    0
}

#[no_mangle]
pub unsafe extern "C" fn __nf_ip6_route(
    net: *mut c_void,
    dst: *mut *mut c_void,
    fl: *mut c_void,
    _strict: c_int,
) -> c_int {
    if net.is_null() || dst.is_null() || fl.is_null() {
        return -EINVAL;
    }

    // Implementation deferred.
    let fl6 = fl as *mut flowi6;
    let result = ip6_route_output(net, ptr::null_mut(), fl6);
    let result_dst = result as *const dst_entry;
    let err = get_dst_error(result_dst);

    if err != 0 {
        dst_release(result);
    } else {
        *dst = result;
    }
    err
}

#[no_mangle]
pub unsafe extern "C" fn br_ip6_fragment(
    net: *mut c_void,
    sk: *mut c_void,
    mut skb: *mut c_void,
    data: *mut nf_bridge_frag_data,
    output: extern "C" fn(net: *mut c_void, sk: *mut c_void, data: *mut nf_bridge_frag_data, skb: *mut c_void) -> c_int,
) -> c_int {
    if net.is_null() || sk.is_null() || skb.is_null() || data.is_null() {
        return -EINVAL;
    }

    let skb_ref = skb as *const sk_buff;
    let br_cb = BR_INPUT_SKB_CB(skb) as *const ip6cb;
    let frag_max_size = if !br_cb.is_null() {
        (*br_cb).frag_max_size
    } else {
        1500
    };
    let tstamp = (*skb_ref).tstamp;
    let mut state: ip6_frag_state = ip6_frag_state {
        prevhdr: ptr::null_mut(),
        nexthdr: 0,
        hlen: 0,
        mtu: 0,
        left: 0,
        offset: 0,
    };
    let mut prevhdr: *mut u8 = ptr::null_mut();
    let mut nexthdr: u8 = 0;
    let mut mtu: u32 = 0;
    let mut hlen: u32 = 0;
    let mut hroom: u32 = 0;
    let mut err: c_int = 0;
    let mut frag_id: u32 = 0;

    err = ip6_find_1stfragopt(skb, &mut prevhdr);
    if err < 0 {
        return err;
    }
    hlen = err as u32;
    nexthdr = *prevhdr;

    let dev = get_skb_dev(skb_ref) as *const net_device;
    mtu = if !dev.is_null() {
        get_net_device_mtu(dev)
    } else {
        1500
    };
    if frag_max_size as u32 > mtu || frag_max_size < 1280 {
        return -EINVAL;
    }

    mtu = frag_max_size as u32;
    if mtu < hlen + 20 + 8 {
        return -EINVAL;
    }
    mtu -= hlen + 20;

    frag_id = ipv6_select_ident(net, &mut (*ipv6_hdr(skb)).daddr as *mut _, &mut (*ipv6_hdr(skb)).saddr as *mut _);

    if (*skb_ref).ip_summed == 1 && skb_checksum_help(skb) != 0 {
        return -EINVAL;
    }

    hroom = LL_RESERVED_SPACE(dev as *mut _);
    if skb_has_frag_list(skb) != 0 {
        let first_len = skb_pagelen(skb);
        let mut iter: ip6_fraglist_iter = ip6_fraglist_iter {
            frag: ptr::null_mut(),
            offset: 0,
            hlen: 0,
        };

        if first_len > hlen + mtu {
            return -EINVAL;
        }

        if skb_cloned(skb) != 0 {
            return -EINVAL;
        }

        // Walk frag list
        // Implementation deferred.
        // Actual implementation would walk the frag list and validate

        err = ip6_fraglist_init(skb, hlen, prevhdr, nexthdr, frag_id, &mut iter);
        if err < 0 {
            return err;
        }

        loop {
            if !iter.frag.is_null() {
                ip6_fraglist_prepare(skb, &mut iter);
            }

            let skb_mut = skb as *mut sk_buff;
            (*skb_mut).tstamp = tstamp;
            err = output(net, sk, data, skb);
            if err != 0 || iter.frag.is_null() {
                break;
            }

            skb = ip6_fraglist_next(&mut iter);
        }

        // kfree(iter.tmp_hdr); // No tmp_hdr field available
        if err == 0 {
            return 0;
        }

        kfree_skb_list(iter.frag as *mut _);
        return err;
    }

    let dev_tailroom = if !dev.is_null() {
        get_net_device_needed_tailroom(dev)
    } else {
        0
    };
    ip6_frag_init(skb, hlen, mtu, dev_tailroom, LL_RESERVED_SPACE(dev as *mut _), prevhdr, nexthdr, frag_id, &mut state);

    while state.left > 0 {
        let skb2 = ip6_frag_next(skb, &mut state);
        if skb2.is_null() {
            err = -ENOMEM;
            break;
        }

        let skb2_mut = skb2 as *mut sk_buff;
        (*skb2_mut).tstamp = tstamp;
        err = output(net, sk, data, skb2);
        if err != 0 {
            break;
        }
    }

    consume_skb(skb);
    return err;
}

// Hardened IPv6 netfilter hooks
#[no_mangle]
pub extern "C" fn nf_ip6_fragment_stub(
    net: *mut c_void,
    sk: *mut c_void,
    skb: *mut c_void,
    data: *mut nf_bridge_frag_data,
    output: extern "C" fn(
        net: *mut c_void,
        sk: *mut c_void,
        data: *mut nf_bridge_frag_data,
        skb: *mut c_void,
    ) -> c_int,
) -> c_int {
    if net.is_null() || skb.is_null() {
        return -EINVAL;
    }
    // SAFETY: Validated non-null pointers
    unsafe { br_ip6_fragment(net, sk, skb, data, output) }
}

#[no_mangle]
pub extern "C" fn nf_ip6_route_input_stub(skb: *mut c_void) -> c_int {
    if skb.is_null() {
        return -EINVAL;
    }
    0
}

#[no_mangle]
pub extern "C" fn nf_ip6_br_fragment_stub(
    net: *mut c_void,
    sk: *mut c_void,
    skb: *mut c_void,
    data: *mut nf_bridge_frag_data,
    output: extern "C" fn(
        net: *mut c_void,
        sk: *mut c_void,
        data: *mut nf_bridge_frag_data,
        skb: *mut c_void,
    ) -> c_int,
) -> c_int {
    if net.is_null() || skb.is_null() {
        return -EINVAL;
    }
    // SAFETY: Validated non-null pointers
    unsafe { br_ip6_fragment(net, sk, skb, data, output) }
}

// Safe wrapper for br_ip6_fragment
#[no_mangle]
pub extern "C" fn br_ip6_fragment_wrapper(
    net: *mut c_void,
    sk: *mut c_void,
    skb: *mut c_void,
    data: *mut nf_bridge_frag_data,
    output: extern "C" fn(
        net: *mut c_void,
        sk: *mut c_void,
        data: *mut nf_bridge_frag_data,
        skb: *mut c_void,
    ) -> c_int,
) -> c_int {
    unsafe { br_ip6_fragment(net, sk, skb, data, output) }
}

// Wrapper type for UnsafeCell to make it Sync for FFI-exposed structures
pub struct Ipv6OpsCell(UnsafeCell<nf_ipv6_ops>);

// SAFETY: Ipv6OpsCell wraps UnsafeCell<nf_ipv6_ops> which contains only function pointers
// (which are Copy and Sync). This is necessary for FFI-exposed kernel structures that
// may be accessed by C code. Interior mutability is provided safely since the pointed
// data (function pointers) are immutable.
unsafe impl Sync for Ipv6OpsCell {}

// Static struct nf_ipv6_ops
#[no_mangle]
pub static ipv6ops: Ipv6OpsCell = Ipv6OpsCell(UnsafeCell::new(nf_ipv6_ops {
    route_me_harder: ip6_route_me_harder,
    route: __nf_ip6_route,
    fragment: nf_ip6_fragment_stub,
    reroute: nf_ip6_reroute,
    route_input: nf_ip6_route_input_stub,
    br_fragment: br_ip6_fragment_wrapper,
}));

// Initialization
#[no_mangle]
pub unsafe extern "C" fn ipv6_netfilter_init() -> c_int {
    // RCU_INIT_POINTER(nf_ipv6_ops, &ipv6ops);
    0
}

#[no_mangle]
pub static nf_ipv6_ops_instance: nf_ipv6_ops = nf_ipv6_ops {
    route_me_harder: ip6_route_me_harder,
    route: __nf_ip6_route,
    fragment: nf_ip6_fragment_stub,
    reroute: nf_ip6_reroute,
    route_input: nf_ip6_route_input_stub,
    br_fragment: nf_ip6_br_fragment_stub,
};

// ---------------------------------------------------------------------------
// REQ-RCD-038: Netfilter Active Ingress Packet Defense Hook
// ---------------------------------------------------------------------------

/// Evaluates network packet ingress against the RunuX Core Defenses eBPF firewall (REQ-RCD-038).
///
/// Returns 0 if permitted (`Verdict::Pass` or `Verdict::InspectDeep`),
/// or negative error code (`-EPERM` / -1) if blocked by firewall rules
/// (Null scan, Xmas scan, SYN-FIN scan, or polymorphic high-entropy payload).
pub fn runux_netfilter_ingress_check(
    src: [u8; 4],
    dst: [u8; 4],
    flags: u8,
    payload: &[u8],
) -> c_int {
    let verdict = ebpf_firewall::evaluate_packet_ingress(src, dst, flags, payload);
    match verdict {
        ebpf_firewall::Verdict::Pass | ebpf_firewall::Verdict::InspectDeep => 0,
        ebpf_firewall::Verdict::BlockKill | ebpf_firewall::Verdict::Rollback => -1,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ebpf_firewall::{TCP_FLAG_ACK, TCP_FLAG_FIN, TCP_FLAG_PSH, TCP_FLAG_SYN, TCP_FLAG_URG};

    #[test]
    fn test_req_rcd_038_netfilter_ingress_defense() {
        let src = [192, 168, 1, 100];
        let dst = [10, 0, 0, 1];

        // 1. Benign payload with standard ACK | PSH flags passes
        let benign_payload = b"GET /api/v1/health HTTP/1.1\r\nHost: runux\r\n\r\n";
        let res_benign = runux_netfilter_ingress_check(src, dst, TCP_FLAG_ACK | TCP_FLAG_PSH, benign_payload);
        assert_eq!(res_benign, 0, "Benign network packet must pass ingress inspection");

        // 2. Null scan (no flags set) is blocked
        let res_null = runux_netfilter_ingress_check(src, dst, 0, &[]);
        assert_eq!(res_null, -1, "Null scan must be dropped with -EPERM (-1)");

        // 3. SYN-FIN scan is blocked
        let res_syn_fin = runux_netfilter_ingress_check(src, dst, TCP_FLAG_SYN | TCP_FLAG_FIN, &[]);
        assert_eq!(res_syn_fin, -1, "SYN-FIN scan must be dropped with -EPERM (-1)");

        // 4. Xmas scan (FIN | URG | PSH) is blocked
        let res_xmas = runux_netfilter_ingress_check(src, dst, TCP_FLAG_FIN | TCP_FLAG_URG | TCP_FLAG_PSH, &[]);
        assert_eq!(res_xmas, -1, "Xmas scan must be dropped with -EPERM (-1)");
    }
}

// Helper functions (extern declarations)
extern "C" {
    fn ipv6_hdr(skb: *mut c_void) -> *mut ipv6hdr;
    fn sk_to_full_sk(sk_partial: *mut c_void) -> *mut c_void;
    fn ipv6_addr_type(addr: *mut in6_addr) -> u32;
    fn ipv6_addr_equal(a: *mut in6_addr, b: *mut in6_addr) -> bool;
    fn sock_net_uid(net: *mut c_void, sk: *mut c_void) -> u32;
    fn fib6_rules_early_flow_dissect(net: *mut c_void, skb: *mut c_void, fl6: *mut flowi6, flkeys: *mut c_void);
    fn IP6_INC_STATS(net: *mut c_void, idev: *mut c_void, mib: c_int);
    fn net_dbg_ratelimited(fmt: *const u8);
    fn dst_release(dst: *mut c_void);
    fn skb_dst_drop(skb: *mut c_void);
    fn skb_dst_set(skb: *mut c_void, dst: *mut c_void);
    fn xfrm_decode_session(skb: *mut c_void, fl: *mut c_void, af: c_int) -> c_int;
    fn xfrm_lookup(net: *mut c_void, dst: *mut c_void, fl: *mut c_void, sk: *mut c_void, flags: c_int) -> *mut c_void;
    fn HH_DATA_ALIGN(len: u32) -> u32;
    fn skb_headroom(skb: *mut c_void) -> u32;
    fn pskb_expand_head(skb: *mut c_void, headroom: u32, data_len: u32, gfp: c_int) -> c_int;
    fn IP6CB(skb: *mut c_void) -> *mut c_void;
    fn BR_INPUT_SKB_CB(skb: *mut c_void) -> *mut c_void;
    fn ip6_route_output(net: *mut c_void, sk: *mut c_void, fl6: *mut flowi6) -> *mut c_void;
    fn ip6_find_1stfragopt(skb: *mut c_void, prevhdr: *mut *mut u8) -> c_int;
    fn skb_checksum_help(skb: *mut c_void) -> c_int;
    fn LL_RESERVED_SPACE(dev: *mut c_void) -> u32;
    fn skb_has_frag_list(skb: *mut c_void) -> c_int;
    fn skb_pagelen(skb: *mut c_void) -> u32;
    fn skb_cloned(skb: *mut c_void) -> c_int;
    fn ip6_fraglist_init(skb: *mut c_void, hlen: u32, prevhdr: *mut u8, nexthdr: u8, frag_id: u32, iter: *mut ip6_fraglist_iter) -> c_int;
    fn ip6_fraglist_prepare(skb: *mut c_void, iter: *mut ip6_fraglist_iter);
    fn ip6_fraglist_next(iter: *mut ip6_fraglist_iter) -> *mut c_void;
    fn ip6_frag_init(skb: *mut c_void, hlen: u32, mtu: u32, tailroom: u32, headroom: u32, prevhdr: *mut u8, nexthdr: u8, frag_id: u32, state: *mut ip6_frag_state);
    fn ip6_frag_next(skb: *mut c_void, state: *mut ip6_frag_state) -> *mut c_void;
    fn consume_skb(skb: *mut c_void);
    fn kfree_skb(skb: *mut c_void);
    fn kfree_skb_list(skb: *mut c_void);
    fn kfree(ptr: *mut c_void);
    fn ip6_dst_idev(dst: *mut c_void) -> *mut c_void;
    fn flowi6_to_flowi(fl6: *mut flowi6) -> *mut c_void;
    fn ipv6_select_ident(net: *mut c_void, daddr: *mut in6_addr, saddr: *mut in6_addr) -> u32;
    fn nf_queue_entry_reroute(entry: *const nf_queue_entry) -> *mut ip6_rt_info;
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
