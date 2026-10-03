#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]

use core::ffi::c_int;
use core::ffi::c_uint;
use core::ffi::c_ulong;
use core::ffi::c_void;
use core::panic::PanicInfo;
use kernel_types::*;

pub const EMSGSIZE: c_int = -90;

// Type definitions

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_state_props { pub mode: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_state { pub props: xfrm_state_props }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_skb_cb { flags: c_ulong }

const ETH_P_IPV6: c_int = 0x86DD;
const XFRM_MODE_TUNNEL: c_int = 2;
const IP6SKB_REROUTED: c_ulong = 1 << 0;
const NFPROTO_IPV6: c_int = 10;
const NF_INET_POST_ROUTING: c_int = 3;

extern "C" {
    fn ip6_find_1stfragopt(skb: *mut sk_buff, prevhdr: *mut *mut u8) -> c_int;
    fn ipv6_local_rxpmtu(sk: *mut sock, fl: *mut flowi6, mtu: c_uint);
    fn ipv6_local_error(sk: *mut sock, code: c_int, fl: *mut flowi6, mtu: c_uint);
    fn xfrm_output(sk: *mut sock, skb: *mut sk_buff) -> c_int;
    fn ip6_fragment(
        net: *mut net,
        sk: *mut sock,
        skb: *mut sk_buff,
        okfn: extern "C" fn(*mut net, *mut sock, *mut sk_buff) -> c_int,
    ) -> c_int;
    fn dst_output(net: *mut net, sk: *mut sock, skb: *mut sk_buff) -> c_int;
    fn skb_dst(skb: *mut sk_buff) -> *mut dst_entry;
    fn ipv6_hdr(skb: *mut sk_buff) -> *mut ipv6hdr;
    fn inner_ipv6_hdr(skb: *mut sk_buff) -> *mut ipv6hdr;
    fn IP6CB(skb: *mut sk_buff) -> *mut ip6_skb_cb;
    fn NF_HOOK_COND(
        pf: c_int,
        hook: c_int,
        net: *mut net,
        sk: *mut sock,
        skb: *mut sk_buff,
        indev: *mut c_void,
        outdev: *mut c_void,
        okfn: extern "C" fn(*mut net, *mut sock, *mut sk_buff) -> c_int,
        cond: bool,
    ) -> c_int;
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}

#[no_mangle]
pub unsafe extern "C" fn xfrm6_find_1stfragopt(
    _x: *mut xfrm_state,
    skb: *mut sk_buff,
    prevhdr: *mut *mut u8,
) -> c_int {
    ip6_find_1stfragopt(skb, prevhdr)
}

#[no_mangle]
pub unsafe extern "C" fn xfrm6_local_rxpmtu(skb: *mut sk_buff, mtu: c_uint) {
    let sk = (*skb).sk as *mut sock;
    if sk.is_null() {
        return;
    }

    let mut fl6 = flowi6 {
        flowi6_oif: 0,
        flowi6_flags: 0,
        flowi6_mark: 0,
        daddr: (*ipv6_hdr(skb)).daddr,
        saddr: (*ipv6_hdr(skb)).saddr,
    };

    ipv6_local_rxpmtu(sk, &mut fl6, mtu);
}

#[no_mangle]
pub unsafe extern "C" fn xfrm6_local_error(skb: *mut sk_buff, mtu: c_uint) {
    let sk = (*skb).sk as *mut sock;
    if sk.is_null() {
        return;
    }

    let hdr = ipv6_hdr(skb);

    let mut fl6 = flowi6 {
        flowi6_oif: 0,
        flowi6_flags: 0,
        flowi6_mark: 0,
        daddr: (*hdr).daddr,
        saddr: (*hdr).saddr,
    };

    ipv6_local_error(sk, EMSGSIZE, &mut fl6, mtu);
}

extern "C" fn __xfrm6_output_finish(net: *mut net, sk: *mut sock, skb: *mut sk_buff) -> c_int {
    let _ = net;
    unsafe { xfrm_output(sk, skb) }
}

extern "C" fn __xfrm6_output(net: *mut net, sk: *mut sock, skb: *mut sk_buff) -> c_int {
    unsafe {
        let dst = skb_dst(skb);
        if dst.is_null() {
            return xfrm_output(sk, skb);
        }

        let x = (*dst).xfrm as *mut xfrm_state;
        if x.is_null() {
            return dst_output(net, sk, skb);
        }

        if (*x).props.mode != XFRM_MODE_TUNNEL {
            return xfrm_output(sk, skb);
        }

        ip6_fragment(net, sk, skb, __xfrm6_output_finish)
    }
}

/// Main xfrm6 output function with netfilter hook
#[no_mangle]
pub unsafe extern "C" fn xfrm6_output(net: *mut net, sk: *mut sock, skb: *mut sk_buff) -> c_int {
    NF_HOOK_COND(
        NFPROTO_IPV6,
        NF_INET_POST_ROUTING,
        net,
        sk,
        skb,
        (*skb).dev as *mut c_void,
        (*skb_dst(skb)).dev as *mut c_void,
        __xfrm6_output,
        ((*IP6CB(skb)).flags & IP6SKB_REROUTED) == 0,
    )
}

// Helper functions (assumed to exist in C)
#[inline(always)]
unsafe fn htons(x: c_int) -> c_int { ((x >> 8) & 0xff) | ((x & 0xff) << 8) }

#[inline(always)]
unsafe fn inet_sk(sk: *mut sock) -> *mut inet_sock {
    (sk as *mut u8).offset(0) as *mut inet_sock
}

// Remove duplicate - defined in extern block
// #[inline(always)]
// unsafe fn IP6CB(skb: *mut sk_buff) -> *mut ip6_skb_cb {
//     (skb as *mut u8).offset(0) as *mut ip6_skb_cb
// }
