#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]

#[cfg(test)]
extern crate std;

// SyncWrapper for safe global mutability
#[repr(transparent)]
pub struct SyncWrapper<T>(pub core::cell::UnsafeCell<T>);
unsafe impl<T> Sync for SyncWrapper<T> {}
impl<T> SyncWrapper<T> {
    pub const fn new(value: T) -> Self {
        Self(core::cell::UnsafeCell::new(value))
    }
    #[inline(always)]
    pub unsafe fn get_mut(&self) -> &mut T {
        // SAFETY: The caller must guarantee exclusive access or single-threaded context.
        unsafe { &mut *self.0.get() }
    }
}

use core::{ptr, ffi::{c_int, c_char}, sync::atomic::{AtomicPtr, Ordering}};
use kernel_types::*;

pub const IPPROTO_ESP: u8 = 50; pub const IPPROTO_AH: u8 = 51; pub const IPPROTO_COMP: u8 = 108;

pub const INET6_PROTO_NOPOLICY: c_int = 1 << 0;
pub const ICMPV6_DEST_UNREACH: c_int = 1;
pub const ICMPV6_PORT_UNREACH: c_int = 4;

pub const EINVAL: c_int = -22;
pub const EEXIST: c_int = -17;
pub const EAGAIN: c_int = -11;
pub const ENOENT: c_int = -2;

pub const AF_INET6: c_int = 10;

unsafe extern "C" {
    fn icmpv6_send(skb: *mut sk_buff, type_: c_int, code: c_int, info: u32);
    fn kfree_skb(skb: *mut sk_buff);
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm6_protocol {
    pub next: *mut xfrm6_protocol,
    pub priority: c_int,
    pub handler: extern "C" fn(*mut sk_buff) -> c_int,
    pub input_handler: extern "C" fn(*mut sk_buff, c_int, u32, c_int) -> c_int,
    pub cb_handler: extern "C" fn(*mut sk_buff, c_int) -> c_int,
    pub err_handler: extern "C" fn(*mut sk_buff, *mut sk_buff, u8, u8, c_int, u32) -> c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet6_protocol {
    pub handler: extern "C" fn(*mut sk_buff) -> c_int,
    pub err_handler: extern "C" fn(*mut sk_buff, *mut sk_buff, u8, u8, c_int, u32) -> c_int,
    pub flags: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_input_afinfo {
    pub family: c_int,
    pub callback: unsafe extern "C" fn(*mut sk_buff, u8, c_int) -> c_int,
}

static ESP6_HANDLERS: SyncWrapper<AtomicPtr<xfrm6_protocol>> = SyncWrapper::new(AtomicPtr::new(ptr::null_mut()));
static AH6_HANDLERS: SyncWrapper<AtomicPtr<xfrm6_protocol>> = SyncWrapper::new(AtomicPtr::new(ptr::null_mut()));
static IPCOMP6_HANDLERS: SyncWrapper<AtomicPtr<xfrm6_protocol>> = SyncWrapper::new(AtomicPtr::new(ptr::null_mut()));

// Dummy mutex implementation
#[repr(C)]
struct Mutex { _private: u32 }
impl Mutex {
    fn lock(&mut self) {}
    fn unlock(&mut self) {}
}
static XFRM6_PROTOCOL_MUTEX: SyncWrapper<Mutex> = SyncWrapper::new(Mutex { _private: 0 });

unsafe fn proto_handlers(protocol: u8) -> *mut AtomicPtr<xfrm6_protocol> {
    match protocol {
        IPPROTO_ESP => ESP6_HANDLERS.get_mut() as *const AtomicPtr<xfrm6_protocol> as *mut AtomicPtr<xfrm6_protocol>,
        IPPROTO_AH => AH6_HANDLERS.get_mut() as *const AtomicPtr<xfrm6_protocol> as *mut AtomicPtr<xfrm6_protocol>,
        IPPROTO_COMP => IPCOMP6_HANDLERS.get_mut() as *const AtomicPtr<xfrm6_protocol> as *mut AtomicPtr<xfrm6_protocol>,
        _ => ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "C" fn xfrm6_esp_rcv(skb: *mut sk_buff) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }
    // SAFETY: Validated non-null skb and synchronized protocol handler dereference.
    unsafe {
        let headp = proto_handlers(IPPROTO_ESP);
        if !headp.is_null() {
            let handler = (*headp).load(Ordering::Acquire);
            if !handler.is_null() {
                return ((*handler).handler)(skb);
            }
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn xfrm6_esp_err(
    skb: *mut sk_buff,
    opt: *mut sk_buff,
    type_: u8,
    code: u8,
    offset: c_int,
    info: u32,
) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }
    // SAFETY: Validated non-null skb and synchronized protocol handler dereference.
    unsafe {
        let headp = proto_handlers(IPPROTO_ESP);
        if !headp.is_null() {
            let handler = (*headp).load(Ordering::Acquire);
            if !handler.is_null() {
                return ((*handler).err_handler)(skb, opt, type_, code, offset, info);
            }
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn xfrm6_ah_rcv(skb: *mut sk_buff) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }
    // SAFETY: Validated non-null skb and synchronized protocol handler dereference.
    unsafe {
        let headp = proto_handlers(IPPROTO_AH);
        if !headp.is_null() {
            let handler = (*headp).load(Ordering::Acquire);
            if !handler.is_null() {
                return ((*handler).handler)(skb);
            }
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn xfrm6_ah_err(
    skb: *mut sk_buff,
    opt: *mut sk_buff,
    type_: u8,
    code: u8,
    offset: c_int,
    info: u32,
) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }
    // SAFETY: Validated non-null skb and synchronized protocol handler dereference.
    unsafe {
        let headp = proto_handlers(IPPROTO_AH);
        if !headp.is_null() {
            let handler = (*headp).load(Ordering::Acquire);
            if !handler.is_null() {
                return ((*handler).err_handler)(skb, opt, type_, code, offset, info);
            }
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn xfrm6_ipcomp_rcv(skb: *mut sk_buff) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }
    // SAFETY: Validated non-null skb and synchronized protocol handler dereference.
    unsafe {
        let headp = proto_handlers(IPPROTO_COMP);
        if !headp.is_null() {
            let handler = (*headp).load(Ordering::Acquire);
            if !handler.is_null() {
                return ((*handler).handler)(skb);
            }
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn xfrm6_ipcomp_err(
    skb: *mut sk_buff,
    opt: *mut sk_buff,
    type_: u8,
    code: u8,
    offset: c_int,
    info: u32,
) -> c_int {
    if skb.is_null() {
        return EINVAL;
    }
    // SAFETY: Validated non-null skb and synchronized protocol handler dereference.
    unsafe {
        let headp = proto_handlers(IPPROTO_COMP);
        if !headp.is_null() {
            let handler = (*headp).load(Ordering::Acquire);
            if !handler.is_null() {
                return ((*handler).err_handler)(skb, opt, type_, code, offset, info);
            }
        }
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn xfrm6_rcv_cb(skb: *mut sk_buff, protocol: u8, err: c_int) -> c_int {
    let headp = proto_handlers(protocol);
    if headp.is_null() {
        return 0;
    }

    let mut handler = (*headp).load(Ordering::Acquire);

    while !handler.is_null() {
        let ret = ((*handler).cb_handler)(skb, err);
        if ret <= 0 {
            return ret;
        }
        handler = (*handler).next;
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn xfrm6_rcv_encap(
    skb: *mut sk_buff,
    nexthdr: c_int,
    spi: u32,
    encap_type: c_int,
) -> c_int {
    let head = proto_handlers(nexthdr as u8);
    let _ret = 0;

    if !head.is_null() {
        let mut handler = (*head).load(Ordering::Acquire);

        while !handler.is_null() {
            let ret = ((*handler).input_handler)(skb, nexthdr, spi, encap_type);
            if ret != EINVAL {
                return ret;
            }
            handler = (*handler).next;
        }
    }

    icmpv6_send(skb, ICMPV6_DEST_UNREACH, ICMPV6_PORT_UNREACH, 0);
    kfree_skb(skb);
    0
}

#[no_mangle]
pub unsafe extern "C" fn xfrm6_protocol_register(
    handler: *mut xfrm6_protocol,
    protocol: u8,
) -> c_int {
    let headp = proto_handlers(protocol);
    if headp.is_null() || handler.is_null() {
        return EINVAL;
    }

    let mutex = XFRM6_PROTOCOL_MUTEX.get_mut();
    mutex.lock();

    let t = (*headp).load(Ordering::Acquire);
    let add_netproto = t.is_null();
    let mut ret = 0;

    // Find insertion point
    let mut prev_ptr: *mut *mut xfrm6_protocol = ptr::null_mut();
    let mut curr = t;

    while !curr.is_null() {
        if (*curr).priority < (*handler).priority {
            break;
        }
        if (*curr).priority == (*handler).priority {
            ret = EEXIST;
            break;
        }
        prev_ptr = &mut (*curr).next;
        curr = (*curr).next;
    }

    if ret == 0 {
        if prev_ptr.is_null() {
            // Insert at head
            (*handler).next = (*headp).load(Ordering::Acquire);
            (*headp).store(handler, Ordering::Release);
        } else {
            // Insert in middle/end
            (*handler).next = *prev_ptr;
            *prev_ptr = handler;
        }
    }

    mutex.unlock();

    if add_netproto && ret == 0 {
        if inet6_add_protocol(netproto(protocol), protocol) != 0 {
            pr_err(b"xfrm6_protocol_register: can't add protocol\n".as_ptr() as *const c_char);
            ret = EAGAIN;
        }
    }

    ret
}

#[no_mangle]
pub unsafe extern "C" fn xfrm6_protocol_deregister(
    handler: *mut xfrm6_protocol,
    protocol: u8,
) -> c_int {
    let headp = proto_handlers(protocol);
    if headp.is_null() || handler.is_null() {
        return EINVAL;
    }

    let mutex = XFRM6_PROTOCOL_MUTEX.get_mut();
    mutex.lock();

    let mut t = (*headp).load(Ordering::Acquire);
    let mut ret = ENOENT;
    let mut prev_ptr: *mut *mut xfrm6_protocol = ptr::null_mut();

    while !t.is_null() {
        if t == handler {
            if prev_ptr.is_null() {
                // Remove from head
                (*headp).store((*handler).next, Ordering::Release);
            } else {
                // Remove from middle/end
                *prev_ptr = (*handler).next;
            }
            ret = 0;
            break;
        }
        prev_ptr = &mut (*t).next;
        t = (*t).next;
    }

    mutex.unlock();

    if ret == 0 {
        let empty = (*headp).load(Ordering::Acquire).is_null();
        if empty {
            if inet6_del_protocol(netproto(protocol), protocol) < 0 {
                pr_err(
                    b"xfrm6_protocol_deregister: can't remove protocol\n".as_ptr() as *const c_char,
                );
                ret = EAGAIN;
            }
        }
    }

    synchronize_net();
    ret
}

// Implementation deferred.
unsafe fn netproto(protocol: u8) -> *mut inet6_protocol {
    match protocol {
        IPPROTO_ESP => ESP6_PROTOCOL.get_mut() as *const inet6_protocol as *mut inet6_protocol,
        IPPROTO_AH => AH6_PROTOCOL.get_mut() as *const inet6_protocol as *mut inet6_protocol,
        IPPROTO_COMP => IPCOMP6_PROTOCOL.get_mut() as *const inet6_protocol as *mut inet6_protocol,
        _ => ptr::null_mut(),
    }
}

static ESP6_PROTOCOL: SyncWrapper<inet6_protocol> = SyncWrapper::new(inet6_protocol {
    handler: xfrm6_esp_rcv,
    err_handler: xfrm6_esp_err,
    flags: INET6_PROTO_NOPOLICY,
});

static AH6_PROTOCOL: SyncWrapper<inet6_protocol> = SyncWrapper::new(inet6_protocol {
    handler: xfrm6_ah_rcv,
    err_handler: xfrm6_ah_err,
    flags: INET6_PROTO_NOPOLICY,
});

static IPCOMP6_PROTOCOL: SyncWrapper<inet6_protocol> = SyncWrapper::new(inet6_protocol {
    handler: xfrm6_ipcomp_rcv,
    err_handler: xfrm6_ipcomp_err,
    flags: INET6_PROTO_NOPOLICY,
});

static XFRM6_INPUT_AFINFO: SyncWrapper<xfrm_input_afinfo> = SyncWrapper::new(xfrm_input_afinfo {
    family: AF_INET6,
    callback: xfrm6_rcv_cb,
});

#[no_mangle]
pub unsafe extern "C" fn xfrm6_protocol_init() -> c_int {
    xfrm_input_register_afinfo(XFRM6_INPUT_AFINFO.get_mut())
}

#[no_mangle]
pub unsafe extern "C" fn xfrm6_protocol_fini() {
    xfrm_input_unregister_afinfo(XFRM6_INPUT_AFINFO.get_mut())
}

// Dummy implementations for required kernel functions
#[no_mangle]
pub unsafe extern "C" fn pr_err(_fmt: *const c_char) {
    // Dummy implementation
}

#[no_mangle]
pub unsafe extern "C" fn synchronize_net() {
    // Dummy implementation
}

#[no_mangle]
pub unsafe extern "C" fn inet6_add_protocol(_proto: *mut inet6_protocol, _protocol: u8) -> c_int {
    // Dummy implementation
    0
}

#[no_mangle]
pub unsafe extern "C" fn inet6_del_protocol(_proto: *mut inet6_protocol, _protocol: u8) -> c_int {
    // Dummy implementation
    0
}

#[no_mangle]
pub unsafe extern "C" fn xfrm_input_register_afinfo(_afinfo: *mut xfrm_input_afinfo) -> c_int {
    // Dummy implementation
    0
}

#[no_mangle]
pub unsafe extern "C" fn xfrm_input_unregister_afinfo(_afinfo: *mut xfrm_input_afinfo) {
    // Dummy implementation
}

// Test cases (conditional compilation)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_protocol_registration() {
        // This would be a real test in a kernel environment
        // SAFETY: Calling xfrm6_protocol_register with null handler for error handling test.
        unsafe {
            let handler = ptr::null_mut();
            assert_eq!(xfrm6_protocol_register(handler, IPPROTO_ESP), EINVAL);
        }
    }

    #[test]
    fn test_null_skb_handling() {
        assert_eq!(xfrm6_esp_rcv(ptr::null_mut()), EINVAL);
        assert_eq!(xfrm6_ah_rcv(ptr::null_mut()), EINVAL);
        assert_eq!(xfrm6_ipcomp_rcv(ptr::null_mut()), EINVAL);
        assert_eq!(xfrm6_esp_err(ptr::null_mut(), ptr::null_mut(), 0, 0, 0, 0), EINVAL);
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
