#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(unused_assignments)]

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

use kernel_types::*;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const EEXIST: c_int = -17;
pub const ENOENT: c_int = -2;
pub const EAGAIN: c_int = -11;

pub const AF_INET6: c_int = 10; pub const AF_INET: c_int = 2; pub const AF_MPLS: c_int = 25;

pub const INET6_PROTO_NOPOLICY: c_int = 1 << 0; pub const INET6_PROTO_FINAL: c_int = 1 << 1;

pub const IPPROTO_IPV6: c_int = 41; pub const IPPROTO_IPIP: c_int = 4; pub const IPPROTO_MPLS: c_int = 137;

#[repr(C)]
pub struct sk_buff { _priv: [u8; 0] }

#[repr(C)]
pub struct inet6_skb_parm { _priv: [u8; 0] }

pub type handler_func = unsafe extern "C" fn(*mut sk_buff) -> c_int;
pub type cb_handler_func = unsafe extern "C" fn(*mut sk_buff, c_int) -> c_int;
pub type err_handler_func =
    unsafe extern "C" fn(*mut sk_buff, *mut c_void, u8, u8, c_int, u32) -> c_int;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm6_tunnel {
    pub priority: c_int,
    pub handler: handler_func,
    pub cb_handler: Option<cb_handler_func>,
    pub err_handler: Option<err_handler_func>,
    pub next: *mut xfrm6_tunnel,
}

static TUNNEL6_HANDLERS: SyncWrapper<*mut xfrm6_tunnel> = SyncWrapper::new(core::ptr::null_mut());
static TUNNEL46_HANDLERS: SyncWrapper<*mut xfrm6_tunnel> = SyncWrapper::new(core::ptr::null_mut());
static TUNNELMPLS6_HANDLERS: SyncWrapper<*mut xfrm6_tunnel> = SyncWrapper::new(core::ptr::null_mut());

// Mutex for synchronization - represented as a raw mutex handle
static TUNNEL6_MUTEX: SyncWrapper<*mut c_void> = SyncWrapper::new(core::ptr::null_mut());

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet6_protocol {
    pub handler: handler_func,
    pub err_handler: Option<err_handler_func>,
    pub flags: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_input_afinfo {
    pub family: c_int,
    pub is_ipip: c_int,
    pub callback: unsafe extern "C" fn(*mut sk_buff, u8, c_int) -> c_int,
}

unsafe extern "C" {
    fn mutex_lock(mutex: *mut c_void);
    fn mutex_unlock(mutex: *mut c_void);
    fn pskb_may_pull(skb: *mut sk_buff, size: c_int) -> c_int;
    fn icmpv6_send(skb: *mut sk_buff, type_: c_int, code: c_int, info: u32);
    fn kfree_skb(skb: *mut sk_buff);
    fn inet6_add_protocol(proto: *const inet6_protocol, protocol: c_int) -> c_int;
    fn inet6_del_protocol(proto: *const inet6_protocol, protocol: c_int) -> c_int;
    fn xfrm_input_register_afinfo(afinfo: *const xfrm_input_afinfo) -> c_int;
    fn xfrm_input_unregister_afinfo(afinfo: *const xfrm_input_afinfo) -> c_int;
}

static TUNNEL6_PROTOCOL: inet6_protocol = inet6_protocol {
    handler: tunnel6_rcv,
    err_handler: Some(tunnel6_err),
    flags: INET6_PROTO_NOPOLICY | INET6_PROTO_FINAL,
};

static TUNNEL46_PROTOCOL: inet6_protocol = inet6_protocol {
    handler: tunnel46_rcv,
    err_handler: Some(tunnel46_err),
    flags: INET6_PROTO_NOPOLICY | INET6_PROTO_FINAL,
};

static TUNNELMPLS6_PROTOCOL: inet6_protocol = inet6_protocol {
    handler: tunnelmpls6_rcv,
    err_handler: Some(tunnelmpls6_err),
    flags: INET6_PROTO_NOPOLICY | INET6_PROTO_FINAL,
};

static TUNNEL6_INPUT_AFINFO: xfrm_input_afinfo = xfrm_input_afinfo {
    family: AF_INET6,
    is_ipip: 1,
    callback: tunnel6_rcv_cb,
};

#[no_mangle]
pub unsafe extern "C" fn xfrm6_tunnel_mpls_supported() -> c_int { 1 }

#[no_mangle]
pub unsafe extern "C" fn xfrm6_tunnel_register(handler: *mut xfrm6_tunnel, family: c_int) -> c_int {
    let _ret: c_int = EEXIST;
    let _priority = (*handler).priority;

    // Lock the mutex before modifying the list
    mutex_lock((*TUNNEL6_MUTEX.get_mut()));

    let mut ret = ENOENT;
    let priority = (*handler).priority;

    let mut pprev: *mut *mut xfrm6_tunnel = match family {
        AF_INET6 => TUNNEL6_HANDLERS.get_mut(),
        AF_INET => TUNNEL46_HANDLERS.get_mut(),
        AF_MPLS => TUNNELMPLS6_HANDLERS.get_mut(),
        _ => {
            mutex_unlock((*TUNNEL6_MUTEX.get_mut()));
            return EINVAL;
        }
    };

    while !(*pprev).is_null() {
        let current = *pprev;
        let current_priority = (*current).priority;
        if current_priority > priority {
            break;
        }
        if current_priority == priority {
            // Priority already exists
            mutex_unlock((*TUNNEL6_MUTEX.get_mut()));
            return EEXIST;
        }
        pprev = &mut (*current).next;
    }

    (*handler).next = *pprev;
    *pprev = handler;

    ret = 0;

    mutex_unlock((*TUNNEL6_MUTEX.get_mut()));
    ret
}

#[no_mangle]
pub unsafe extern "C" fn xfrm6_tunnel_deregister(handler: *mut xfrm6_tunnel, family: c_int) -> c_int {
    if handler.is_null() {
        return EINVAL;
    }

    mutex_lock((*TUNNEL6_MUTEX.get_mut()));

    let mut ret = ENOENT;
    let mut pprev: *mut *mut xfrm6_tunnel = match family {
        AF_INET6 => TUNNEL6_HANDLERS.get_mut(),
        AF_INET => TUNNEL46_HANDLERS.get_mut(),
        AF_MPLS => TUNNELMPLS6_HANDLERS.get_mut(),
        _ => {
            mutex_unlock((*TUNNEL6_MUTEX.get_mut()));
            return EINVAL;
        }
    };

    let mut current: *mut xfrm6_tunnel = *pprev;
    while !current.is_null() {
        if current == handler {
            *pprev = (*current).next;
            ret = 0;
            break;
        }
        pprev = &mut (*current).next;
        current = *pprev;
    }

    mutex_unlock((*TUNNEL6_MUTEX.get_mut()));

    // Synchronize with network
    synchronize_net();

    ret
}

// Helper function for synchronization
#[no_mangle]
pub unsafe extern "C" fn synchronize_net() {
    // In real kernel code, this would synchronize with network operations
    // For this translation, we'll just return
}

// Implementation of tunnelmpls6_rcv
#[no_mangle]
pub unsafe extern "C" fn tunnelmpls6_rcv(skb: *mut sk_buff) -> c_int {
    if pskb_may_pull(skb, core::mem::size_of::<ipv6hdr>() as c_int) == 0 {
        kfree_skb(skb);
        return 0;
    }

    let mut handler: *mut xfrm6_tunnel = (*TUNNELMPLS6_HANDLERS.get_mut());
    while !handler.is_null() {
        if ((*handler).handler)(skb) == 0 {
            return 0;
        }
        handler = (*handler).next;
    }

    icmpv6_send(skb, ICMPV6_DEST_UNREACH, ICMPV6_PORT_UNREACH, 0);
    kfree_skb(skb);
    0
}

// Implementation of tunnel6_rcv
#[no_mangle]
pub unsafe extern "C" fn tunnel6_rcv(skb: *mut sk_buff) -> c_int {
    if pskb_may_pull(skb, core::mem::size_of::<ipv6hdr>() as c_int) == 0 {
        kfree_skb(skb);
        return 0;
    }

    let mut handler: *mut xfrm6_tunnel = (*TUNNEL6_HANDLERS.get_mut());
    while !handler.is_null() {
        if ((*handler).handler)(skb) == 0 {
            return 0;
        }
        handler = (*handler).next;
    }

    icmpv6_send(skb, ICMPV6_DEST_UNREACH, ICMPV6_PORT_UNREACH, 0);
    kfree_skb(skb);
    0
}

// Implementation of tunnel6_rcv_cb
#[no_mangle]
pub unsafe extern "C" fn tunnel6_rcv_cb(skb: *mut sk_buff, proto: u8, err: c_int) -> c_int {
    let head: *mut xfrm6_tunnel = if proto == IPPROTO_IPV6 as u8 {
        (*TUNNEL6_HANDLERS.get_mut())
    } else {
        (*TUNNEL46_HANDLERS.get_mut())
    };

    let mut handler: *mut xfrm6_tunnel = head;
    while !handler.is_null() {
        if let Some(cb_handler) = (*handler).cb_handler {
            let ret = cb_handler(skb, err);
            if ret <= 0 {
                return ret;
            }
        }
        handler = (*handler).next;
    }

    0
}

// Implementation of tunnel46_rcv
#[no_mangle]
pub unsafe extern "C" fn tunnel46_rcv(skb: *mut sk_buff) -> c_int {
    if pskb_may_pull(skb, core::mem::size_of::<iphdr>() as c_int) == 0 {
        kfree_skb(skb);
        return 0;
    }

    let mut handler: *mut xfrm6_tunnel = (*TUNNEL46_HANDLERS.get_mut());
    while !handler.is_null() {
        if ((*handler).handler)(skb) == 0 {
            return 0;
        }
        handler = (*handler).next;
    }

    icmpv6_send(skb, ICMPV6_DEST_UNREACH, ICMPV6_PORT_UNREACH, 0);
    kfree_skb(skb);
    0
}

// Implementation of tunnel6_err
#[no_mangle]
pub unsafe extern "C" fn tunnel6_err(
    skb: *mut sk_buff,
    opt: *mut c_void,
    type_: u8,
    code: u8,
    offset: c_int,
    info: u32,
) -> c_int {
    let mut handler: *mut xfrm6_tunnel = (*TUNNEL6_HANDLERS.get_mut());
    while !handler.is_null() {
        if let Some(err_handler) = (*handler).err_handler {
            if err_handler(skb, opt, type_, code, offset, info) == 0 {
                return 0;
            }
        }
        handler = (*handler).next;
    }

    -ENOENT
}

// Implementation of tunnel46_err
#[no_mangle]
pub unsafe extern "C" fn tunnel46_err(
    skb: *mut sk_buff,
    opt: *mut c_void,
    type_: u8,
    code: u8,
    offset: c_int,
    info: u32,
) -> c_int {
    let mut handler: *mut xfrm6_tunnel = (*TUNNEL46_HANDLERS.get_mut());
    while !handler.is_null() {
        if let Some(err_handler) = (*handler).err_handler {
            if err_handler(skb, opt, type_, code, offset, info) == 0 {
                return 0;
            }
        }
        handler = (*handler).next;
    }

    -ENOENT
}

// Implementation of tunnelmpls6_err
#[no_mangle]
pub unsafe extern "C" fn tunnelmpls6_err(
    skb: *mut sk_buff,
    opt: *mut c_void,
    type_: u8,
    code: u8,
    offset: c_int,
    info: u32,
) -> c_int {
    let mut handler: *mut xfrm6_tunnel = (*TUNNELMPLS6_HANDLERS.get_mut());
    while !handler.is_null() {
        if let Some(err_handler) = (*handler).err_handler {
            if err_handler(skb, opt, type_, code, offset, info) == 0 {
                return 0;
            }
        }
        handler = (*handler).next;
    }

    -ENOENT
}

// Module initialization function
#[no_mangle]
pub unsafe extern "C" fn tunnel6_init() -> c_int {
    if inet6_add_protocol(&TUNNEL6_PROTOCOL, IPPROTO_IPV6) != 0 {
        return -EAGAIN;
    }

    if inet6_add_protocol(&TUNNEL46_PROTOCOL, IPPROTO_IPIP) != 0 {
        inet6_del_protocol(&TUNNEL6_PROTOCOL, IPPROTO_IPV6);
        return -EAGAIN;
    }

    if xfrm6_tunnel_mpls_supported() != 0 {
        if inet6_add_protocol(&TUNNELMPLS6_PROTOCOL, IPPROTO_MPLS) != 0 {
            inet6_del_protocol(&TUNNEL6_PROTOCOL, IPPROTO_IPV6);
            inet6_del_protocol(&TUNNEL46_PROTOCOL, IPPROTO_IPIP);
            return -EAGAIN;
        }
    }

    if xfrm6_tunnel_mpls_supported() != 0 {
        if xfrm_input_register_afinfo(&TUNNEL6_INPUT_AFINFO) != 0 {
            inet6_del_protocol(&TUNNEL6_PROTOCOL, IPPROTO_IPV6);
            inet6_del_protocol(&TUNNEL46_PROTOCOL, IPPROTO_IPIP);
            if xfrm6_tunnel_mpls_supported() != 0 {
                inet6_del_protocol(&TUNNELMPLS6_PROTOCOL, IPPROTO_MPLS);
            }
            return -EAGAIN;
        }
    }

    0
}

// Module cleanup function
#[no_mangle]
pub unsafe extern "C" fn tunnel6_fini() {
    if xfrm6_tunnel_mpls_supported() != 0 {
        if xfrm_input_unregister_afinfo(&TUNNEL6_INPUT_AFINFO) != 0 {
            // Handle error
        }
    }

    if inet6_del_protocol(&TUNNEL46_PROTOCOL, IPPROTO_IPIP) != 0 {
        // Handle error
    }

    if inet6_del_protocol(&TUNNEL6_PROTOCOL, IPPROTO_IPV6) != 0 {
        // Handle error
    }

    if xfrm6_tunnel_mpls_supported() != 0 {
        if inet6_del_protocol(&TUNNELMPLS6_PROTOCOL, IPPROTO_MPLS) != 0 {
            // Handle error
        }
    }
}

// Module macros
#[no_mangle]
pub unsafe extern "C" fn module_init() {
    tunnel6_init();
}

#[no_mangle]
pub unsafe extern "C" fn module_exit() {
    tunnel6_fini();
}

// Constants for ICMPv6
pub const ICMPV6_DEST_UNREACH: c_int = 3; pub const ICMPV6_PORT_UNREACH: c_int = 4;

#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------------
    // Test 1: Error-code constants match their canonical Linux kernel values.
    // -----------------------------------------------------------------------
    #[test]
    fn test_error_code_constants() {
        assert_eq!(EINVAL, -22, "EINVAL must be -22");
        assert_eq!(ENOMEM, -12, "ENOMEM must be -12");
        assert_eq!(EEXIST, -17, "EEXIST must be -17");
        assert_eq!(ENOENT, -2,  "ENOENT must be -2");
        assert_eq!(EAGAIN, -11, "EAGAIN must be -11");
    }

    // -----------------------------------------------------------------------
    // Test 2: Address-family constants match canonical Linux values.
    // -----------------------------------------------------------------------
    #[test]
    fn test_address_family_constants() {
        assert_eq!(AF_INET6, 10, "AF_INET6 must be 10");
        assert_eq!(AF_INET,  2,  "AF_INET must be 2");
        assert_eq!(AF_MPLS,  25, "AF_MPLS must be 25");
    }

    // -----------------------------------------------------------------------
    // Test 3: IP protocol number constants match canonical Linux values.
    // -----------------------------------------------------------------------
    #[test]
    fn test_ipproto_constants() {
        assert_eq!(IPPROTO_IPV6, 41,  "IPPROTO_IPV6 must be 41");
        assert_eq!(IPPROTO_IPIP, 4,   "IPPROTO_IPIP must be 4");
        assert_eq!(IPPROTO_MPLS, 137, "IPPROTO_MPLS must be 137");
    }

    // -----------------------------------------------------------------------
    // Test 4: ICMPv6 constants and inet6 protocol flag bitmasks.
    // -----------------------------------------------------------------------
    #[test]
    fn test_icmpv6_and_proto_flag_constants() {
        assert_eq!(ICMPV6_DEST_UNREACH,  3, "ICMPV6_DEST_UNREACH must be 3");
        assert_eq!(ICMPV6_PORT_UNREACH,  4, "ICMPV6_PORT_UNREACH must be 4");
        // INET6_PROTO_NOPOLICY = 1 << 0 = 1, INET6_PROTO_FINAL = 1 << 1 = 2
        assert_eq!(INET6_PROTO_NOPOLICY, 1, "INET6_PROTO_NOPOLICY must be 1");
        assert_eq!(INET6_PROTO_FINAL,    2, "INET6_PROTO_FINAL must be 2");
        // Combined flags used on all three protocol descriptors
        let combined = INET6_PROTO_NOPOLICY | INET6_PROTO_FINAL;
        assert_eq!(combined, 3, "combined NOPOLICY|FINAL must be 3");
    }

    // -----------------------------------------------------------------------
    // Test 5: xfrm6_tunnel_deregister rejects a null handler pointer.
    //
    // The function checks `handler.is_null()` before acquiring the mutex,
    // so this is safe to call even though the global mutex is a null pointer.
    // -----------------------------------------------------------------------
    #[test]
    fn test_deregister_null_handler_returns_einval() {
        // SAFETY: We pass a null handler pointer deliberately to exercise the
        // null-guard at the top of xfrm6_tunnel_deregister.  The function
        // returns EINVAL immediately, before touching any global state or the
        // mutex, so this is safe in a single-threaded test context.
        let ret = unsafe { xfrm6_tunnel_deregister(core::ptr::null_mut(), AF_INET6) };
        assert_eq!(ret, EINVAL, "null handler must yield EINVAL (-22)");
    }

    // -----------------------------------------------------------------------
    // Test 6: xfrm6_tunnel_mpls_supported always returns 1 (MPLS enabled).
    // -----------------------------------------------------------------------
    #[test]
    fn test_mpls_supported_returns_one() {
        // SAFETY: xfrm6_tunnel_mpls_supported is a pure function with no
        // side-effects; it simply returns the compile-time constant 1.
        let supported = unsafe { xfrm6_tunnel_mpls_supported() };
        assert_eq!(supported, 1, "xfrm6_tunnel_mpls_supported must return 1");
    }

    // -----------------------------------------------------------------------
    // Test 7: synchronize_net is a no-op and must not panic or crash.
    // -----------------------------------------------------------------------
    #[test]
    fn test_synchronize_net_is_noop() {
        // SAFETY: synchronize_net contains no unsafe operations; it is an
        // empty routine that immediately returns.  Calling it here is safe.
        unsafe { synchronize_net() };
        // If we reach this point the call succeeded without crashing.
    }

    // -----------------------------------------------------------------------
    // Test 8: SyncWrapper::new constructs successfully and get_mut returns a
    //         valid mutable reference to the contained value.
    // -----------------------------------------------------------------------
    #[test]
    fn test_sync_wrapper_new_and_get_mut() {
        let wrapper: SyncWrapper<i32> = SyncWrapper::new(42_i32);
        // SAFETY: The wrapper is stack-allocated, single-threaded, and not
        // shared across threads in this test.  Exclusive access is guaranteed
        // by the local scope, so calling get_mut is safe here.
        let val = unsafe { wrapper.get_mut() };
        assert_eq!(*val, 42, "SyncWrapper must expose the stored value via get_mut");
        *val = 100;
        // SAFETY: Same guarantees as above; still single-threaded and local.
        assert_eq!(unsafe { *wrapper.get_mut() }, 100, "mutated value must persist");
    }
}

#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
