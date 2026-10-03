#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

use core::ffi::{c_char, c_void};
use core::sync::atomic::{AtomicPtr, Ordering};

extern "C" {
    fn kmalloc(size: usize, flags: u32) -> *mut c_void;
    fn kfree(ptr: *mut c_void);
    fn nf_ct_timeout_destroy(timeout: *mut nf_conntrack_timeout);
}

const GFP_KERNEL: u32 = 0xCC0;

#[repr(C)]
pub struct nf_conn {
    _priv: [u8; 0],
}
#[repr(C)]
pub struct nf_conntrack_helper {
    _priv: [u8; 0],
}

#[repr(C)]
pub struct nf_conntrack_timeout {
    pub name: *const c_char,
    pub timeout: u32,
    pub hook_mask: u8,
    pub next: *mut nf_conntrack_timeout,
    pub use_: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_inet_addr {
    pub all: [u32; 4],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_man_tcp {
    pub port: u16,
    pub state: u8,
    pub _pad: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_man_udp {
    pub port: u16,
    pub _pad: u16,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_man_icmp {
    pub type_: u8,
    pub code: u8,
    pub _pad: u16,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_man_sctp {
    pub port: u16,
    pub state: u8,
    pub _pad: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_man_dccp {
    pub port: u16,
    pub state: u8,
    pub _pad: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub union nf_conntrack_man_proto {
    pub all: [u32; 2],
    pub tcp: core::mem::ManuallyDrop<nf_conntrack_man_tcp>,
    pub udp: core::mem::ManuallyDrop<nf_conntrack_man_udp>,
    pub icmp: core::mem::ManuallyDrop<nf_conntrack_man_icmp>,
    pub sctp: core::mem::ManuallyDrop<nf_conntrack_man_sctp>,
    pub dccp: core::mem::ManuallyDrop<nf_conntrack_man_dccp>,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple {
    pub src: nf_inet_addr,
    pub dst: nf_inet_addr,
    pub src_u: nf_conntrack_man_proto,
    pub dst_u: nf_conntrack_man_proto,
    pub src_l3num: u8,
    pub dst_l3num: u8,
    pub src_protonum: u8,
    pub dst_protonum: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_hash {
    pub tuplehash: *mut nf_conntrack_tuple_hash,
    pub tuple: nf_conntrack_tuple,
    pub me: *mut nf_conn,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_expect {
    pub tuple: nf_conntrack_tuple,
    pub mask: nf_conntrack_tuple,
    pub expectfn: Option<extern "C" fn(*mut nf_conn, *mut nf_conntrack_expect)>,
    pub timeout: u32,
    pub flags: u8,
    pub class: u8,
    pub id: u16,
    pub master: *mut nf_conn,
    pub helper: *mut nf_conntrack_helper,
}

static NF_CT_TIMEOUT_LIST: AtomicPtr<nf_conntrack_timeout> = AtomicPtr::new(core::ptr::null_mut());

#[no_mangle]
pub unsafe extern "C" fn nf_ct_timeout_lookup(
    name: *const c_char,
    timeout: u32,
    hook_mask: u8,
) -> *mut nf_conntrack_timeout {
    let mut timeout_ptr = nf_ct_timeout_find_get(name);

    if timeout_ptr.is_null() {
        timeout_ptr = nf_ct_timeout_alloc(name, timeout, hook_mask);
        if timeout_ptr.is_null() {
            return core::ptr::null_mut();
        }
    } else {
        nf_ct_timeout_put(timeout_ptr);
    }

    timeout_ptr
}

#[no_mangle]
pub unsafe extern "C" fn nf_ct_timeout_find_get(name: *const c_char) -> *mut nf_conntrack_timeout {
    let timeout_ptr = nf_ct_timeout_find(name);

    if !timeout_ptr.is_null() {
        nf_ct_timeout_get(timeout_ptr);
    }

    timeout_ptr
}

#[no_mangle]
pub unsafe extern "C" fn nf_ct_timeout_alloc(
    name: *const c_char,
    timeout: u32,
    hook_mask: u8,
) -> *mut nf_conntrack_timeout {
    let timeout_ptr = kmalloc(
        core::mem::size_of::<nf_conntrack_timeout>(),
        GFP_KERNEL,
    ) as *mut nf_conntrack_timeout;

    if timeout_ptr.is_null() {
        return core::ptr::null_mut();
    }

    (*timeout_ptr).name = name;
    (*timeout_ptr).timeout = timeout;
    (*timeout_ptr).hook_mask = hook_mask;
    (*timeout_ptr).next = NF_CT_TIMEOUT_LIST.load(Ordering::SeqCst);
    (*timeout_ptr).use_ = 1;
    NF_CT_TIMEOUT_LIST.store(timeout_ptr, Ordering::SeqCst);

    timeout_ptr
}

#[no_mangle]
pub unsafe extern "C" fn nf_ct_timeout_find(name: *const c_char) -> *mut nf_conntrack_timeout {
    let mut cur = NF_CT_TIMEOUT_LIST.load(Ordering::SeqCst);

    while !cur.is_null() {
        let a = core::ffi::CStr::from_ptr((*cur).name);
        let b = core::ffi::CStr::from_ptr(name);
        if a.to_bytes() == b.to_bytes() {
            return cur;
        }
        cur = (*cur).next;
    }

    core::ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn nf_ct_timeout_get(timeout: *mut nf_conntrack_timeout) {
    if timeout.is_null() {
        return;
    }
    (*timeout).use_ = (*timeout).use_.wrapping_add(1);
}

#[no_mangle]
pub unsafe extern "C" fn nf_ct_timeout_put(timeout: *mut nf_conntrack_timeout) {
    if timeout.is_null() {
        return;
    }

    if (*timeout).use_ <= 1 {
        nf_ct_timeout_list_del(timeout);
        kfree(timeout as *mut c_void);
    } else {
        (*timeout).use_ -= 1;
    }
}


#[no_mangle]
pub unsafe extern "C" fn nf_ct_timeout_list_del(timeout: *mut nf_conntrack_timeout) {
    let mut prev: *mut nf_conntrack_timeout = core::ptr::null_mut();
    let mut curr = NF_CT_TIMEOUT_LIST.load(Ordering::SeqCst);

    while !curr.is_null() {
        if curr == timeout {
            if prev.is_null() {
                NF_CT_TIMEOUT_LIST.store((*curr).next, Ordering::SeqCst);
            } else {
                (*prev).next = (*curr).next;
            }
            break;
        }

        prev = curr;
        curr = (*curr).next;
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_ct_timeout_init() {
    NF_CT_TIMEOUT_LIST.store(core::ptr::null_mut(), Ordering::SeqCst);
}

#[no_mangle]
pub unsafe extern "C" fn nf_ct_timeout_cleanup() {
    let mut timeout_ptr = NF_CT_TIMEOUT_LIST.load(Ordering::SeqCst);

    while !timeout_ptr.is_null() {
        let next = (*timeout_ptr).next;
        kfree(timeout_ptr as *mut c_void);
        timeout_ptr = next;
    }

    NF_CT_TIMEOUT_LIST.store(core::ptr::null_mut(), Ordering::SeqCst);
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
