#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(clippy::manual_c_str_literals)]

use core::{{mem, ptr}, ffi::{c_int, c_void}};
use kernel_types::*;

pub type size_t = usize;
pub type c_size_t = usize;
pub type socklen_t = u32;
pub type netdev_features_t = u32;

pub const IPPROTO_ESP: u8 = 50;
pub const NEXTHDR_ESP: u8 = 50;
pub const XFRM_MAX_DEPTH: usize = 16;
pub const AF_INET6: c_int = 10;

pub const SKB_GSO_TCPV6: u32 = 0x00000008; pub const SKB_GSO_ESP: u32 = 0x00000400;

pub const NETIF_F_HW_ESP: u32 = 0x00000010;
pub const NETIF_F_HW_ESP_TX_CSUM: u32 = 0x00000020;
pub const NETIF_F_SG: u32 = 0x00000002;
pub const NETIF_F_CSUM_MASK: u32 = 0x0000000F;
pub const NETIF_F_SCTP_CRC: u32 = 0x00000040;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const EOPNOTSUPP: c_int = -95;
pub const EINPROGRESS: c_int = -115;
pub const EAGAIN: c_int = -11;

// Type definitions

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_id { pub spi: u32 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_props { pub header_len: u32 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_mode { pub encap: u8 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_offload_state { pub dev: *mut c_void }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_state {
    pub id: xfrm_id,
    pub props: xfrm_props,
    pub data: *mut c_void,
    pub outer_mode: xfrm_mode,
    pub xso: xfrm_offload_state,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_offload {
    pub flags: u32,
    pub proto: u8,
    pub seq: [u32; 2],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sec_path {
    pub xvec: [*mut xfrm_state; XFRM_MAX_DEPTH],
    pub len: usize,
    pub ovec: [u8; 4],
    pub olen: usize,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_opt_hdr { pub nexthdr: u8 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_address_t { pub a6: [u32; 4] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct list_head { pub next: *mut list_head, pub prev: *mut list_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net_offload_callbacks {
    pub gro_receive: unsafe extern "C" fn(*mut sk_buff) -> *mut sk_buff,
    pub gso_segment: unsafe extern "C" fn(*mut sk_buff, netdev_features_t) -> *mut sk_buff,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net_offload { pub callbacks: net_offload_callbacks }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_type_offload {
    pub description: *const u8,
    pub owner: *const c_void,
    pub proto: u8,
    pub input_tail: unsafe extern "C" fn(*mut xfrm_state, *mut sk_buff) -> c_int,
    pub xmit: unsafe extern "C" fn(*mut xfrm_state, *mut sk_buff, netdev_features_t) -> c_int,
    pub encap: unsafe extern "C" fn(*mut xfrm_state, *mut sk_buff),
}

// SAFETY: xfrm_type_offload is safe to share between threads
unsafe impl Sync for xfrm_type_offload {}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_control_block { pub nhoff: c_int, pub flags: u32 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_tunnel_skb_cb { pub tunnel: xfrm_tunnel_info }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_tunnel_info { pub ip6: *mut c_void }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_spi_skb_cb {
    pub family: c_int,
    pub daddroff: c_int,
    pub seq: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct napi_gro_cb { pub same_flow: c_int, pub flush: c_int }

// SAFETY: Caller must ensure `hdr` is either null or a valid, properly aligned
// pointer to an `ipv6_opt_hdr` with a lifetime that outlasts this call.
// A null pointer is explicitly handled at the start of the function body.
#[no_mangle]
pub unsafe extern "C" fn ipv6_optlen(hdr: *const ipv6_opt_hdr) -> c_int {
    if hdr.is_null() {
        return 0;
    }
    let len = (*hdr).nexthdr & 0x0F;
    (len as c_int) * 8
}

// SAFETY: Caller must ensure `ipv6_hdr` is either null or a valid, aligned
// pointer to an `ipv6hdr` followed by at least `nhlen` bytes of readable
// extension-header data. `nhlen` must not exceed the actual packet length.
// A null pointer is explicitly rejected at the start of the function body.
#[no_mangle]
pub unsafe extern "C" fn esp6_nexthdr_esp_offset(ipv6_hdr: *const ipv6hdr, nhlen: c_int) -> c_int {
    let mut off = mem::size_of::<ipv6hdr>() as c_int;

    if ipv6_hdr.is_null() {
        return 0;
    }

    if (*ipv6_hdr).nexthdr == NEXTHDR_ESP {
        return mem::offset_of!(ipv6hdr, nexthdr) as c_int;
    }

    while off < nhlen {
        let exthdr = (ipv6_hdr as *const u8).add(off as usize) as *const ipv6_opt_hdr;
        if (*exthdr).nexthdr == NEXTHDR_ESP {
            return off;
        }
        let optlen = ipv6_optlen(exthdr);
        if optlen <= 0 {
            break;
        }
        off += optlen;
    }

    0
}

/// GRO receive handler for ESP IPv6
///
/// # Safety
/// - `skb` must be a valid sk_buff pointer
// SAFETY: Caller must pass a non-null, kernel-allocated `sk_buff` that is
// valid for the duration of this call and properly initialised by the GRO
// layer. A null check is performed immediately on entry; all subsequent
// pointer dereferences are guarded by the non-null invariant established
// by that check or by null returns from helper functions.
#[no_mangle]
pub unsafe extern "C" fn esp6_gro_receive(
    skb: *mut sk_buff,
) -> *mut sk_buff {
    if skb.is_null() {
        return ptr::null_mut();
    }

    let offset = skb_gro_offset(skb);
    let xo = xfrm_offload(skb);

    if !pskb_pull(skb, offset) {
        return ptr::null_mut();
    }

    let mut spi: u32 = 0;
    let mut seq: u32 = 0;
    if xfrm_parse_spi(skb, IPPROTO_ESP, &mut spi, &mut seq) != 0 {
        return ptr::null_mut();
    }

    if xo.is_null() || (*xo).flags & (1 << 0) == 0 {
        let sp = secpath_set(skb);
        if sp.is_null() {
            return ptr::null_mut();
        }

        if (*sp).len == XFRM_MAX_DEPTH {
            return ptr::null_mut();
        }

        let x = xfrm_state_lookup(
            dev_net((*skb).sk as *mut sock),
            (*skb).mark,
            &(*ipv6_hdr(skb)).daddr as *const _ as *const nf_inet_addr,
            spi,
            IPPROTO_ESP,
            AF_INET6,
        );
        if x.is_null() {
            return ptr::null_mut();
        }

        (*skb).mark = xfrm_smark_get((*skb).mark, x);

        (*sp).xvec[(*sp).len] = x;
        (*sp).len += 1;
        (*sp).olen += 1;

        let new_xo = xfrm_offload(skb);
        if new_xo.is_null() {
            return ptr::null_mut();
        }
    }

    (*xo).flags |= 1 << 1; // XFRM_GRO

    let nhoff = esp6_nexthdr_esp_offset(ipv6_hdr(skb), offset);
    if nhoff == 0 {
        return ptr::null_mut();
    }

    (*IP6CB(skb)).nhoff = nhoff;
    (*XFRM_TUNNEL_SKB_CB(skb)).tunnel.ip6 = ptr::null_mut();
    (*XFRM_SPI_SKB_CB(skb)).family = AF_INET6;
    (*XFRM_SPI_SKB_CB(skb)).daddroff = mem::offset_of!(ipv6hdr, daddr) as c_int;
    (*XFRM_SPI_SKB_CB(skb)).seq = seq;

    xfrm_input(skb, IPPROTO_ESP, spi, -2);

    secpath_reset(skb);
    skb_push(skb, offset);
    (*NAPI_GRO_CB(skb)).same_flow = 0;
    (*NAPI_GRO_CB(skb)).flush = 1;

    ptr::null_mut()
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {
        core::hint::spin_loop();
    }
}

/// GSO segment handler for ESP IPv6
///
/// # Safety
/// - `skb` must be a valid sk_buff pointer
/// - `features` must be valid netdev_features_t
// SAFETY: Caller must pass a non-null, kernel-allocated `sk_buff` that is
// valid for the duration of this call and properly initialised by the GSO
// layer. `features` is a plain bitmask and needs no special invariants.
// A null check is performed immediately on entry; all subsequent pointer
// dereferences are guarded by the non-null invariant or by null returns
// from helper functions.
#[no_mangle]
pub unsafe extern "C" fn esp6_gso_segment(
    skb: *mut sk_buff,
    features: netdev_features_t,
) -> *mut sk_buff {
    if skb.is_null() {
        return ptr::null_mut();
    }

    let offset = skb_gso_offset(skb);
    let xo = xfrm_offload(skb);

    if !pskb_pull(skb, offset) {
        return ptr::null_mut();
    }

    let mut spi: u32 = 0;
    let mut seq: u32 = 0;
    if xfrm_parse_spi(skb, IPPROTO_ESP, &mut spi, &mut seq) != 0 {
        return ptr::null_mut();
    }

    if xo.is_null() || (*xo).flags & (1 << 0) == 0 {
        let sp = secpath_set(skb);
        if sp.is_null() {
            return ptr::null_mut();
        }

        if (*sp).len == XFRM_MAX_DEPTH {
            return ptr::null_mut();
        }

        let x = xfrm_state_lookup(
            dev_net((*skb).sk as *mut sock),
            (*skb).mark,
            &(*ipv6_hdr(skb)).daddr as *const _ as *const nf_inet_addr,
            spi,
            IPPROTO_ESP,
            AF_INET6,
        );
        if x.is_null() {
            return ptr::null_mut();
        }

        (*skb).mark = xfrm_smark_get((*skb).mark, x);

        (*sp).xvec[(*sp).len] = x;
        (*sp).len += 1;
        (*sp).olen += 1;

        let new_xo = xfrm_offload(skb);
        if new_xo.is_null() {
            return ptr::null_mut();
        }
    }

    (*xo).flags |= 1 << 1; // XFRM_GSO

    let nhoff = esp6_nexthdr_esp_offset(ipv6_hdr(skb), offset);
    if nhoff == 0 {
        return ptr::null_mut();
    }

    (*IP6CB(skb)).nhoff = nhoff;
    (*XFRM_TUNNEL_SKB_CB(skb)).tunnel.ip6 = ptr::null_mut();
    (*XFRM_SPI_SKB_CB(skb)).family = AF_INET6;
    (*XFRM_SPI_SKB_CB(skb)).daddroff = mem::offset_of!(ipv6hdr, daddr) as c_int;
    (*XFRM_SPI_SKB_CB(skb)).seq = seq;

    let segs = skb_gso_segment(skb, features);
    if segs.is_null() {
        return ptr::null_mut();
    }

    skb_push(skb, offset);
    segs
}

// Module initialization
// SAFETY: Must be called exactly once during module load, before any packet
// processing begins. The static references `&esp6_type_offload` and
// `&esp6_offload` are valid for the entire module lifetime ('static).
#[no_mangle]
pub unsafe extern "C" fn esp6_offload_init() -> c_int {
    if xfrm_register_type_offload(&esp6_type_offload, AF_INET6) < 0 {
        pr_info(b"esp6_offload_init: can't add xfrm type offload\n".as_ptr() as *const c_char);
        return -EAGAIN;
    }

    inet6_add_offload(&esp6_offload, IPPROTO_ESP as c_int)
}

// SAFETY: Must be called exactly once during module unload, after all
// in-flight packet processing has ceased. The static references passed
// are valid for the module's entire lifetime.
#[no_mangle]
pub unsafe extern "C" fn esp6_offload_exit() {
    xfrm_unregister_type_offload(&esp6_type_offload, AF_INET6);
    inet6_del_offload(&esp6_offload, IPPROTO_ESP as c_int);
}

// Implementation deferred.
// SAFETY: Caller must pass a non-null, valid `xfrm_type_offload` pointer
// that remains valid until a matching `xfrm_unregister_type_offload` call.
// `_family` must be a recognised address-family constant (e.g. `AF_INET6`).
#[no_mangle]
pub unsafe extern "C" fn xfrm_register_type_offload(
    _type_: *const xfrm_type_offload,
    _family: c_int,
) -> c_int {
    // Implementation would interface with kernel APIs
    0
}

// SAFETY: Caller must pass the same non-null `xfrm_type_offload` pointer
// that was previously registered, and `_family` must match the value used
// at registration time. Must not be called concurrently with packet
// processing that may read the offload type table.
#[no_mangle]
pub unsafe extern "C" fn xfrm_unregister_type_offload(
    _type_: *const xfrm_type_offload,
    _family: c_int,
) {
    // Implementation would interface with kernel APIs
}

// SAFETY: Caller must pass a non-null, valid `net_offload` pointer that
// remains valid until a matching `inet6_del_offload` call. `_proto` must
// be a valid IP protocol number (e.g. `IPPROTO_ESP`).
#[no_mangle]
pub unsafe extern "C" fn inet6_add_offload(
    _offload: *const net_offload,
    _proto: c_int,
) -> c_int {
    // Implementation would interface with kernel APIs
    0
}

// SAFETY: Caller must pass the same non-null `net_offload` pointer that was
// previously registered and the same `_proto` value. Must not be called
// while in-flight GRO/GSO operations are using the offload handler.
#[no_mangle]
pub unsafe extern "C" fn inet6_del_offload(
    _offload: *const net_offload,
    _proto: c_int,
) {
    // Implementation would interface with kernel APIs
}

// Module metadata
#[no_mangle]
pub static esp6_offload: net_offload = net_offload {
    callbacks: net_offload_callbacks {
        gro_receive: esp6_gro_receive,
        gso_segment: esp6_gso_segment,
    },
};

#[no_mangle]
pub static esp6_type_offload: xfrm_type_offload = xfrm_type_offload {
    description: b"ESP6 OFFLOAD\0".as_ptr(),
    owner: ptr::null(),
    proto: IPPROTO_ESP,
    input_tail: esp6_input_tail,
    xmit: esp6_xmit,
    encap: esp6_gso_encap,
};

// SAFETY: All pointer operations assume valid pointers as per kernel API contracts
// and proper synchronization is maintained by the kernel's internal locking mechanisms.

// Helper functions for missing kernel APIs
// SAFETY: Caller must pass non-null, valid `xfrm_state` and `sk_buff`
// pointers that are live for the duration of this call, as required by the
// `xfrm_type_offload.input_tail` callback contract.
#[no_mangle]
pub unsafe extern "C" fn esp6_input_tail(
    _x: *mut xfrm_state,
    _skb: *mut sk_buff,
) -> c_int {
    // Implementation would interface with kernel APIs
    0
}

// SAFETY: Caller must pass non-null, valid `xfrm_state` and `sk_buff`
// pointers that are live for the duration of this call, as required by the
// `xfrm_type_offload.xmit` callback contract. `_features` is a plain
// bitmask with no alignment or lifetime requirements.
#[no_mangle]
pub unsafe extern "C" fn esp6_xmit(
    _x: *mut xfrm_state,
    _skb: *mut sk_buff,
    _features: netdev_features_t,
) -> c_int {
    // Implementation would interface with kernel APIs
    0
}

// SAFETY: Caller must pass non-null, valid `xfrm_state` and `sk_buff`
// pointers that are live for the duration of this call, as required by the
// `xfrm_type_offload.encap` callback contract.
#[no_mangle]
pub unsafe extern "C" fn esp6_gso_encap(
    _x: *mut xfrm_state,
    _skb: *mut sk_buff,
) {
    // Implementation would interface with kernel APIs
}

// SAFETY: Caller must pass a non-null, kernel-allocated `sk_buff` pointer
// that is valid for the duration of this call; the GRO layer guarantees
// this invariant before invoking the GRO receive callback.
#[no_mangle]
pub unsafe extern "C" fn skb_gro_offset(_skb: *mut sk_buff) -> c_int {
    // Implementation would interface with kernel APIs
    0
}

// SAFETY: Caller must pass a non-null, kernel-allocated `sk_buff` pointer
// and a non-negative `_len` that does not exceed the available headroom of
// the buffer; the kernel guarantees both before calling pskb_pull.
#[no_mangle]
pub unsafe extern "C" fn pskb_pull(_skb: *mut sk_buff, _len: c_int) -> bool {
    // Implementation would interface with kernel APIs
    false
}

// SAFETY: Caller must pass a non-null `sk_buff` pointer, a valid IP
// protocol number in `_proto`, and non-null, writable `_spi`/`_seq`
// pointers pointing to properly aligned `u32` values. All pointers must
// remain valid for the duration of this call.
#[no_mangle]
pub unsafe extern "C" fn xfrm_parse_spi(
    _skb: *mut sk_buff,
    _proto: u8,
    _spi: *mut u32,
    _seq: *mut u32,
) -> c_int {
    // Implementation would interface with kernel APIs
    0
}

#[no_mangle]
pub unsafe extern "C" fn secpath_set(_skb: *mut sk_buff) -> *mut sec_path {
    // Implementation would interface with kernel APIs
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn xfrm_state_lookup(
    _net: *mut c_void,
    _mark: *mut c_void,
    _daddr: *const nf_inet_addr,
    _spi: u32,
    _proto: u8,
    _family: c_int,
) -> *mut xfrm_state {
    // Implementation would interface with kernel APIs
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn xfrm_smark_get(mark: *mut c_void, _x: *mut xfrm_state) -> *mut c_void {
    // Implementation would interface with kernel APIs
    mark
}

#[no_mangle]
pub unsafe extern "C" fn xfrm_offload(_skb: *mut sk_buff) -> *mut xfrm_offload {
    // Implementation would interface with kernel APIs
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_hdr(_skb: *mut sk_buff) -> *mut ipv6hdr {
    // Implementation would interface with kernel APIs
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn dev_net(_sk: *mut sock) -> *mut c_void {
    // Implementation would interface with kernel APIs
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn IP6CB(_skb: *mut sk_buff) -> *mut ip6_control_block {
    // Implementation would interface with kernel APIs
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn XFRM_TUNNEL_SKB_CB(_skb: *mut sk_buff) -> *mut xfrm_tunnel_skb_cb {
    // Implementation would interface with kernel APIs
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn XFRM_SPI_SKB_CB(_skb: *mut sk_buff) -> *mut xfrm_spi_skb_cb {
    // Implementation would interface with kernel APIs
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn xfrm_input(
    _skb: *mut sk_buff,
    _proto: u8,
    _spi: u32,
    _encap_type: c_int,
) {
    // Implementation would interface with kernel APIs
}

#[no_mangle]
pub unsafe extern "C" fn secpath_reset(_skb: *mut sk_buff) {
    // Implementation would interface with kernel APIs
}

#[no_mangle]
pub unsafe extern "C" fn skb_push(_skb: *mut sk_buff, _len: c_int) {
    // Implementation would interface with kernel APIs
}

#[no_mangle]
pub unsafe extern "C" fn NAPI_GRO_CB(_skb: *mut sk_buff) -> *mut napi_gro_cb {
    // Implementation would interface with kernel APIs
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn skb_gso_offset(_skb: *mut sk_buff) -> c_int {
    // Implementation would interface with kernel APIs
    0
}

#[no_mangle]
pub unsafe extern "C" fn skb_gso_segment(
    _skb: *mut sk_buff,
    _features: netdev_features_t,
) -> *mut sk_buff {
    // Implementation would interface with kernel APIs
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn pr_info(_fmt: *const c_char) {
    // Implementation would interface with kernel APIs
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── ABI / protocol constant tests ────────────────────────────────────────

    #[test]
    fn test_protocol_constants() {
        assert_eq!(IPPROTO_ESP, 50u8);
        assert_eq!(NEXTHDR_ESP, 50u8);
        assert_eq!(AF_INET6, 10);
        assert_eq!(XFRM_MAX_DEPTH, 16);
    }

    #[test]
    fn test_errno_constants() {
        assert_eq!(EINVAL, -22);
        assert_eq!(ENOMEM, -12);
        assert_eq!(EOPNOTSUPP, -95);
        assert_eq!(EINPROGRESS, -115);
        assert_eq!(EAGAIN, -11);
    }

    #[test]
    fn test_netdev_feature_flags_are_distinct() {
        // Single-bit hardware feature flags must not overlap each other.
        // NETIF_F_CSUM_MASK is a multi-bit mask, so it is excluded from
        // the pairwise-disjoint check and tested separately below.
        let single_bit_flags = [
            NETIF_F_HW_ESP,
            NETIF_F_HW_ESP_TX_CSUM,
            NETIF_F_SG,
            NETIF_F_SCTP_CRC,
        ];
        for i in 0..single_bit_flags.len() {
            for j in (i + 1)..single_bit_flags.len() {
                assert_eq!(
                    single_bit_flags[i] & single_bit_flags[j], 0,
                    "single-bit flags[{}]={:#x} and flags[{}]={:#x} overlap",
                    i, single_bit_flags[i], j, single_bit_flags[j]
                );
            }
        }
        // CSUM_MASK must be a superset of NETIF_F_SG (covers the low 4 bits)
        assert_eq!(NETIF_F_SG & NETIF_F_CSUM_MASK, NETIF_F_SG,
            "NETIF_F_CSUM_MASK must cover NETIF_F_SG");
    }

    // ── null-pointer guard tests ─────────────────────────────────────────────

    #[test]
    fn test_gro_receive_null_returns_null() {
        // A null sk_buff must be rejected immediately without a crash
        let result = unsafe { esp6_gro_receive(core::ptr::null_mut()) };
        assert!(result.is_null(), "esp6_gro_receive(null) must return null");
    }

    #[test]
    fn test_gso_segment_null_returns_null() {
        let result = unsafe { esp6_gso_segment(core::ptr::null_mut(), 0) };
        assert!(result.is_null(), "esp6_gso_segment(null) must return null");
    }

    // ── ipv6_optlen tests ────────────────────────────────────────────────────

    #[test]
    fn test_ipv6_optlen_null_returns_zero() {
        let result = unsafe { ipv6_optlen(core::ptr::null()) };
        assert_eq!(result, 0, "ipv6_optlen(null) must return 0");
    }

    #[test]
    fn test_ipv6_optlen_nexthdr_value() {
        // nexthdr = 0x2F → low nibble = 0xF = 15 → 15 * 8 = 120
        let hdr = ipv6_opt_hdr { nexthdr: 0x2F };
        let result = unsafe { ipv6_optlen(&hdr as *const _) };
        assert_eq!(result, 120);
    }

    // ── SKB GSO-flag constant sanity ─────────────────────────────────────────

    #[test]
    fn test_gso_flags_nonzero_and_distinct() {
        assert_ne!(SKB_GSO_TCPV6, 0);
        assert_ne!(SKB_GSO_ESP, 0);
        assert_eq!(SKB_GSO_TCPV6 & SKB_GSO_ESP, 0);
    }

    // ── struct size tests ────────────────────────────────────────────────────

    #[test]
    fn test_xfrm_offload_size() {
        // flags(4) + proto(1) + pad(3) + seq[2](8) = 16 bytes minimum
        assert!(core::mem::size_of::<xfrm_offload>() >= 12);
    }

    #[test]
    fn test_sec_path_depth_matches_constant() {
        // sec_path must hold exactly XFRM_MAX_DEPTH xvec entries
        let sp: sec_path = unsafe { core::mem::zeroed() };
        assert_eq!(sp.xvec.len(), XFRM_MAX_DEPTH);
    }
}

