#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(non_snake_case)]
#![allow(clippy::too_many_arguments)]
#![allow(clippy::implicit_return_in_non_void_function)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs)]

use core::{alloc::{GlobalAlloc, Layout}, ffi::{c_int, c_void}, mem, ptr};
use kernel_types::*;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOSYS: c_int = -38;
pub const ENOENT: c_int = -2;
pub const EINPROGRESS: c_int = -115;
pub const EOPNOTSUPP: c_int = -95;
pub const EREMCHG: c_int = -103;

struct DummyAlloc;
unsafe impl GlobalAlloc for DummyAlloc {
    unsafe fn alloc(&self, _layout: Layout) -> *mut u8 {
        ptr::null_mut()
    }
    unsafe fn dealloc(&self, _ptr: *mut u8, _layout: Layout) {}
}
#[global_allocator]
static GLOBAL_ALLOCATOR: DummyAlloc = DummyAlloc;

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

#[cfg(target_os = "none")]
#[unsafe(no_mangle)]
pub extern "C" fn rust_eh_personality() {}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct page { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sock { _private: [u8; 0] }

pub type __be16 = u16;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_skb_cb { pub xfrm: xfrm_skb_cb_inner }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_skb_cb_inner { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct esp_skb_cb { pub xfrm: xfrm_skb_cb, pub tmp: *mut c_void }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct esp_output_extra { pub seqhi: u32, pub esphoff: u32 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct aead_request { pub src: *mut scatterlist, pub dst: *mut scatterlist }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct crypto_aead { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct scatterlist { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_state {
    pub data: *mut crypto_aead,
    pub props: xfrm_state_props,
    pub encap: *mut xfrm_encap_tmpl,
    pub lock: spinlock_t,
    pub encap_sk: *mut sock,
    pub id: xfrm_id,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_id { pub daddr: xfrm_address }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_address { pub a4: __be32 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_state_props { pub flags: u32, pub saddr: xfrm_address }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_encap_tmpl {
    pub encap_type: u16,
    pub encap_sport: __be16,
    pub encap_dport: __be16,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct spinlock_t { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct rcu_head { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct esp_tcp_sk { pub sk: *mut sock, pub rcu: rcu_head }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_offload_seq { pub hi: u32 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_offload { pub flags: u32, pub seq: xfrm_offload_seq }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sec_path { pub len: u8, pub xvec: [*mut xfrm_state; 0] }

#[inline]
fn align_up(v: usize, a: usize) -> usize {
    if a == 0 {
        v
    } else {
        (v + (a - 1)) & !(a - 1)
    }
}

unsafe extern "C" {
    fn crypto_aead_ivsize(aead: *mut crypto_aead) -> u32;
    fn crypto_aead_alignmask(aead: *mut crypto_aead) -> u32;
    fn crypto_tfm_ctx_alignment() -> u32;
    fn crypto_aead_reqsize(aead: *mut crypto_aead) -> u32;
    fn aead_request_set_tfm(req: *mut aead_request, tfm: *mut crypto_aead);
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn esp_alloc_tmp(
    aead: *mut crypto_aead,
    nfrags: c_int,
    extralen: c_int,
) -> *mut c_void {
    if aead.is_null() {
        return ptr::null_mut();
    }

    let mut len = extralen.max(0) as usize;

    let ivsize = unsafe { crypto_aead_ivsize(aead) } as usize;
    len = len.saturating_add(ivsize);

    if ivsize > 0 {
        let tfm_align = unsafe { crypto_tfm_ctx_alignment() } as usize;
        let align_mask =
            (unsafe { crypto_aead_alignmask(aead) } as usize) & !(tfm_align.saturating_sub(1));
        len = len.saturating_add(align_mask);
        len = align_up(len, tfm_align);
    }

    len = len
        .saturating_add(mem::size_of::<aead_request>())
        .saturating_add(unsafe { crypto_aead_reqsize(aead) } as usize);
    len = align_up(len, mem::align_of::<scatterlist>());

    let frags = nfrags.max(0) as usize;
    len = len.saturating_add(mem::size_of::<scatterlist>().saturating_mul(frags));

    let layout = match Layout::from_size_align(len.max(1), mem::align_of::<usize>()) {
        Ok(l) => l,
        Err(_) => return ptr::null_mut(),
    };

    unsafe { GLOBAL_ALLOCATOR.alloc(layout) as *mut c_void }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn esp_tmp_extra(tmp: *mut c_void) -> *mut esp_output_extra {
    if tmp.is_null() {
        return ptr::null_mut();
    }
    let aligned = align_up(tmp as usize, mem::align_of::<esp_output_extra>());
    aligned as *mut esp_output_extra
}

#[no_mangle]
pub unsafe extern "C" fn esp_tmp_iv(
    aead: *mut crypto_aead,
    tmp: *mut c_void,
    extralen: c_int,
) -> *mut u8 {
    if aead.is_null() || tmp.is_null() {
        return ptr::null_mut();
    }

    let ivsize = crypto_aead_ivsize(aead);
    if ivsize == 0 {
        return (tmp as *mut u8).add(extralen as usize);
    }

    let align_mask = (crypto_aead_alignmask(aead) + 1) as usize;
    let offset = (extralen as usize + align_mask - 1) & !(align_mask - 1);

    (tmp as *mut u8).add(offset)
}

#[no_mangle]
pub unsafe extern "C" fn esp_tmp_req(
    aead: *mut crypto_aead,
    iv: *mut u8,
) -> *mut aead_request {
    if aead.is_null() || iv.is_null() {
        return ptr::null_mut();
    }

    let ivsize = crypto_aead_ivsize(aead) as usize;
    let align = crypto_tfm_ctx_alignment() as usize;
    let offset = (ivsize + align - 1) & !(align - 1);

    let req = (iv as *mut u8).add(offset as usize) as *mut aead_request;
    aead_request_set_tfm(req, aead);
    req
}

#[no_mangle]
pub unsafe extern "C" fn esp_req_sg(
    aead: *mut crypto_aead,
    req: *mut aead_request,
) -> *mut scatterlist {
    if aead.is_null() || req.is_null() {
        return ptr::null_mut();
    }

    let reqsize = crypto_aead_reqsize(aead);
    let offset = (req as *mut u8).add(mem::size_of::<aead_request>() + reqsize as usize) as usize;

    let aligned = offset + (mem::align_of::<scatterlist>() - 1) & !(mem::align_of::<scatterlist>() - 1);

    aligned as *mut scatterlist
}

#[no_mangle]
pub unsafe extern "C" fn esp_ssg_unref(
    x: *mut xfrm_state,
    tmp: *mut c_void,
) {
    if x.is_null() || tmp.is_null() {
        return;
    }

    let aead = (*x).data;
    let mut extralen = 0;

    if (*x).props.flags & XFRM_STATE_ESN() != 0 {
        extralen += mem::size_of::<esp_output_extra>() as c_int;
    }

    let _extra = esp_tmp_extra(tmp);
    let iv = esp_tmp_iv(aead, tmp, extralen);
    let req = esp_tmp_req(aead, iv);

    // Unref skb_frag_pages in the src scatterlist if necessary
    if (*req).src != (*req).dst {
        let mut sg = sg_next((*req).src);
        while !sg.is_null() {
            put_page(sg_page(sg));
            sg = sg_next(sg);
        }
    }
}

#[cfg(feature = "espintcp")]
#[no_mangle]
pub unsafe extern "C" fn esp_free_tcp_sk(head: *mut rcu_head) {
    if head.is_null() {
        return;
    }

    let esk = container_of(head, esp_tcp_sk, rcu);
    sock_put((*esk).sk);
    libc::free(esk as *mut c_void);
}

#[cfg(feature = "espintcp")]
#[no_mangle]
pub unsafe extern "C" fn esp_find_tcp_sk(x: *mut xfrm_state) -> *mut sock {
    if x.is_null() {
        return ptr::null_mut();
    }

    let encap = (*x).encap;
    let sk = rcu_dereference((*x).encap_sk);

    if !sk.is_null() && (*sk).sk_state == TCP_ESTABLISHED() {
        return sk;
    }

    spin_lock_bh(&(*x).lock);
    let sport = (*encap).encap_sport;
    let dport = (*encap).encap_dport;
    let nsk = rcu_dereference_protected((*x).encap_sk, lockdep_is_held(&(*x).lock));

    if !sk.is_null() && sk == nsk {
        let esk = libc::malloc(mem::size_of::<esp_tcp_sk>()) as *mut esp_tcp_sk;
        if esk.is_null() {
            spin_unlock_bh(&(*x).lock);
            return ptr::null_mut();
        }

        RCU_INIT_POINTER((*x).encap_sk, ptr::null_mut());
        (*esk).sk = sk;
        call_rcu(&(*esk).rcu, esp_free_tcp_sk);
    }

    spin_unlock_bh(&(*x).lock);

    let net = xs_net(x);
    let sk = inet_lookup_established(net, &tcp_hashinfo,
                                     &(*x).id.daddr.a4,
                                     (*encap).encap_dport,
                                     &(*x).props.saddr.a4,
                                     (*encap).encap_sport,
                                     0);

    if sk.is_null() {
        return ptr::null_mut();
    }

    if !tcp_is_ulp_esp(sk) {
        sock_put(sk);
        return ptr::null_mut();
    }

    spin_lock_bh(&(*x).lock);
    let nsk = rcu_dereference_protected((*x).encap_sk, lockdep_is_held(&(*x).lock));

    if (*encap).encap_sport != sport || (*encap).encap_dport != dport {
        sock_put(sk);
        return if !nsk.is_null() { nsk } else { ptr::null_mut() };
    } else if sk == nsk {
        sock_put(sk);
    } else {
        rcu_assign_pointer((*x).encap_sk, sk);
    }

    spin_unlock_bh(&(*x).lock);
    sk
}

// Helper functions (declared as extern in C)
extern "C" {
    fn sg_next(sg: *mut scatterlist) -> *mut scatterlist;
    fn sg_page(sg: *mut scatterlist) -> *mut page;
    fn put_page(page: *mut page);
    fn XFRM_STATE_ESN() -> u32;
    fn xs_net(x: *mut xfrm_state) -> *mut net;
    fn TCP_ESTABLISHED() -> u8;
    fn rcu_dereference(ptr: *mut c_void) -> *mut c_void;
    fn rcu_dereference_protected(ptr: *mut c_void, lock_held: bool) -> *mut c_void;
    fn spin_lock_bh(lock: *mut spinlock_t);
    fn spin_unlock_bh(lock: *mut spinlock_t);
    fn lockdep_is_held(lock: *mut spinlock_t) -> bool;
    fn RCU_INIT_POINTER(ptr: *mut *mut c_void, val: *mut c_void);
    fn call_rcu(head: *mut rcu_head, func: extern "C" fn(*mut rcu_head));
    fn inet_lookup_established(net: *mut net, hashinfo: *mut c_void,
                               daddr: *mut c_void, dport: __be16,
                               saddr: *mut c_void, sport: __be16,
                               netns: c_int) -> *mut sock;
    fn tcp_is_ulp_esp(sk: *mut sock) -> bool;
    fn rcu_assign_pointer(ptr: *mut *mut c_void, val: *mut c_void);
    fn sock_put(sk: *mut sock);
    fn espintcp_queue_out(sk: *mut sock, skb: *mut sk_buff) -> c_int;
    fn espintcp_push_skb(sk: *mut sock, skb: *mut sk_buff) -> c_int;
    fn bh_lock_sock(sk: *mut sock);
    fn bh_unlock_sock(sk: *mut sock);
    fn xfrm_trans_queue_net(net: *mut net, skb: *mut sk_buff,
                            cb: extern "C" fn(*mut net, *mut sock, *mut sk_buff)) -> c_int;
    fn local_bh_disable();
    fn local_bh_enable();
    fn xfrm_dev_resume(skb: *mut sk_buff);
    fn xfrm_output_resume(sk: *mut sock, skb: *mut sk_buff, err: c_int);
    fn kfree_skb(skb: *mut sk_buff);
    fn XFRM_INC_STATS(net: *mut net, stat: c_int);
    fn skb_push(skb: *mut sk_buff, len: c_int) -> *mut u8;
    fn secpath_reset(skb: *mut sk_buff);
}

// Helper macros
#[inline]
fn ALIGN(val: usize, align: usize) -> usize { (val + align - 1) & !(align - 1) }

#[inline]
fn PTR_ALIGN(ptr: *mut c_void, align: usize) -> *mut c_void {
    let offset = (ptr as usize + align - 1) & !(align - 1);
    offset as *mut c_void
}

// Constants
pub const XFRM_DEV_RESUME: u32 = 1 << 0; pub const TCP_ENCAP_ESPINTCP: u16 = 5;

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    #[test]
    fn test_memory_alignment() {
        // Simple test for alignment calculations
        assert!(mem::align_of::<esp_output_extra>() == 4);
        assert!(mem::align_of::<scatterlist>() == 8);
    }
}
