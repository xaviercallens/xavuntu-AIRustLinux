#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
use kernel_types::*;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_udp_tunnel {
    pub encap_type: c_int,
    pub encap_rcv: Option<extern "C" fn(skb: *mut sk_buff) -> c_int>,
    pub encap_destroy: Option<extern "C" fn(t: *mut ip6_udp_tunnel)>,
    pub err_handler: Option<extern "C" fn(sk: *mut sock, err: c_int) -> c_int>,
    pub encap_sport: __be16,
    pub encap_dport: __be16,
    pub encap_flags: c_int,
    pub encap_parms: *mut c_void,
    pub encap_data: *mut c_void,
}

#[no_mangle]
pub unsafe extern "C" fn ip6_udp_tunnel_xmit_sk(
    sk: *mut sock,
    skb: *mut sk_buff,
    flow: *const flowi,
    src: *const sockaddr,
    dst: *const sockaddr,
) -> c_int {
    if sk.is_null() || skb.is_null() || flow.is_null() || src.is_null() || dst.is_null() {
        return -EINVAL;
    }

    let inet_sock_ptr = (*sk).sk_user_data as *mut inet_sock;
    if inet_sock_ptr.is_null() {
        return -EINVAL;
    }

    let tunnel = (*inet_sock_ptr).pinet6 as *mut ip6_udp_tunnel;
    if tunnel.is_null() {
        return -EINVAL;
    }

    let encap_rcv = (*tunnel).encap_rcv;
    if encap_rcv.is_none() {
        return -EINVAL;
    }

    let ret = encap_rcv.unwrap()(skb);
    if ret != 0 {
        return ret;
    }

    0
}

#[no_mangle]
pub unsafe extern "C" fn ip6_udp_tunnel_rcv(
    sk: *mut sock,
    skb: *mut sk_buff,
) -> c_int {
    if sk.is_null() || skb.is_null() {
        return -EINVAL;
    }

    let inet_sock_ptr = (*sk).sk_user_data as *mut inet_sock;
    if inet_sock_ptr.is_null() {
        return -EINVAL;
    }

    let tunnel = (*inet_sock_ptr).pinet6 as *mut ip6_udp_tunnel;
    if tunnel.is_null() {
        return -EINVAL;
    }

    let encap_rcv = (*tunnel).encap_rcv;
    if encap_rcv.is_none() {
        return -EINVAL;
    }

    let ret = encap_rcv.unwrap()(skb);
    if ret != 0 {
        return ret;
    }

    0
}

#[no_mangle]
pub unsafe extern "C" fn ip6_udp_tunnel_err(
    sk: *mut sock,
    err: c_int,
) -> c_int {
    if sk.is_null() {
        return -EINVAL;
    }

    let inet_sock_ptr = (*sk).sk_user_data as *mut inet_sock;
    if inet_sock_ptr.is_null() {
        return -EINVAL;
    }

    let tunnel = (*inet_sock_ptr).pinet6 as *mut ip6_udp_tunnel;
    if tunnel.is_null() {
        return -EINVAL;
    }

    let err_handler = (*tunnel).err_handler;
    if err_handler.is_none() {
        return -EINVAL;
    }

    let ret = err_handler.unwrap()(sk, err);
    if ret != 0 {
        return ret;
    }

    0
}

#[no_mangle]
pub unsafe extern "C" fn ip6_udp_tunnel_close(
    sk: *mut sock,
) -> c_int {
    if sk.is_null() {
        return -EINVAL;
    }

    let inet_sock_ptr = (*sk).sk_user_data as *mut inet_sock;
    if inet_sock_ptr.is_null() {
        return -EINVAL;
    }

    let tunnel = (*inet_sock_ptr).pinet6 as *mut ip6_udp_tunnel;
    if tunnel.is_null() {
        return -EINVAL;
    }

    let encap_destroy = (*tunnel).encap_destroy;
    if encap_destroy.is_none() {
        return -EINVAL;
    }

    encap_destroy.unwrap()(tunnel);

    0
}

#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
