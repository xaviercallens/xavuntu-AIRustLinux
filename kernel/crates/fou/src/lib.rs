#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]

use core::ffi::{c_int, c_void};
use core::ptr;
use kernel_types::*;

pub const FOU_F_REMCSUM_NOPARTIAL: u8 = 1 << 0;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct list_head { pub next: *mut list_head, pub prev: *mut list_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct rcu_head {
    pub next: *mut rcu_head,
    pub func: Option<unsafe extern "C" fn(*mut rcu_head)>,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct guehdr {
    pub version: u8,
    pub hlen: u8,
    pub proto_ctype: u8,
    pub flags: u8,
    pub control: u8,
    pub _pad: [u8; 3],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fou {
    pub sock: *mut sock,
    pub protocol: u8,
    pub flags: u8,
    pub port: u16,
    pub family: u8,
    pub type_: u16,
    pub list: list_head,
    pub rcu: rcu_head,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fou_net { pub fou_list: list_head, pub fou_lock: *mut c_void }

unsafe extern "C" {
    fn ip_hdr(skb: *mut sk_buff) -> *mut iphdr;
    fn ipv6_hdr(skb: *mut sk_buff) -> *mut ipv6hdr;
    fn udp_hdr(skb: *mut sk_buff) -> *mut udphdr;

    fn __skb_pull(skb: *mut sk_buff, len: usize) -> *mut u8;
    fn skb_postpull_rcsum(skb: *mut sk_buff, start: *const c_void, len: usize);
    fn iptunnel_pull_offloads(skb: *mut sk_buff) -> c_int;
    fn kfree_skb(skb: *mut sk_buff);

    fn pskb_may_pull(skb: *mut sk_buff, len: usize) -> bool;
    fn skb_remcsum_process(
        skb: *mut sk_buff,
        ptr: *mut c_void,
        start: u16,
        offset: u16,
        nopartial: bool,
    );

    fn ntohs(v: u16) -> u16;
}

#[no_mangle]
pub unsafe extern "C" fn fou_recv_pull(skb: *mut sk_buff, fou: *mut fou, len: usize) -> c_int {
    if skb.is_null() || fou.is_null() {
        return -22;
    }

    let fou_ref = &*fou;

    if fou_ref.family == 0x02 {
        let ip = ip_hdr(skb);
        if ip.is_null() {
            return -22;
        }
        let tot_len = (*ip).tot_len;
        (*ip).tot_len = (ntohs(tot_len).wrapping_sub(len as u16)).to_be();
    } else if fou_ref.family == 0x0a {
        let ip6 = ipv6_hdr(skb);
        if ip6.is_null() {
            return -22;
        }
        let payload_len = (*ip6).payload_len;
        (*ip6).payload_len = (ntohs(payload_len).wrapping_sub(len as u16)).to_be();
    }

    __skb_pull(skb, len);
    skb_postpull_rcsum(skb, udp_hdr(skb) as *const c_void, len);
    iptunnel_pull_offloads(skb)
}

#[no_mangle]
pub unsafe extern "C" fn fou_udp_recv(_sk: *mut sock, skb: *mut sk_buff) -> c_int {
    if skb.is_null() {
        return 1;
    }

    let fou_ptr: *mut fou = ptr::null_mut();
    if fou_ptr.is_null() {
        return 1;
    }

    if fou_recv_pull(skb, fou_ptr, core::mem::size_of::<udphdr>()) != 0 {
        kfree_skb(skb);
        return 0;
    }

    -((*fou_ptr).protocol as c_int)
}

#[no_mangle]
pub unsafe extern "C" fn gue_remcsum(
    skb: *mut sk_buff,
    gueh: *mut guehdr,
    data: *mut c_void,
    hdrlen: usize,
    _ipproto: u8,
    nopartial: c_int,
) -> *mut guehdr {
    if skb.is_null() || gueh.is_null() || data.is_null() {
        return ptr::null_mut();
    }

    let pd = data as *mut u16;
    let start = ntohs(*pd);
    let offset = ntohs(*pd.add(1));

    let plen = core::mem::size_of::<udphdr>() as u64
        + hdrlen as u64
        + (offset as u64 + core::mem::size_of::<u16>() as u64).max(start as u64);

    if !pskb_may_pull(skb, plen as usize) {
        return ptr::null_mut();
    }

    let new_gueh = (udp_hdr(skb) as *mut guehdr).add(1);
    let data_ptr = (new_gueh as *mut u8).add(hdrlen) as *mut c_void;

    skb_remcsum_process(skb, data_ptr, start, offset, nopartial != 0);

    new_gueh
}

#[no_mangle]
pub unsafe extern "C" fn gue_control_message(skb: *mut sk_buff, gueh: *mut guehdr) -> c_int {
    if skb.is_null() || gueh.is_null() {
        return 0;
    }
    kfree_skb(skb);
    0
}

#[no_mangle]
pub unsafe extern "C" fn gue_udp_recv(_sk: *mut sock, skb: *mut sk_buff) -> c_int {
    if skb.is_null() {
        return 1;
    }
    1
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}
