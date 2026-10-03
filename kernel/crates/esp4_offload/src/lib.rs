#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons)]

use core::{ptr, ffi::{c_int, c_void}, panic::PanicInfo};

type size_t = usize;
pub type netdev_features_t = u32;
pub type xfrm_address_t = [u8; 16];
pub type socklen_t = u32;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const EINPROGRESS: c_int = -115;
pub const EOPNOTSUPP: c_int = -95;
pub const ENOSYS: c_int = -38;
pub const EAGAIN: c_int = -35;

#[repr(C)]
pub struct list_head { pub next: *mut list_head, pub prev: *mut list_head }

#[repr(C)]
pub struct net_device { _private: [u8; 0] }

#[repr(C)]
pub struct sk_buff {
    pub dev: *mut net_device,
    pub mark: u32,
    _private: [u8; 0],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct skb_shared_info { pub gso_type: u16, _private: [u8; 0] }

#[repr(C)]
pub struct xfrm_offload { pub flags: u32, _private: [u8; 0] }

#[repr(C)]
pub struct sec_path {
    pub len: u32,
    pub olen: u32,
    pub xvec: [*mut xfrm_state; 8],
}

#[repr(C)]
pub struct xfrm_state { _private: [u8; 0] }

#[repr(C)]
pub struct iphdr {
    _pad0: [u8; 16],
    pub daddr: u32,
    _pad1: [u8; 1],
    pub protocol: u8,
}

#[repr(C)]
pub struct ip_esp_hdr { _private: [u8; 0] }

#[repr(C)]
pub struct net_offload { _private: [u8; 0] }

#[repr(C)]
pub struct xfrm_type_offload { _private: [u8; 0] }

#[repr(C)]
pub struct napi_gro_cb {
    pub same_flow: u8,
    pub flush: u8,
    _private: [u8; 0],
}

#[repr(C)]
pub struct xfrm_tunnel_skb_cb_tunnel { pub ip4: *mut c_void }

#[repr(C)]
pub struct xfrm_tunnel_skb_cb { pub tunnel: xfrm_tunnel_skb_cb_tunnel }

#[repr(C)]
pub struct xfrm_spi_skb_cb {
    pub family: c_int,
    pub daddroff: u16,
    pub seq: u32,
}

pub type gro_receive_t = extern "C" fn(*mut list_head, *mut sk_buff) -> *mut sk_buff;
pub type gso_segment_t = extern "C" fn(*mut sk_buff, netdev_features_t) -> *mut sk_buff;

pub const IPPROTO_ESP: c_int = 50;
pub const AF_INET: c_int = 2;
pub const XFRM_MAX_DEPTH: u32 = 8;
pub const CRYPTO_DONE: u32 = 1 << 0;
pub const XFRM_GRO: u32 = 1 << 1;

const fn offset_of_iphdr_daddr() -> u16 {
    16
}

unsafe extern "C" {
    fn skb_gro_offset(skb: *mut sk_buff) -> c_int;
    fn pskb_pull(skb: *mut sk_buff, len: c_int) -> *mut sk_buff;
    fn xfrm_parse_spi(skb: *mut sk_buff, proto: c_int, spi: *mut u32, seq: *mut u32) -> c_int;
    fn xfrm_offload(skb: *mut sk_buff) -> *mut xfrm_offload;
    fn secpath_set(skb: *mut sk_buff) -> *mut sec_path;
    fn xfrm_state_lookup(
        net: *mut c_void,
        mark: u32,
        daddr: *mut xfrm_address_t,
        spi: u32,
        proto: c_int,
        family: c_int,
    ) -> *mut xfrm_state;
    fn xfrm_smark_get(mark: u32, x: *mut xfrm_state) -> u32;
    fn secpath_reset(skb: *mut sk_buff);
    fn xfrm_input(skb: *mut sk_buff, proto: c_int, spi: u32, encap_type: c_int);
    fn NAPI_GRO_CB(skb: *mut sk_buff) -> *mut napi_gro_cb;
    fn skb_push(skb: *mut sk_buff, len: c_int) -> *mut sk_buff;
    fn ip_esp_hdr(skb: *mut sk_buff) -> *mut ip_esp_hdr;
    fn ip_hdr(skb: *mut sk_buff) -> *mut iphdr;
    fn skb_network_offset(skb: *mut sk_buff) -> c_int;
    fn __skb_push(skb: *mut sk_buff, len: c_int) -> *mut sk_buff;
    fn skb_mac_gso_segment(skb: *mut sk_buff, features: netdev_features_t) -> *mut sk_buff;
    fn skb_shinfo(skb: *mut sk_buff) -> *mut skb_shared_info;
    fn inet_offloads(proto: c_int) -> *mut net_offload;
    fn xfrm_register_type_offload(type_: *mut xfrm_type_offload, family: c_int) -> c_int;
    fn inet_add_offload(ops: *mut net_offload, proto: c_int) -> c_int;
    fn xfrm_unregister_type_offload(type_: *mut xfrm_type_offload, family: c_int);
    fn inet_del_offload(ops: *mut net_offload, proto: c_int);
    fn kmalloc(size: size_t, flags: c_int) -> *mut c_void;
    fn kfree(ptr: *mut c_void);
    fn dev_net(dev: *mut net_device) -> *mut c_void;
    fn XFRM_TUNNEL_SKB_CB(skb: *mut sk_buff) -> *mut xfrm_tunnel_skb_cb;
    fn XFRM_SPI_SKB_CB(skb: *mut sk_buff) -> *mut xfrm_spi_skb_cb;
    fn ERR_PTR(err: c_int) -> *mut sk_buff;
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}

#[no_mangle]
pub unsafe extern "C" fn esp4_gro_receive(head: *mut list_head, skb: *mut sk_buff) -> *mut sk_buff {
    let _ = head;
    let _ = offset_of_iphdr_daddr();

    let offset = unsafe { skb_gro_offset(skb) };
    if offset < 0 {
        return ptr::null_mut();
    }

    if unsafe { pskb_pull(skb, offset) }.is_null() {
        return ptr::null_mut();
    }

    let mut spi: u32 = 0;
    let mut seq: u32 = 0;
    if unsafe { xfrm_parse_spi(skb, IPPROTO_ESP, &mut spi, &mut seq) } != 0 {
        return ptr::null_mut();
    }

    let xo_ptr = unsafe { xfrm_offload(skb) };
    if xo_ptr.is_null() || (unsafe { (*xo_ptr).flags } & CRYPTO_DONE) == 0 {
        let sp = unsafe { secpath_set(skb) };
        if sp.is_null() {
            return ptr::null_mut();
        }
    }

    skb
}
