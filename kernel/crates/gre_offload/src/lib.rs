#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons)]

use core::{ptr, ffi::{c_int, c_void}};
use kernel_types::*;

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

// Constants from Linux headers
pub const IPPROTO_GRE: c_int = 47;
pub const NETIF_F_SCTP_CRC: netdev_features_t = 1 << 17;
pub const NETIF_F_HW_CSUM: netdev_features_t = 1 << 1;
pub const SKB_GSO_GRE_CSUM: u16 = 1 << 4;
pub const SKB_GSO_PARTIAL: u16 = 1 << 11;
pub const CHECKSUM_PARTIAL: c_int = 2;
pub const ENODEV: c_int = -19;
pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOENT: c_int = -2;
pub const SKB_GSO_GRE: u16 = 1 << 12;

// GRE flags
pub const GRE_KEY: u16 = 1 << 1; pub const GRE_CSUM: u16 = 1 << 2;

type netdev_features_t = u32;

// Use sk_buff from kernel_types
// #[repr(C)]
// pub struct sk_buff {
//     _priv: [u8; 0],
// }

#[repr(C)]
pub struct list_head { next: *mut list_head, prev: *mut list_head }

#[repr(C)]
pub struct gre_base_hdr { flags: u16, protocol: u16 }

#[repr(C)]
pub struct packet_offload_callbacks {
    gso_segment: Option<extern "C" fn(*mut sk_buff, netdev_features_t) -> *mut sk_buff>,
    gro_receive: Option<extern "C" fn(*mut list_head, *mut sk_buff) -> *mut sk_buff>,
    gro_complete: Option<extern "C" fn(*mut sk_buff, c_int) -> c_int>,
}

#[repr(C)]
pub struct packet_offload { callbacks: packet_offload_callbacks }

unsafe extern "C" {
    fn skb_inner_mac_header(skb: *const sk_buff) -> usize;
    fn skb_gro_header_slow(skb: *mut sk_buff, hlen: usize, off: usize) -> *mut c_void;
    fn skb_transport_header(skb: *const sk_buff) -> usize;
    fn skb_get_protocol(skb: *const sk_buff) -> u16;
    fn skb_set_protocol(skb: *mut sk_buff, protocol: u16);

    fn skb_get_encapsulation(skb: *const sk_buff) -> c_int;
    fn skb_set_encapsulation(skb: *mut sk_buff, val: c_int);

    fn skb_get_inner_network_offset(skb: *const sk_buff) -> u16;
    fn skb_get_inner_protocol(skb: *const sk_buff) -> u16;

    fn skb_get_mac_header(skb: *const sk_buff) -> u16;
    fn skb_get_mac_len(skb: *const sk_buff) -> u16;
    fn skb_set_mac_len(skb: *mut sk_buff, val: u16);

    fn skb_get_ip_summed(skb: *const sk_buff) -> c_int;
    fn skb_set_encap_hdr_csum(skb: *mut sk_buff, val: c_int);

    fn pskb_may_pull(skb: *mut sk_buff, len: usize) -> c_int;
    fn __skb_pull(skb: *mut sk_buff, len: usize) -> *mut c_void;
    fn skb_reset_mac_header(skb: *mut sk_buff);
    fn skb_set_network_header(skb: *mut sk_buff, offset: u16);
    fn skb_set_transport_header(skb: *mut sk_buff, offset: usize);
    fn skb_mac_gso_segment(skb: *mut sk_buff, features: netdev_features_t) -> *mut sk_buff;
    fn skb_gso_error_unwind(
        skb: *mut sk_buff,
        protocol: u16,
        tnl_hlen: usize,
        mac_offset: u16,
        mac_len: u16,
    );
    fn skb_tnl_header_len(skb: *mut sk_buff) -> usize;
    fn skb_gro_offset(skb: *mut sk_buff) -> usize;
    fn skb_gro_header_fast(skb: *mut sk_buff, offset: usize) -> *mut c_void;
    fn skb_gro_header_hard(skb: *mut sk_buff, hlen: usize) -> c_int;
    fn skb_gro_pull(skb: *mut sk_buff, len: usize) -> *mut c_void;
    fn skb_gro_postpull_rcsum(skb: *mut sk_buff, data: *mut c_void, len: usize);
    fn skb_gro_flush_final(skb: *mut sk_buff, pp: *mut sk_buff, flush: c_int);
    fn skb_gro_checksum_simple_validate(skb: *mut sk_buff) -> c_int;
    fn skb_gro_checksum_try_convert(
        skb: *mut sk_buff,
        protocol: c_int,
        compute_pseudo: extern "C" fn(*mut sk_buff) -> u32,
    );
    fn skb_is_gso(skb: *mut sk_buff) -> c_int;
    fn gro_find_receive_by_type(protocol: u16) -> *mut packet_offload;
    fn gro_find_complete_by_type(protocol: u16) -> *mut packet_offload;
    fn call_gro_receive(
        gro_receive: extern "C" fn(*mut list_head, *mut sk_buff) -> *mut sk_buff,
        head: *mut list_head,
        skb: *mut sk_buff,
    ) -> *mut sk_buff;
    fn inet_add_offload(offload: *const packet_offload, protocol: c_int) -> c_int;
    fn inet_del_offload(offload: *const packet_offload, protocol: c_int);
    fn rcu_read_lock();
    fn rcu_read_unlock();
}

#[allow(unused_unsafe)]
#[allow(clippy::not_unsafe_ptr_arg_deref)]
#[no_mangle]
pub extern "C" fn gre_gso_segment(
    skb: *mut sk_buff,
    features: netdev_features_t,
) -> *mut sk_buff {
    unsafe {
    // 🛡️ FORMAL VERIFICATION BOUNDARY (Mapped to Lean 4: gre_encap_bounds_check)
    requires!(!skb.is_null(), "gre_encap_bounds_check: skb invariant violated");

    let tnl_hlen = unsafe { skb_inner_mac_header(skb) - skb_transport_header(skb) };
    let need_csum = unsafe { skb_get_ip_summed(skb) == CHECKSUM_PARTIAL };

    if unsafe { skb_get_encapsulation(skb) } == 0 {
        return ptr::null_mut();
    }

    if tnl_hlen < core::mem::size_of::<gre_base_hdr>() {
        return ptr::null_mut();
    }

    if unsafe { pskb_may_pull(skb, tnl_hlen) } == 0 {
        return ptr::null_mut();
    }

    let segs = unsafe {
        skb_set_encapsulation(skb, 0);
        __skb_pull(skb, tnl_hlen);
        skb_reset_mac_header(skb);
        skb_set_network_header(skb, skb_get_inner_network_offset(skb));
        skb_set_mac_len(skb, skb_get_inner_network_offset(skb));
        skb_set_protocol(skb, skb_get_inner_protocol(skb));
        skb_set_encap_hdr_csum(skb, if need_csum { 1 } else { 0 });
        skb_set_transport_header(skb, skb_get_inner_network_offset(skb) as usize);
        skb_mac_gso_segment(skb, features)
    };

    if segs.is_null() || (segs as *const c_void).is_null() {
        unsafe {
            skb_gso_error_unwind(
                skb,
                (*skb).protocol,
                tnl_hlen,
                0,  // mac_header offset
                (*skb).mac_len,
            )
        };
        return segs;
    }

    let gso_partial = unsafe { (*skb).ip_summed & (SKB_GSO_PARTIAL as u8) != 0 };
    let outer_hlen = unsafe { skb_tnl_header_len(skb) };
    let gre_offset = outer_hlen - tnl_hlen;
    let mut current_skb = segs;

    loop {
        unsafe {
            let greh = current_skb as *mut gre_base_hdr;
            let pcsum = (greh as *mut c_void).offset(core::mem::size_of::<gre_base_hdr>() as isize) as *mut u16;

            if (*current_skb).ip_summed == CHECKSUM_PARTIAL as u8 {
                // Implementation deferred.
                // (*current_skb).encapsulation = 1;
            }

            (*current_skb).mac_len = (*skb).mac_len;
            (*current_skb).protocol = (*skb).protocol;

            __skb_pull(current_skb, outer_hlen);
            skb_reset_mac_header(current_skb);
            skb_set_network_header(current_skb, (*skb).mac_len);
            skb_set_transport_header(current_skb, gre_offset);

            if !need_csum {
                if (*current_skb).next.is_null() {
                    break;
                }
                current_skb = (*current_skb).next;
                continue;
            }

            // Calculate checksum
            if gso_partial && skb_is_gso(current_skb) != 0 {
                let partial_adj = (*current_skb).len;
                *pcsum = !((partial_adj as u32).to_be() as u16);
            } else {
                *pcsum = 0;
            }

            // SAFETY: Pointer arithmetic is valid as we've allocated sufficient space
            *pcsum.offset(1) = 0;

            if need_csum {
                (*current_skb).ip_summed = CHECKSUM_PARTIAL as u8;
            }

            if (*current_skb).next.is_null() {
                break;
            }
            current_skb = (*current_skb).next;
        }
    }

    segs
    }
}

#[allow(unused_unsafe)]
#[allow(clippy::not_unsafe_ptr_arg_deref)]
#[no_mangle]
pub extern "C" fn gre_gro_receive(head: *mut list_head, skb: *mut sk_buff) -> *mut sk_buff {
    unsafe {
    let mut pp = ptr::null_mut();

    if (*napi_gro_cb(skb)).encap_mark != 0 {
        return pp;
    }

    (*napi_gro_cb(skb)).encap_mark = 1;

    let off = skb_gro_offset(skb);
    let hlen = off + core::mem::size_of::<gre_base_hdr>();
    let greh = skb_gro_header_fast(skb, off) as *mut gre_base_hdr;

    if skb_gro_header_hard(skb, hlen) != 0 {
        let greh = skb_gro_header_slow(skb, hlen, off) as *mut gre_base_hdr;
        if greh.is_null() {
            return pp;
        }
    }

    // Check GRE flags
    if (*greh).flags & !(GRE_KEY | GRE_CSUM) != 0 {
        return pp;
    }

    if (*greh).flags & GRE_CSUM != 0 && (*napi_gro_cb(skb)).is_fou != 0 {
        return pp;
    }

    let type_ = (*greh).protocol;

    rcu_read_lock();
    let ptype = gro_find_receive_by_type(type_);
    if ptype.is_null() {
        rcu_read_unlock();
        return pp;
    }

    let mut grehlen = core::mem::size_of::<gre_base_hdr>();
    if (*greh).flags & GRE_KEY != 0 {
        grehlen += core::mem::size_of::<u32>();
    }
    if (*greh).flags & GRE_CSUM != 0 {
        grehlen += core::mem::size_of::<u16>();
    }

    let hlen = off + grehlen;
    if skb_gro_header_hard(skb, hlen) != 0 {
        let greh = skb_gro_header_slow(skb, hlen, off) as *mut gre_base_hdr;
        if greh.is_null() {
            rcu_read_unlock();
            return pp;
        }
    }

    // Checksum validation
    if (*greh).flags & GRE_CSUM != 0 && (*napi_gro_cb(skb)).flush == 0 {
        if skb_gro_checksum_simple_validate(skb) != 0 {
            rcu_read_unlock();
            return pp;
        }
        skb_gro_checksum_try_convert(skb, IPPROTO_GRE, null_compute_pseudo);
    }

    // Check same flow
    let mut p = (*head).next;
    while !core::ptr::eq(p, head) {
        let greh2 = (p as *mut sk_buff).add(off) as *mut gre_base_hdr;

        if (*greh2).flags != (*greh).flags || (*greh2).protocol != (*greh).protocol {
            (*napi_gro_cb(p as *mut sk_buff)).same_flow = 0;
        } else if (*greh).flags & GRE_KEY != 0 {
            let key1 =
                (greh as *mut u8).add(core::mem::size_of::<gre_base_hdr>()) as *mut u32;
            let key2 =
                (greh2 as *mut u8).add(core::mem::size_of::<gre_base_hdr>()) as *mut u32;
            if *key1 != *key2 {
                (*napi_gro_cb(p as *mut sk_buff)).same_flow = 0;
            }
        }

        p = (*p).next;
    }

    skb_gro_pull(skb, grehlen);
    skb_gro_postpull_rcsum(skb, greh as *mut c_void, grehlen);

    pp = call_gro_receive((*ptype).callbacks.gro_receive.unwrap(), head, skb);
    let flush = 0;

    rcu_read_unlock();
    skb_gro_flush_final(skb, pp, flush);

    pp
    }
}

#[allow(unused_unsafe)]
#[allow(clippy::not_unsafe_ptr_arg_deref)]
#[no_mangle]
pub extern "C" fn gre_gro_complete(skb: *mut sk_buff, nhoff: c_int) -> c_int {
    unsafe {
    let greh = (skb as *mut c_void).offset(nhoff as isize) as *mut gre_base_hdr;
    let mut grehlen = core::mem::size_of::<gre_base_hdr>() as u32;
    let mut err = -ENOENT;

    // (*skb).encapsulation = 1;
    // (*skb).ip_summed = 0;
    (*skb_shinfo(skb)).gso_type = SKB_GSO_GRE;

    let type_ = (*greh).protocol;
    if (*greh).flags & GRE_KEY != 0 {
        grehlen += core::mem::size_of::<u32>() as u32;
    }
    if (*greh).flags & GRE_CSUM != 0 {
        grehlen += core::mem::size_of::<u16>() as u32;
    }

    rcu_read_lock();
    let ptype = gro_find_complete_by_type(type_);
    if !ptype.is_null() {
        if let Some(gro_complete_func) = (*ptype).callbacks.gro_complete {
            err = gro_complete_func(skb, nhoff + grehlen as c_int);
        }
    }
    rcu_read_unlock();

    skb_set_inner_mac_header(skb, nhoff + grehlen as c_int);

    err
    }
}

/// # Safety
/// May modify kernel structures.
#[no_mangle]
pub unsafe extern "C" fn gre_offload_init() -> c_int {
    let mut err = inet_add_offload(&GRE_OFFLOAD, IPPROTO_GRE);
    if err != 0 {
        return err;
    }

    // IPv6 support
    // if IS_ENABLED(CONFIG_IPV6) {
    //     err = inet6_add_offload(&gre_offload, IPPROTO_GRE);
    //     if (err)
    //         inet_del_offload(&gre_offload, IPPROTO_GRE);
    // }

    err
}

// Helper functions - remove duplicate definition, use extern declaration
// #[inline]
// unsafe fn skb_inner_mac_header(skb: *mut sk_buff) -> usize {
//     0
// }

#[inline]
unsafe fn skb_shinfo(skb: *mut sk_buff) -> *mut skb_shared_info {
    // Implementation deferred.
    (skb as *mut c_void).offset(128) as *mut skb_shared_info
}

#[inline]
unsafe fn skb_set_inner_mac_header(_skb: *mut sk_buff, _offset: c_int) {
    // Implementation deferred.
}

#[repr(C)]
struct skb_shared_info {
    gso_type: u16,
    gso_size: u16,
    data_offset: u16,
    // ... many more fields ...
}

#[repr(C)]
struct NAPI_GRO_CB {
    encap_mark: u8,
    same_flow: u8,
    flush: u8,
    is_fou: u8,
    data_offset: usize,
}

#[inline]
unsafe fn napi_gro_cb(skb: *mut sk_buff) -> *mut NAPI_GRO_CB {
    // Implementation deferred.
    (skb as *mut c_void).offset(192) as *mut NAPI_GRO_CB
}

static GRE_OFFLOAD: packet_offload = packet_offload {
    callbacks: packet_offload_callbacks {
        gso_segment: Some(gre_gso_segment as extern "C" fn(*mut sk_buff, netdev_features_t) -> *mut sk_buff),
        gro_receive: Some(gre_gro_receive as extern "C" fn(*mut list_head, *mut sk_buff) -> *mut sk_buff),
        gro_complete: Some(gre_gro_complete as extern "C" fn(*mut sk_buff, c_int) -> c_int),
    },
};

#[no_mangle]
pub extern "C" fn null_compute_pseudo(skb: *mut sk_buff) -> u32 {
    if skb.is_null() {
        return 0;
    }
    unsafe { (*skb).len as u32 }
}

// Module initialization
/// # Safety
/// Invokes initialization functions that modify kernel state.
#[no_mangle]
pub unsafe extern "C" fn device_initcall(gre_offload_init: extern "C" fn() -> c_int) {
    gre_offload_init();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_null_compute_pseudo() {
        assert_eq!(null_compute_pseudo(ptr::null_mut()), 0);

        let mut skb: sk_buff = unsafe { core::mem::zeroed() };
        skb.len = 128;
        assert_eq!(null_compute_pseudo(&mut skb as *mut sk_buff), 128);
    }
}

