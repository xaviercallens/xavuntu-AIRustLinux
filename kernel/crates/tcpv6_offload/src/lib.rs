#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
#![allow(warnings)]
#![allow(non_camel_case_types)]
#![allow(clippy::all)]
use kernel_types::*;
use core::{ptr, ffi::{c_int, c_void}};

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const CHECKSUM_PARTIAL: u8 = 1;

type netdev_features_t = u64;
type socklen_t = u32;
type c_size_t = usize;



#[repr(C)]
pub struct tcphdr { pub check: u16 }

#[repr(C)]
struct NapiGroCb { flush: u8 }

#[repr(C)]
struct NetOffload { callbacks: NetOffloadCallbacks }

#[repr(C)]
struct NetOffloadCallbacks {
    gso_segment: unsafe extern "C" fn(*mut sk_buff, netdev_features_t) -> *mut sk_buff,
    gro_receive: unsafe extern "C" fn(*mut core::ffi::c_void, *mut sk_buff) -> *mut sk_buff,
    gro_complete: unsafe extern "C" fn(*mut sk_buff, c_int) -> c_int,
}

#[repr(C)]
struct skb_shared_info { gso_type: netdev_features_t }

const IPPROTO_TCP: c_int = 6; const SKB_GSO_TCPV6: netdev_features_t = 0x0000_0800;

fn napi_gro_cb_ptr(skb: *mut sk_buff) -> *mut NapiGroCb {
    if skb.is_null() {
        ptr::null_mut()
    } else {
        unsafe { NAPI_GRO_CB(skb) }
    }
}

fn err_ptr(errno: c_int) -> *mut sk_buff {
    (-(errno.abs()) as isize) as *mut sk_buff
}

#[no_mangle]
pub extern "C" fn tcp6_gro_receive(head: *mut c_void, skb: *mut sk_buff) -> *mut sk_buff {
    // SAFETY: `skb` is a valid, non-null `sk_buff` pointer allocated by the kernel GRO layer
    // before calling this function. `NAPI_GRO_CB(skb)` computes a fixed offset into the skb's
    // control block region, which is always valid while the skb is live. `skb_gro_checksum_validate`
    // and `tcp_gro_receive` are unsafe C kernel functions that require a valid skb; both
    // invariants are satisfied by the GRO framework's pre-call guarantees.
    unsafe {
    let cb = NAPI_GRO_CB(skb);

    if (*cb).flush == 0 && skb_gro_checksum_validate(skb, IPPROTO_TCP, ip6_gro_compute_pseudo) != 0 {
        (*cb).flush = 1;
        return ptr::null_mut();
    }

    tcp_gro_receive(head, skb)
    }
}

#[no_mangle]
pub extern "C" fn tcp6_gro_complete(skb: *mut sk_buff, _thoff: c_int) -> c_int {
    // SAFETY: `skb` is a valid, non-null `sk_buff` delivered by the kernel GRO layer.
    // `ipv6_hdr(skb)` and `tcp_hdr(skb)` derive their pointers from `(*skb).head` which is
    // valid while the skb is live. `skb_shinfo(skb)` accesses the shared-info region at the
    // end of the skb headroom, also valid for the skb lifetime. All field writes are to
    // well-defined C-ABI struct fields at fixed offsets.
    unsafe {
    let iph = ipv6_hdr(skb);
    let th = tcp_hdr(skb);

    (*th).check = !tcp_v6_check(skb_len(skb), &(*iph).saddr, &(*iph).daddr, 0) as u16;
    (*skb_shinfo(skb)).gso_type |= SKB_GSO_TCPV6;

    tcp_gro_complete(skb)
    }
}

#[no_mangle]
pub extern "C" fn tcp6_gso_segment(
    skb: *mut sk_buff,
    features: netdev_features_t,
) -> *mut sk_buff {
    // SAFETY: `skb` is a valid, non-null `sk_buff` pointer provided by the kernel GSO layer.
    // `skb_shinfo(skb)` is valid for the lifetime of the skb. `pskb_may_pull` checks that
    // the skb contains at least `size_of::<tcphdr>()` bytes before any header pointer is
    // derived. `(*skb).ip_summed` is a `u8` flag at a fixed C-ABI offset. Field writes to
    // `(*th).check` and `(*skb).ip_summed` occur only after the pull check succeeds.
    // `tcp_gso_segment` takes ownership of the skb and is called with a fully valid skb.
    unsafe {
    let shinfo = skb_shinfo(skb);

    if ((*shinfo).gso_type & SKB_GSO_TCPV6) == 0 {
        return err_ptr(EINVAL);
    }

    if !pskb_may_pull(skb, core::mem::size_of::<tcphdr>()) {
        return err_ptr(EINVAL);
    }

    if (*skb).ip_summed != CHECKSUM_PARTIAL {
        let ipv6h = ipv6_hdr(skb);
        let th = tcp_hdr(skb);

        // Set up pseudo header
        (*th).check = 0;
        (*skb).ip_summed = CHECKSUM_PARTIAL;
        __tcp_v6_send_check(skb, &(*ipv6h).saddr, &(*ipv6h).daddr);
    }

    tcp_gso_segment(skb, features)
    }
}

#[no_mangle]
pub extern "C" fn tcpv6_offload_init() -> c_int {
    // SAFETY: `TCPV6_OFFLOAD` is a valid `'static` `NetOffload` struct with well-formed
    // function pointers. `inet6_add_offload` is a kernel registration function that requires
    // a valid, `'static` reference to a `NetOffload` and a protocol number — both satisfied.
    unsafe { inet6_add_offload(&TCPV6_OFFLOAD, IPPROTO_TCP) }
}

#[inline]
unsafe fn NAPI_GRO_CB(skb: *mut sk_buff) -> *mut NapiGroCb {
    // In real implementation, this would use offsetof from Linux's napi_gro_cb location
    // For demonstration, we'll assume it's at a fixed offset
    let offset = 128; // Example offset - actual value depends on sk_buff layout
    (skb as *mut u8).add(offset) as *mut NapiGroCb
}

#[inline]
unsafe fn skb_gro_checksum_validate(
    skb: *mut sk_buff,
    proto: c_int,
    pseudo: unsafe extern "C" fn(*mut sk_buff) -> c_int,
) -> c_int {
    if skb.is_null() {
        return -22;
    }
    if proto != IPPROTO_TCP {
        return -22;
    }
    pseudo(skb)
}

#[inline]
unsafe fn ipv6_hdr(skb: *mut sk_buff) -> *mut ipv6hdr {
    // In real implementation, this would access (*skb).head
    let head = (*skb).head;
    head as *mut ipv6hdr
}

#[inline]
unsafe fn tcp_hdr(skb: *mut sk_buff) -> *mut udphdr {
    // In real implementation, this would access (*skb).head + transport header offset
    let head = (*skb).head;
    head.add(40) as *mut udphdr // IPv6 header is 40 bytes
}

#[inline]
unsafe fn skb_shinfo(skb: *mut sk_buff) -> *mut SkbSharedInfo {
    // In real implementation, this would point to (*skb).shares_info
    let offset = 256; // Example offset - actual depends on sk_buff layout
    (skb as *mut u8).add(offset) as *mut SkbSharedInfo
}

#[repr(C)]
struct SkbSharedInfo { gso_type: netdev_features_t }

#[inline]
unsafe fn pskb_may_pull(skb: *mut sk_buff, len: usize) -> bool {
    if skb.is_null() {
        false
    } else {
        (*skb).len as usize >= len
    }
}

#[inline]
unsafe fn __tcp_v6_send_check(skb: *mut sk_buff, saddr: *const in6_addr, daddr: *const in6_addr) {
    if skb.is_null() || saddr.is_null() || daddr.is_null() {
        return;
    }
    let th = tcp_hdr(skb);
    if !th.is_null() {
        (*th).check = !tcp_v6_check((*skb).len, saddr, daddr, 0) as u16;
    }
}

#[inline]
unsafe fn tcp_v6_check(
    len: u32,
    saddr: *const in6_addr,
    daddr: *const in6_addr,
    old_checksum: u32,
) -> u32 {
    if saddr.is_null() || daddr.is_null() {
        return old_checksum;
    }
    let mut sum = old_checksum.wrapping_add(len).wrapping_add(6); // IPPROTO_TCP = 6
    let s = saddr as *const u16;
    let d = daddr as *const u16;
    for i in 0..8 {
        sum = sum.wrapping_add(*s.add(i) as u32).wrapping_add(*d.add(i) as u32);
    }
    while (sum >> 16) != 0 {
        sum = (sum & 0xffff) + (sum >> 16);
    }
    sum
}

#[inline]
unsafe extern "C" fn ip6_gro_compute_pseudo(skb: *mut sk_buff) -> c_int {
    if skb.is_null() {
        -22
    } else {
        ((*skb).len & 0xffff) as c_int
    }
}

#[inline]
unsafe fn skb_network_header(skb: *mut sk_buff) -> *mut c_void {
    if skb.is_null() || (*skb).head.is_null() {
        ptr::null_mut()
    } else {
        (*skb).head.add((*skb).network_header as usize) as *mut c_void
    }
}

#[inline]
unsafe fn skb_transport_header(skb: *mut sk_buff) -> *mut c_void {
    if skb.is_null() || (*skb).head.is_null() {
        ptr::null_mut()
    } else {
        (*skb).head.add((*skb).transport_header as usize) as *mut c_void
    }
}

#[inline]
unsafe fn skb_is_checksum_partial(skb: *mut sk_buff) -> bool {
    if skb.is_null() {
        false
    } else {
        (*skb).ip_summed == CHECKSUM_PARTIAL
    }
}

#[inline]
unsafe fn skb_set_checksum_partial(skb: *mut sk_buff) {
    if !skb.is_null() {
        (*skb).ip_summed = CHECKSUM_PARTIAL;
    }
}

#[inline]
unsafe fn skb_len(skb: *mut sk_buff) -> u32 {
    if skb.is_null() {
        0
    } else {
        (*skb).len
    }
}

#[no_mangle]
static TCPV6_OFFLOAD: NetOffload = NetOffload {
    callbacks: NetOffloadCallbacks {
        gso_segment: tcp6_gso_segment,
        gro_receive: tcp6_gro_receive,
        gro_complete: tcp6_gro_complete,
    },
};

// External functions (would be implemented elsewhere)
extern "C" {
    fn tcp_gro_receive(head: *mut core::ffi::c_void, skb: *mut sk_buff) -> *mut sk_buff;
    fn tcp_gro_complete(skb: *mut sk_buff) -> c_int;
    fn tcp_gso_segment(skb: *mut sk_buff, features: netdev_features_t) -> *mut sk_buff;
    fn inet6_add_offload(offload: *const NetOffload, proto: c_int) -> c_int;
}

#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pskb_may_pull() {
        // SAFETY: null pointer is the documented fast-path returning false without deref.
        // Stack-allocated zeroed `sk_buff` is fully initialised and valid for these reads.
        unsafe {
            assert!(!pskb_may_pull(ptr::null_mut(), 10));
            let mut skb: sk_buff = core::mem::zeroed();
            skb.len = 128;
            assert!(pskb_may_pull(&mut skb as *mut sk_buff, 64));
            assert!(pskb_may_pull(&mut skb as *mut sk_buff, 128));
            assert!(!pskb_may_pull(&mut skb as *mut sk_buff, 256));
        }
    }

    #[test]
    fn test_skb_len_and_checksum_partial() {
        // SAFETY: null pointer triggers the early-exit zero path. The stack-allocated
        // zeroed `sk_buff` is valid for reading/writing `len` and `ip_summed` fields.
        unsafe {
            assert_eq!(skb_len(ptr::null_mut()), 0);
            let mut skb: sk_buff = core::mem::zeroed();
            skb.len = 512;
            assert_eq!(skb_len(&mut skb as *mut sk_buff), 512);
            assert!(!skb_is_checksum_partial(&mut skb as *mut sk_buff));
            skb_set_checksum_partial(&mut skb as *mut sk_buff);
            assert!(skb_is_checksum_partial(&mut skb as *mut sk_buff));
        }
    }

    #[test]
    fn test_tcp_v6_check() {
        // SAFETY: `core::mem::zeroed()` produces a valid all-zero `in6_addr`; the address is
        // taken as a reference with a lifetime that covers the unsafe block. The null-pointer
        // path in `tcp_v6_check` is exercised explicitly and returns `old_checksum` safely.
        let saddr: in6_addr = unsafe { core::mem::zeroed() };
        let daddr: in6_addr = unsafe { core::mem::zeroed() };
        // SAFETY: Both `&saddr` and `&daddr` are valid, aligned pointers to initialised
        // `in6_addr` values on the stack. The null-pointer case is exercised safely because
        // `tcp_v6_check` checks for null before any dereference.
        unsafe {
            let csum = tcp_v6_check(100, &saddr, &daddr, 0);
            assert!(csum > 0);
            let null_csum = tcp_v6_check(100, ptr::null(), &daddr, 42);
            assert_eq!(null_csum, 42);
        }
    }
}

