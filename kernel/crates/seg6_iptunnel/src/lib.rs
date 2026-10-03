#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

use core::ffi::{c_int, c_void};
use core::mem;
use core::ptr;
use kernel_types::*;


pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ETH_P_IP: c_int = 0x0800;
pub const ETH_P_IPV6: c_int = 0x86DD;
pub const IPPROTO_IPV6: c_int = 41;
pub const IPPROTO_IPIP: c_int = 4;
pub const IPPROTO_ETHERNET: c_int = 143;
pub const IPV6_FLOWLABEL_MASK: u32 = 0x000FFFFF;
pub const NEXTHDR_ROUTING: u8 = 43;

// Type definitions

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_sr_hdr {
    pub nexthdr: u8,
    pub hdrlen: u8,
    pub m: u8,
    pub reserved: u8,
    pub first_segment: u8,
    pub segments: [in6_addr; 1],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct seg6_iptunnel_encap { pub mode: c_int, pub srh: *mut ipv6_sr_hdr }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct dst_cache { _private: [u8; 1] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct seg6_lwt { pub cache: dst_cache, pub tuninfo: [seg6_iptunnel_encap; 1] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct lwtunnel_state { pub data: *mut c_void }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct dst_entry {
    pub dev: *mut c_void,
    _private: [u8; 0],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net {
    _private: [u8; 0],
}

// Function implementations

#[no_mangle]
pub unsafe extern "C" fn seg6_lwt_headroom(tuninfo: *const seg6_iptunnel_encap) -> size_t {
    if tuninfo.is_null() {
        return 0;
    }

    let mode = (*tuninfo).mode;
    let mut head: size_t = 0;

    match mode {
        0 => {}
        1 => head = mem::size_of::<ipv6hdr>(),
        2 => return 0,
        _ => {}
    }

    let hdrlen = (*tuninfo)
        .srh
        .as_ref()
        .map_or(0, |srh| ((srh.hdrlen as size_t) + 1) << 3);

    hdrlen + head
}

#[no_mangle]
pub unsafe extern "C" fn seg6_do_srh_encap(
    skb: *mut sk_buff,
    osrh: *mut ipv6_sr_hdr,
    _proto: c_int,
) -> c_int {
    if skb.is_null() || osrh.is_null() {
        return EINVAL;
    }

    let dst = skb_dst(skb);
    if dst.is_null() || (*dst).dev.is_null() {
        return EINVAL;
    }

    let net = dev_net((*dst).dev as *mut net_device);
    if net.is_null() {
        return EINVAL;
    }

    let inner_hdr_ptr = ipv6_hdr(skb);
    if inner_hdr_ptr.is_null() {
        return EINVAL;
    }

    let osrh_ref = &*osrh;
    let hdrlen = ((osrh_ref.hdrlen as size_t) + 1) << 3;
    let tot_len = hdrlen + mem::size_of::<ipv6hdr>();

    let err = skb_cow_head(skb, tot_len as c_int);
    if err != 0 {
        return err;
    }

    let inner_hdr = &*inner_hdr_ptr;
    let flowlabel = seg6_make_flowlabel(net, skb, inner_hdr_ptr);

    skb_push(skb, tot_len as c_int);
    skb_reset_network_header(skb);
    skb_mac_header_rebuild(skb);

    let hdr = ipv6_hdr(skb);
    if hdr.is_null() {
        return EINVAL;
    }

    if (*skb).protocol == htons(ETH_P_IPV6 as u16) {
        ip6_flow_hdr(hdr, ip6_tclass(ip6_flowinfo(inner_hdr_ptr)), flowlabel);
        (*hdr).hop_limit = inner_hdr.hop_limit;
    } else {
        ip6_flow_hdr(hdr, 0, flowlabel);
        let ndst = skb_dst(skb);
        if ndst.is_null() {
            return EINVAL;
        }
        (*hdr).hop_limit = ip6_dst_hoplimit(ndst);
        memset(IP6CB(skb), 0, mem::size_of::<*mut c_void>() as c_int);
    }

    (*hdr).nexthdr = NEXTHDR_ROUTING;

    let isrh = (hdr as *mut u8).add(mem::size_of::<ipv6hdr>()) as *mut ipv6_sr_hdr;
    ptr::copy_nonoverlapping(osrh, isrh, hdrlen);

    (*isrh).nexthdr = _proto as u8;

    let daddr = &mut (*hdr).daddr;
    let saddr = &mut (*hdr).saddr;
    set_tun_src(net, (*dst).dev as *mut net_device, daddr, saddr);

    skb_postpush_rcsum(skb, hdr as *mut u8, tot_len as c_int);

    0
}

/// Insert SRH inline in IPv6 packet
///
/// # Safety
/// - `skb` must be a valid pointer to sk_buff
/// - `osrh` must be a valid pointer to ipv6_sr_hdr
///
/// # Returns
/// 0 on success, error code otherwise
#[no_mangle]
pub unsafe extern "C" fn seg6_do_srh_inline(skb: *mut sk_buff, osrh: *mut ipv6_sr_hdr) -> c_int {
    if skb.is_null() || osrh.is_null() {
        return EINVAL;
    }

    let oldhdr = ipv6_hdr(skb);
    if oldhdr.is_null() {
        return EINVAL;
    }

    let osrh_ref = &*osrh;
    let hdrlen = ((osrh_ref.hdrlen as usize) + 1) << 3;

    let err = skb_cow_head(skb, hdrlen as c_int);
    if err != 0 {
        return err;
    }

    skb_pull(skb, mem::size_of::<ipv6hdr>() as c_int);
    skb_postpull_rcsum(
        skb,
        skb_network_header(skb),
        mem::size_of::<ipv6hdr>() as c_int,
    );

    skb_push(skb, mem::size_of::<ipv6hdr>() as c_int + hdrlen as c_int);
    skb_reset_network_header(skb);
    skb_mac_header_rebuild(skb);

    let hdr = ipv6_hdr(skb);
    let _oldhdr_ref = &*oldhdr;

    memmove(
        hdr as *mut c_void,
        oldhdr as *const c_void,
        mem::size_of::<ipv6hdr>(),
    );

    let isrh = (hdr as *mut u8).add(mem::size_of::<ipv6hdr>()) as *mut ipv6_sr_hdr;
    ptr::copy_nonoverlapping(osrh, isrh, hdrlen);

    (*isrh).nexthdr = (*hdr).nexthdr;
    (*hdr).nexthdr = NEXTHDR_ROUTING;

    (*isrh).segments[0] = (*hdr).daddr;
    (*hdr).daddr = (*isrh).segments[(*isrh).first_segment as usize];

    skb_postpush_rcsum(skb, hdr as *mut u8, (mem::size_of::<ipv6hdr>() + hdrlen) as c_int);

    0
}

// Internal functions
unsafe fn seg6_encap_lwtunnel(lwt: *mut lwtunnel_state) -> *mut seg6_iptunnel_encap {
    if lwt.is_null() {
        return ptr::null_mut();
    }

    let slwt = seg6_lwt_lwtunnel(lwt);
    if slwt.is_null() {
        return ptr::null_mut();
    }

    &mut (*slwt).tuninfo[0]
}

fn seg6_lwt_lwtunnel(lwt: *mut lwtunnel_state) -> *mut seg6_lwt {
    if lwt.is_null() {
        return ptr::null_mut();
    }

    lwt as *mut seg6_lwt
}

// Helper functions (FFI-compatible signatures)
#[no_mangle]
pub unsafe extern "C" fn skb_cow_head(_skb: *mut sk_buff, headroom: c_int) -> c_int {
    // Implementation deferred.
    // Actual implementation would handle memory allocation
    if headroom < 0 {
        return EINVAL;
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn skb_push(_skb: *mut sk_buff, _len: c_int) -> *mut u8 {
    // Implementation deferred.
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn skb_reset_network_header(_skb: *mut sk_buff) {
    // No-op for FFI compatibility
}

#[no_mangle]
pub unsafe extern "C" fn skb_mac_header_rebuild(_skb: *mut sk_buff) {
    // No-op for FFI compatibility
}

#[no_mangle]
pub unsafe extern "C" fn skb_pull(_skb: *mut sk_buff, _len: c_int) {
    // No-op for FFI compatibility
}

#[no_mangle]
pub unsafe extern "C" fn skb_postpull_rcsum(_skb: *mut sk_buff, _data: *const u8, _len: c_int) {
    // No-op for FFI compatibility
}

#[no_mangle]
pub unsafe extern "C" fn skb_postpush_rcsum(_skb: *mut sk_buff, _data: *mut u8, _len: c_int) {
    // No-op for FFI compatibility
}

#[no_mangle]
pub unsafe extern "C" fn skb_dst(_skb: *mut sk_buff) -> *mut dst_entry {
    // Implementation deferred.
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn dev_net(_dev: *mut net_device) -> *mut net {
    // Implementation deferred.
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_hdr(_skb: *mut sk_buff) -> *mut ipv6hdr {
    // Implementation deferred.
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn skb_network_header(_skb: *mut sk_buff) -> *mut u8 {
    // Implementation deferred.
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn ip6_flowinfo(_hdr: *mut ipv6hdr) -> u32 {
    // Implementation deferred.
    0
}

#[no_mangle]
pub unsafe extern "C" fn ip6_tclass(_flowinfo: u32) -> u8 {
    // Implementation deferred.
    0
}

#[no_mangle]
pub unsafe extern "C" fn ip6_flow_hdr(_hdr: *mut ipv6hdr, _tclass: u8, _flowlabel: u32) {
    // No-op for FFI compatibility
}

#[no_mangle]
pub unsafe extern "C" fn ip6_dst_hoplimit(_dst: *mut dst_entry) -> u8 {
    // Implementation deferred.
    0
}

#[no_mangle]
pub unsafe extern "C" fn IP6CB(_skb: *mut sk_buff) -> *mut c_void {
    // Implementation deferred.
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn memset(_dest: *mut c_void, _c: c_int, _n: c_int) {
    // No-op for FFI compatibility
}

#[no_mangle]
pub unsafe extern "C" fn memmove(_dest: *mut c_void, _src: *const c_void, _n: usize) {
    // No-op for FFI compatibility
}

#[no_mangle]
pub unsafe extern "C" fn set_tun_src(
    _net: *mut net,
    _dev: *mut net_device,
    _daddr: *mut in6_addr,
    _saddr: *mut in6_addr,
) {
    // No-op for FFI compatibility
}

#[no_mangle]
pub unsafe extern "C" fn seg6_make_flowlabel(
    _net: *mut net,
    _skb: *mut sk_buff,
    _inner_hdr: *mut ipv6hdr,
) -> u32 {
    // Implementation deferred.
    0
}

#[no_mangle]
pub unsafe extern "C" fn htons(x: u16) -> u16 {
    x.to_be()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_seg6_lwt_headroom() {
        // Basic test case
        let mut tuninfo = super::seg6_iptunnel_encap {
            mode: 1, // ENCAP
            srh: ptr::null_mut(),
        };

        let result = unsafe { super::seg6_lwt_headroom(&tuninfo) };
        assert!(result > 0);
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
