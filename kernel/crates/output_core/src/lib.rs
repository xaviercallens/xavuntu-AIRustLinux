#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

use kernel_types::*;

// Missing types from kernel headers
#[repr(C)]
#[derive(Copy, Clone)]
pub struct tun_key {
    pub tun_id: u64,
    pub iif: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct flowi4 {
    pub flowi4_iif: c_int,
    pub flowi4_oif: c_int,
    pub flowi4_tos: u8,
    pub flowi4_scope: u8,
    pub flowi4_proto: u8,
    pub flowi4_flags: u8,
    pub flowi4_tun_key: tun_key,
    pub flowi4_mark: u32,
    pub flowi4_secid: u32,
    pub flowi4_tun_flags: u8,
    pub flowi4_uid: u32,
    pub flowi4_saddr: in_addr,
    pub flowi4_daddr: in_addr,
    pub flowi4_fwmark: u32,
    pub flowi4_secmark: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct output_core {
    pub skb: *mut sk_buff,
    pub dev: *mut net_device,
    pub flowi: flowi4,
    pub iph: *mut iphdr,
    pub ipv6h: *mut ipv6hdr,
    pub udph: *mut udphdr,
    pub esp: *mut ip_esp_hdr,
    pub frag: *mut sk_buff,
    pub frag_head: *mut sk_buff,
    pub frag_prev: *mut sk_buff,
    pub frag_next: *mut sk_buff,
    pub frag_list: *mut sk_buff,
    pub frag_tail: *mut sk_buff,
    pub frag_count: c_int,
    pub frag_size: c_int,
    pub frag_offset: c_int,
    pub frag_len: c_int,
    pub frag_max_size: c_int,
    pub frag_max_offset: c_int,
    pub frag_max_len: c_int,
    pub frag_max_count: c_int,
}

#[no_mangle]
pub unsafe extern "C" fn output_core_init(oc: *mut output_core) {
    if oc.is_null() {
        return;
    }

    let oc = &mut *oc;
    oc.skb = core::ptr::null_mut();
    oc.dev = core::ptr::null_mut();
    oc.flowi = flowi4 {
        flowi4_iif: 0,
        flowi4_oif: 0,
        flowi4_tos: 0,
        flowi4_scope: 0,
        flowi4_proto: 0,
        flowi4_flags: 0,
        flowi4_tun_key: tun_key {
            tun_id: 0,
            iif: 0,
        },
        flowi4_mark: 0,
        flowi4_secid: 0,
        flowi4_tun_flags: 0,
        flowi4_uid: 0,
        flowi4_saddr: in_addr { s_addr: 0, ip: core::ptr::null_mut() },
        flowi4_daddr: in_addr { s_addr: 0, ip: core::ptr::null_mut() },
        flowi4_fwmark: 0,
        flowi4_secmark: 0,
    };
    oc.iph = core::ptr::null_mut();
    oc.ipv6h = core::ptr::null_mut();
    oc.udph = core::ptr::null_mut();
    oc.esp = core::ptr::null_mut();
    oc.frag = core::ptr::null_mut();
    oc.frag_head = core::ptr::null_mut();
    oc.frag_prev = core::ptr::null_mut();
    oc.frag_next = core::ptr::null_mut();
    oc.frag_list = core::ptr::null_mut();
    oc.frag_tail = core::ptr::null_mut();
    oc.frag_count = 0;
    oc.frag_size = 0;
    oc.frag_offset = 0;
    oc.frag_len = 0;
    oc.frag_max_size = 0;
    oc.frag_max_offset = 0;
    oc.frag_max_len = 0;
    oc.frag_max_count = 0;
}

#[no_mangle]
pub unsafe extern "C" fn output_core_free(oc: *mut output_core) {
    if oc.is_null() {
        return;
    }

    let oc = &mut *oc;
    oc.skb = core::ptr::null_mut();
    oc.dev = core::ptr::null_mut();
    oc.iph = core::ptr::null_mut();
    oc.ipv6h = core::ptr::null_mut();
    oc.udph = core::ptr::null_mut();
    oc.esp = core::ptr::null_mut();
    oc.frag = core::ptr::null_mut();
    oc.frag_head = core::ptr::null_mut();
    oc.frag_prev = core::ptr::null_mut();
    oc.frag_next = core::ptr::null_mut();
    oc.frag_list = core::ptr::null_mut();
    oc.frag_tail = core::ptr::null_mut();
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
