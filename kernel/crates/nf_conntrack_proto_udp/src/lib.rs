#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
//!
//! This module provides FFI-compatible Rust bindings for the Linux kernel's UDP connection tracking
//! functionality. It implements connection tracking for UDP and UDPLITE protocols with timeout
//! management and error checking capabilities.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(clippy::manual_c_str_literals)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::{ffi::{c_char, c_int, c_void}, mem::{self, size_of}, ptr};
use kernel_types::*;

pub const IPPROTO_UDP: c_int = 17;
pub const IPPROTO_UDPLITE: c_int = 136;
pub const NF_ACCEPT: c_int = 1;
pub const NF_INET_PRE_ROUTING: c_int = 0;

pub const UDP_CT_UNREPLIED: usize = 0; pub const UDP_CT_REPLIED: usize = 1; pub const UDP_CT_MAX: usize = 2;

pub const IPS_SEEN_REPLY_BIT: c_int = 1;
pub const IPS_ASSURED_BIT: c_int = 2;
pub const IPS_NAT_CLASH: c_int = 4;
pub const IPCT_ASSURED: c_int = 1;
pub const CTA_TIMEOUT_UDP_UNREPLIED: c_int = 1;
pub const CTA_TIMEOUT_UDP_REPLIED: c_int = 2;
pub const CTA_TIMEOUT_UDP_MAX: c_int = 3;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_hook_state {
    pub net: *mut c_void,
    pub pf: c_int,
    pub hook: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_proto { pub udp: nf_conn_udp }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_udp { pub stream_ts: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_udp_net { pub timeouts: [c_int; UDP_CT_MAX] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_l4proto { pub l4proto: c_int, pub allow_clash: bool }

#[repr(C)]
pub struct net_t { _priv: [u8; 0] }

// Static data
static UDP_TIMEOUTS: [c_int; UDP_CT_MAX as usize] = [30, 120]; // *HZ

unsafe extern "C" {
    fn nf_udp_pernet(net: *mut c_void) -> *mut nf_udp_net;
    fn nf_l4proto_log_invalid(
        skb: *mut sk_buff,
        net: *mut c_void,
        pf: c_int,
        proto: c_int,
        fmt: *const c_char,
        ...
    ) -> c_int;
    fn nf_checksum(skb: *mut sk_buff, hook: c_int, dataoff: c_int, proto: c_int, pf: c_int) -> bool;
    fn nf_checksum_partial(
        skb: *mut sk_buff,
        hook: c_int,
        dataoff: c_int,
        cscov: c_int,
        proto: c_int,
        pf: c_int,
    ) -> bool;
    fn skb_header_pointer(
        skb: *mut sk_buff,
        dataoff: c_int,
        size: c_int,
        hdr: *mut udphdr,
    ) -> *mut udphdr;
    fn nf_ct_timeout_lookup(ct: *mut nf_conn) -> *mut c_int;
    fn nf_ct_refresh_acct(ct: *mut nf_conn, ctinfo: c_int, skb: *mut sk_buff, timeout: c_int) -> c_int;
    fn nf_conntrack_event_cache(event: c_int, ct: *mut nf_conn);
    fn nf_ct_net(ct: *mut nf_conn) -> *mut c_void;
    fn nf_ct_port_tuple_to_nlattr(skb: *mut sk_buff, data: *mut c_void) -> c_int;
    fn nf_ct_port_nlattr_to_tuple(tb: *mut c_void, data: *mut c_void) -> c_int;
    fn nf_ct_port_nlattr_tuple_size() -> c_int;
}

#[inline(always)]
unsafe fn ntohs(v: u16) -> u16 { u16::from_be(v) }

fn udp_error_log(skb: *mut sk_buff, state: *mut nf_hook_state, msg: *const c_char) {
    unsafe {
        nf_l4proto_log_invalid(skb, (*state).net, (*state).pf, IPPROTO_UDP, msg);
    }
}

fn udplite_error_log(skb: *mut sk_buff, state: *mut nf_hook_state, msg: *const c_char) {
    unsafe {
        nf_l4proto_log_invalid(skb, (*state).net, (*state).pf, IPPROTO_UDPLITE, msg);
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn udp_error(
    skb: *mut sk_buff,
    dataoff: c_int,
    state: *mut nf_hook_state,
) -> bool {
    let udplen = (*skb).len - dataoff as u32;
    let mut _hdr: udphdr = mem::zeroed();
    let hdr = skb_header_pointer(skb, dataoff, size_of::<udphdr>() as c_int, &mut _hdr);

    if hdr.is_null() {
        udp_error_log(skb, state, c"short packet".as_ptr());
        return true;
    }

    let hdr_len = (*hdr).len;
    if (ntohs(hdr_len) as u32 > udplen) || ((ntohs(hdr_len) as usize) < size_of::<udphdr>()) {
        udp_error_log(skb, state, c"truncated/malformed packet".as_ptr());
        return true;
    }

    if (*hdr).check == 0 {
        return false;
    }

    if (*state).hook == NF_INET_PRE_ROUTING &&
       nf_checksum(skb, (*state).hook, dataoff, IPPROTO_UDP, (*state).pf) {
        udp_error_log(skb, state, b"bad checksum\0".as_ptr() as *const c_char);
        return true;
    }

    false
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_udp_packet(
    ct: *mut nf_conn,
    skb: *mut sk_buff,
    dataoff: c_int,
    ctinfo: c_int,
    state: *mut nf_hook_state,
) -> c_int {
    if udp_error(skb, dataoff, state) {
        return -NF_ACCEPT;
    }

    let mut timeouts: *mut c_int = ptr::null_mut();
    let ct_timeout = nf_ct_timeout_lookup(ct);

    if ct_timeout.is_null() {
        let net = nf_ct_net(ct);
        let un = nf_udp_pernet(net);
        timeouts = (*un).timeouts.as_mut_ptr();
    } else {
        timeouts = ct_timeout;
    }

    if !nf_ct_is_confirmed(ct) {
        let proto = (*ct).proto as *mut nf_conn_proto;
        (*proto).udp.stream_ts = 2 * HZ() + jiffies();
    }

    if test_bit(ct, IPS_SEEN_REPLY_BIT) {
        let proto = (*ct).proto as *mut nf_conn_proto;
        let extra = if time_after(jiffies(), (*proto).udp.stream_ts) {
            *timeouts.add(UDP_CT_REPLIED)
        } else {
            *timeouts.add(UDP_CT_UNREPLIED)
        };

        nf_ct_refresh_acct(ct, ctinfo, skb, extra);

        if ((*ct).status & IPS_NAT_CLASH as c_ulong) != 0 {
            return NF_ACCEPT;
        }

        if !test_and_set_bit(ct, IPS_ASSURED_BIT) {
            nf_conntrack_event_cache(IPCT_ASSURED, ct);
        }
    } else {
        nf_ct_refresh_acct(ct, ctinfo, skb, *timeouts.add(UDP_CT_UNREPLIED));
    }

    NF_ACCEPT
}

// UDPLITE implementation
#[no_mangle]
pub unsafe extern "C" fn udplite_error(
    skb: *mut sk_buff,
    dataoff: c_int,
    state: *mut nf_hook_state,
) -> bool {
    let udplen = (*skb).len - dataoff as u32;
    let mut _hdr: udphdr = mem::zeroed();
    let hdr = skb_header_pointer(skb, dataoff, size_of::<udphdr>() as c_int, &mut _hdr);

    if hdr.is_null() {
        udplite_error_log(skb, state, b"short packet\0".as_ptr() as *const c_char);
        return true;
    }

    let mut cscov = ntohs((*hdr).len);
    if cscov == 0 {
        cscov = udplen as u16;
    } else if (cscov < size_of::<udphdr>() as u16) || (cscov > udplen as u16) {
        udplite_error_log(skb, state, b"invalid checksum coverage\0".as_ptr() as *const c_char);
        return true;
    }

    if (*hdr).check == 0 {
        udplite_error_log(skb, state, b"checksum missing\0".as_ptr() as *const c_char);
        return true;
    }

    if (*state).hook == NF_INET_PRE_ROUTING &&
       nf_checksum_partial(skb, (*state).hook, dataoff, cscov as c_int, IPPROTO_UDP, (*state).pf) {
        udplite_error_log(skb, state, b"bad checksum\0".as_ptr() as *const c_char);
        return true;
    }

    false
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_udplite_packet(
    ct: *mut nf_conn,
    skb: *mut sk_buff,
    dataoff: c_int,
    ctinfo: c_int,
    state: *mut nf_hook_state,
) -> c_int {
    if udplite_error(skb, dataoff, state) {
        return -NF_ACCEPT;
    }

    let mut timeouts: *mut c_int = ptr::null_mut();
    let ct_timeout = nf_ct_timeout_lookup(ct);

    if ct_timeout.is_null() {
        let net = nf_ct_net(ct);
        let un = nf_udp_pernet(net);
        timeouts = (*un).timeouts.as_mut_ptr();
    } else {
        timeouts = ct_timeout;
    }

    if test_bit(ct, IPS_SEEN_REPLY_BIT) {
        nf_ct_refresh_acct(ct, ctinfo, skb, *timeouts.add(UDP_CT_REPLIED));

        if ((*ct).status & IPS_NAT_CLASH as c_ulong) != 0 {
            return NF_ACCEPT;
        }

        if !test_and_set_bit(ct, IPS_ASSURED_BIT) {
            nf_conntrack_event_cache(IPCT_ASSURED, ct);
        }
    } else {
        nf_ct_refresh_acct(ct, ctinfo, skb, *timeouts.add(UDP_CT_UNREPLIED));
    }

    NF_ACCEPT
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_udp_init_net(net: *mut c_void) {
    let un = nf_udp_pernet(net);
    for i in 0..UDP_CT_MAX as usize {
        (*un).timeouts[i] = UDP_TIMEOUTS[i] * HZ();
    }
}

#[no_mangle]
pub unsafe extern "C" fn udp_timeout(ct: *mut nf_conn) -> c_int {
    let t = nf_ct_timeout_lookup(ct);
    if !t.is_null() {
        *t
    } else {
        UDP_TIMEOUTS[UDP_CT_UNREPLIED]
    }
}

#[inline]
unsafe fn test_bit(ct: *mut nf_conn, bit: c_int) -> bool { (*ct).status & (1 << bit) != 0 }

#[inline]
unsafe fn test_and_set_bit(ct: *mut nf_conn, bit: c_int) -> bool {
    let old = (*ct).status;
    (*ct).status |= 1 << bit;
    old & (1 << bit) != 0
}

#[inline]
fn time_after(x: c_int, y: c_int) -> bool { (x - y) > 0 }

#[inline]
fn jiffies() -> c_int {
    // Implementation deferred.
    0
}

#[inline]
fn HZ() -> c_int { 100 }

#[inline]
fn nf_ct_is_confirmed(_ct: *mut nf_conn) -> bool {
    // Implementation deferred.
    false
}

// Module exports
#[no_mangle]
pub static NF_CONNTRACK_L4PROTO_UDP: nf_conntrack_l4proto = nf_conntrack_l4proto {
    l4proto: IPPROTO_UDP,
    allow_clash: true,
    // ... (other fields omitted for brevity)
};

#[cfg(feature = "udplite")]
#[no_mangle]
pub static NF_CONNTRACK_L4PROTO_UDPLITE: nf_conntrack_l4proto = nf_conntrack_l4proto {
    l4proto: IPPROTO_UDPLITE,
    allow_clash: true,
    // ... (other fields omitted for brevity)
};
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── ABI / protocol constant tests ────────────────────────────────────────

    #[test]
    fn test_protocol_constants() {
        assert_eq!(IPPROTO_UDP, 17);
        assert_eq!(IPPROTO_UDPLITE, 136);
        assert_eq!(NF_ACCEPT, 1);
        assert_eq!(NF_INET_PRE_ROUTING, 0);
    }

    #[test]
    fn test_conntrack_state_indices() {
        assert_eq!(UDP_CT_UNREPLIED, 0);
        assert_eq!(UDP_CT_REPLIED, 1);
        assert_eq!(UDP_CT_MAX, 2);
    }

    #[test]
    fn test_bit_flag_constants() {
        assert_eq!(IPS_SEEN_REPLY_BIT, 1);
        assert_eq!(IPS_ASSURED_BIT, 2);
        assert_eq!(IPS_NAT_CLASH, 4);
        assert_eq!(IPCT_ASSURED, 1);
    }

    // ── ntohs correctness ────────────────────────────────────────────────────

    #[test]
    fn test_ntohs_swaps_bytes() {
        // 0x0035 in network order is port 53 (DNS)
        let net_port: u16 = 0x3500u16; // big-endian 53 stored in little-endian mem
        let host = unsafe { ntohs(net_port) };
        assert_eq!(host, 0x0035u16);
    }

    // ── test_bit / test_and_set_bit helpers ─────────────────────────────────

    #[test]
    fn test_bit_reads_correct_bit() {
        let mut ct: nf_conn = unsafe { core::mem::zeroed() };
        ct.status = 1 << IPS_SEEN_REPLY_BIT; // bit-1 set
        let seen = unsafe { test_bit(&mut ct as *mut nf_conn, IPS_SEEN_REPLY_BIT) };
        let assured = unsafe { test_bit(&mut ct as *mut nf_conn, IPS_ASSURED_BIT) };
        assert!(seen, "IPS_SEEN_REPLY_BIT should be set");
        assert!(!assured, "IPS_ASSURED_BIT should not be set");
    }

    #[test]
    fn test_and_set_bit_sets_and_returns_old() {
        let mut ct: nf_conn = unsafe { core::mem::zeroed() };
        // First call: bit not set → returns false, then sets it
        let was_set = unsafe { test_and_set_bit(&mut ct as *mut nf_conn, IPS_ASSURED_BIT) };
        assert!(!was_set, "bit was clear before first set");
        // Second call: bit now set → returns true
        let still_set = unsafe { test_and_set_bit(&mut ct as *mut nf_conn, IPS_ASSURED_BIT) };
        assert!(still_set, "bit should be set after first call");
    }

    // ── time_after helper ────────────────────────────────────────────────────

    #[test]
    fn test_time_after_positive_difference() {
        assert!(time_after(100, 50), "100 is after 50");
        assert!(!time_after(50, 100), "50 is not after 100");
        assert!(!time_after(50, 50), "equal times: not strictly after");
    }

    // ── static timeout table ─────────────────────────────────────────────────

    #[test]
    fn test_udp_timeouts_have_two_entries() {
        assert_eq!(UDP_TIMEOUTS.len(), UDP_CT_MAX);
        // Unreplied timeout must be shorter than replied timeout (kernel policy)
        assert!(
            UDP_TIMEOUTS[UDP_CT_UNREPLIED] < UDP_TIMEOUTS[UDP_CT_REPLIED],
            "unreplied timeout must be shorter than replied"
        );
    }
}

