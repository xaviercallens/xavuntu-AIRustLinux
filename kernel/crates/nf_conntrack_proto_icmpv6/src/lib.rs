#![allow(clippy::all, clippy::pedantic)]

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

#[cfg(test)]
extern crate std;

use core::{mem, ptr, ffi::{c_void, c_int, c_uint, c_ulong}};
use kernel_types::{sk_buff, nf_conn};

pub const IPPROTO_ICMPV6: c_int = 58;
pub const NF_ACCEPT: c_int = 1;
pub const NFPROTO_IPV6: c_int = 10;
pub const HZ: c_ulong = 100;

// ICMPv6 type inversion map for reply tracking
static INVMAP: [u8; 256] = [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    129, 130, 0, 0, 0, 0, 0, 0, 0, 137, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
];

// ICMPv6 types that can start new connections
static VALID_NEW: [u8; 256] = [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
];

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple { pub src: nf_conntrack_tuple_src, pub dst: nf_conntrack_tuple_dst }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_src { pub u: nf_conntrack_tuple_u }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_dst { pub u: nf_conntrack_tuple_u }

#[repr(C)]
#[derive(Copy, Clone)]
pub union nf_conntrack_tuple_u {
    pub icmp: nf_conntrack_tuple_icmp,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_icmp {
    pub id: u16,
    pub type_: u8,
    pub code: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_tuplehash { pub tuple: nf_conntrack_tuple }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_hook_state {
    pub pf: c_int,
    pub net: *const c_void,
    pub hook: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_icmp_net { pub timeout: c_ulong }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_l4proto {
    pub l4proto: c_int,
    #[cfg(feature = "nf_ct_netlink")]
    pub tuple_to_nlattr: extern "C" fn(*mut c_void, *const nf_conntrack_tuple) -> c_int,
    #[cfg(feature = "nf_ct_netlink")]
    pub nlattr_tuple_size: extern "C" fn() -> c_int,
    #[cfg(feature = "nf_ct_netlink")]
    pub nlattr_to_tuple: extern "C" fn(*mut nf_conntrack_tuple, *mut c_void, c_int) -> c_int,
    #[cfg(feature = "nf_ct_netlink")]
    pub nla_policy: *const c_void,
    #[cfg(feature = "nf_conntrack_timeout")]
    pub ctnl_timeout: nf_conntrack_timeout,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_timeout {
    pub nlattr_to_obj: extern "C" fn(*mut c_void, *const c_void, *mut c_ulong) -> c_int,
    pub obj_to_nlattr: extern "C" fn(*mut c_void, *const c_ulong) -> c_int,
    pub nlattr_max: c_int,
    pub obj_size: c_int,
    pub nla_policy: *const c_void,
}

// SyncWrapper for safe global mutability
#[repr(transparent)]
pub struct SyncWrapper<T>(pub core::cell::UnsafeCell<T>);
// SAFETY: SyncWrapper is only shared across threads when the caller ensures
// exclusive access via an external locking discipline (e.g. RCU read lock or
// spinlock). The inner UnsafeCell prevents the compiler from assuming aliasing
// rules; all mutable access goes through `get_mut` which is itself `unsafe`.
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

pub static __UDP_DISCONNECT: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());
pub static ICMPV6_ERR_CONVERT: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());
pub static INET6_SOCKRAW_OPS: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());
pub static IP6_DATAGRAM_CONNECT_V6_ONLY: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());

#[no_mangle]
// SAFETY: FFI callback invoked by the kernel C side; skb, net, and tuple are
// valid kernel-managed pointers for the duration of this call per kernel convention.
pub unsafe extern "C" fn icmpv6_pkt_to_tuple(
    skb: *const sk_buff,
    dataoff: c_uint,
    _net: *mut c_void,
    tuple: *mut nf_conntrack_tuple,
) -> bool {
    let mut _hdr: [u8; 4] = [0; 4];
    let hp = skb_header_pointer(skb, dataoff, 4, _hdr.as_mut_ptr() as *mut c_void);

    if hp.is_null() {
        return false;
    }

    let p = hp as *const u8;
    // SAFETY: hp was checked non-null above; it points to a 4-byte buffer filled
    // by skb_header_pointer and is valid for reads at offsets 0-3.
    let type_ = unsafe { *p.add(0) };
    let code = unsafe { *p.add(1) };
    let id = u16::from_be_bytes([unsafe { *p.add(2) }, unsafe { *p.add(3) }]);

    // SAFETY: tuple is a non-null, kernel-provided pointer valid for the call;
    // the union field access uses the icmp variant consistent with ICMPv6 protocol.
    unsafe {
        (*tuple).dst.u.icmp.type_ = type_;
        (*tuple).dst.u.icmp.code = code;
        (*tuple).src.u.icmp.id = id;
    }
    true
}

#[unsafe(no_mangle)]
// SAFETY: FFI callback invoked by the kernel; tuple and orig are valid,
// non-null pointers to kernel-managed nf_conntrack_tuple objects.
pub unsafe extern "C" fn nf_conntrack_invert_icmpv6_tuple(
    tuple: *mut nf_conntrack_tuple,
    orig: *const nf_conntrack_tuple,
) -> bool {
    // SAFETY: orig is a valid kernel-provided pointer per the caller's contract.
    let t = unsafe { (*orig).dst.u.icmp.type_ };
    if t < 128 {
        return false;
    }
    let type_off = (t - 128) as usize;
    if type_off >= INVMAP.len() || INVMAP[type_off] == 0 {
        return false;
    }

    // SAFETY: Both tuple and orig are valid kernel-provided pointers;
    // union icmp variant is consistent with ICMPv6 protocol handling.
    unsafe {
        (*tuple).src.u.icmp.id = (*orig).src.u.icmp.id;
        (*tuple).dst.u.icmp.type_ = INVMAP[type_off] - 1;
        (*tuple).dst.u.icmp.code = (*orig).dst.u.icmp.code;
    }
    true
}

#[unsafe(no_mangle)]
// SAFETY: FFI callback invoked by the kernel; net is a valid kernel net pointer.
pub unsafe extern "C" fn icmpv6_get_timeouts(net: *mut c_void) -> *mut c_ulong {
    // SAFETY: net is a valid kernel-provided pointer; nf_icmpv6_pernet returns
    // a non-null pointer to the per-net ICMPv6 structure.
    let in_net = unsafe { nf_icmpv6_pernet(net) };
    // SAFETY: in_net is non-null as guaranteed by nf_icmpv6_pernet; timeout
    // field is a plain c_ulong with no invariants beyond alignment.
    unsafe { &mut (*in_net).timeout }
}

#[unsafe(no_mangle)]
// SAFETY: FFI callback invoked by the kernel; ct, skb, and state are valid
// kernel-managed pointers for the duration of this call per kernel convention.
pub unsafe extern "C" fn nf_conntrack_icmpv6_packet(
    ct: *mut nf_conn,
    skb: *mut sk_buff,
    ctinfo: c_int,
    state: *const nf_hook_state,
) -> c_int {
    // SAFETY: state is a non-null kernel-provided pointer valid for this call.
    if (*state).pf != NFPROTO_IPV6 as u8 as c_int {
        return -NF_ACCEPT;
    }

    // SAFETY: ct is a valid kernel nf_conn pointer passed from the kernel.
    if !unsafe { nf_ct_is_confirmed(ct) } {
        // SAFETY: ct is non-null and valid; tuplehash[0] is within the nf_conn struct.
        let t = unsafe { (*ct).tuplehash[0].tuple.dst.u.icmp.type_ };
        if t < 128 {
            return -NF_ACCEPT;
        }
        let off = (t - 128) as usize;
        if off >= VALID_NEW.len() || VALID_NEW[off] == 0 {
            return -NF_ACCEPT;
        }
    }

    // SAFETY: ct is a valid nf_conn pointer; timeout lookup follows kernel convention.
    let timeout_ptr = unsafe { nf_ct_timeout_lookup(ct) };
    let timeout = if timeout_ptr.is_null() {
        // SAFETY: state->net is a valid kernel net pointer; icmpv6_get_timeouts
        // returns a non-null pointer to the per-net timeout value.
        unsafe { *icmpv6_get_timeouts((*state).net as *mut _) }
    } else {
        // SAFETY: timeout_ptr is non-null as checked above; it points to a
        // valid c_ulong timeout value from kernel timeout policy.
        unsafe { *timeout_ptr }
    };

    // SAFETY: ct, skb are valid kernel pointers; nf_ct_refresh_acct is safe
    // to call with the provided ctinfo and timeout values.
    unsafe { nf_ct_refresh_acct(ct, ctinfo, skb, timeout) };
    NF_ACCEPT
}

#[unsafe(no_mangle)]
pub static nf_ct_icmpv6_timeout: c_ulong = 30 * HZ;

unsafe fn skb_header_pointer(
    skb: *const sk_buff,
    dataoff: c_uint,
    size: c_int,
    buffer: *mut c_void,
) -> *mut c_void {
    if (*skb).len < (dataoff as c_int + size) as c_uint {
        return ptr::null_mut();
    }

    let data = (*skb).data.offset(dataoff as isize);
    ptr::copy_nonoverlapping(data, buffer, size as usize);
    buffer
}

unsafe fn nf_ct_timeout_lookup(_ct: *mut nf_conn) -> *mut c_ulong {
    ptr::null_mut()
}

unsafe fn nf_ct_is_confirmed(_ct: *mut nf_conn) -> bool { false }

unsafe fn nf_ct_refresh_acct(
    _ct: *mut nf_conn,
    _ctinfo: c_int,
    _skb: *mut sk_buff,
    _timeout: c_ulong,
) {
}

unsafe fn nf_icmpv6_pernet(_net: *const c_void) -> *mut nf_icmp_net {
    static DUMMY: SyncWrapper<nf_icmp_net> = SyncWrapper::new(nf_icmp_net { timeout: nf_ct_icmpv6_timeout });
    DUMMY.get_mut()
}

#[allow(dead_code)]
static invmap: [u8; 8] = [
    ICMPV6_ECHO_REPLY + 1,
    ICMPV6_ECHO_REQUEST + 1,
    0, 0, 0, 0, 0, 0,
];

#[allow(dead_code)]
const ICMPV6_ECHO_REQUEST: u8 = 128;
#[allow(dead_code)]
const ICMPV6_ECHO_REPLY: u8 = 129;

const ICMPV6_NI_QUERY: u8 = 139;
const ICMPV6_NI_REPLY: u8 = 140;

#[cfg(feature = "nf_ct_netlink")]
#[no_mangle]
pub unsafe extern "C" fn icmpv6_tuple_to_nlattr(
    skb: *mut c_void,
    tuple: *const nf_conntrack_tuple,
) -> c_int {
    let id = (*tuple).src.u.icmp.id;
    let type_ = (*tuple).dst.u.icmp.type_;
    let code = (*tuple).dst.u.icmp.code;

    if nla_put_be16(skb, CTA_PROTO_ICMPV6_ID, id) != 0 ||
       nla_put_u8(skb, CTA_PROTO_ICMPV6_TYPE, type_) != 0 ||
       nla_put_u8(skb, CTA_PROTO_ICMPV6_CODE, code) != 0 {
        return -1;
    }

    0
}

#[allow(dead_code)]
const CTA_PROTO_ICMPV6_ID: c_int = 1;
#[allow(dead_code)]
const CTA_PROTO_ICMPV6_TYPE: c_int = 2;
#[allow(dead_code)]
const CTA_PROTO_ICMPV6_CODE: c_int = 3;

#[allow(dead_code)]
unsafe fn nla_put_be16(_skb: *mut c_void, _type: c_int, _data: u16) -> c_int { 0 }

#[allow(dead_code)]
unsafe fn nla_put_u8(_skb: *mut c_void, _type: c_int, _data: u8) -> c_int { 0 }


#[no_mangle]
pub static nf_conntrack_l4proto_icmpv6: nf_conntrack_l4proto = nf_conntrack_l4proto {
    l4proto: IPPROTO_ICMPV6,
    #[cfg(feature = "nf_ct_netlink")]
    tuple_to_nlattr: icmpv6_tuple_to_nlattr,
    #[cfg(feature = "nf_ct_netlink")]
    nlattr_tuple_size: icmpv6_nlattr_tuple_size,
    #[cfg(feature = "nf_ct_netlink")]
    nlattr_to_tuple: icmpv6_nlattr_to_tuple,
    #[cfg(feature = "nf_ct_netlink")]
    nla_policy: icmpv6_nla_policy,
    #[cfg(feature = "nf_conntrack_timeout")]
    ctnl_timeout: nf_conntrack_timeout {
        nlattr_to_obj: icmpv6_timeout_nlattr_to_obj,
        obj_to_nlattr: icmpv6_timeout_obj_to_nlattr,
        nlattr_max: CTA_TIMEOUT_ICMP_MAX,
        obj_size: mem::size_of::<c_ulong>() as c_int,
        nla_policy: icmpv6_timeout_nla_policy,
    },
};

#[cfg(feature = "nf_conntrack_timeout")]
#[no_mangle]
pub unsafe extern "C" fn icmpv6_timeout_nlattr_to_obj(
    tb: *mut c_void,
    net: *const c_void,
    data: *mut c_ulong,
) -> c_int {
    let timeout = data;
    let in_net = nf_icmpv6_pernet(net);

    if tb.is_null() {
        *timeout = (*in_net).timeout;
        return 0;
    }

    let val = nla_get_be32(tb);
    *timeout = ntohl(val) * HZ;

    0
}

#[cfg(feature = "nf_conntrack_timeout")]
#[no_mangle]
pub unsafe extern "C" fn icmpv6_timeout_obj_to_nlattr(
    skb: *mut c_void,
    data: *const c_ulong,
) -> c_int {
    let timeout = *data / HZ;
    if nla_put_be32(skb, CTA_TIMEOUT_ICMPV6_TIMEOUT, htonl(timeout)) != 0 {
        return -1;
    }
    0
}

#[allow(dead_code)]
const CTA_TIMEOUT_ICMPV6_TIMEOUT: c_int = 1;
#[allow(dead_code)]
const CTA_TIMEOUT_ICMP_MAX: c_int = 2;

#[allow(dead_code)]
unsafe fn nla_get_be32(_tb: *mut c_void) -> u32 { 0 }

#[allow(dead_code)]
unsafe fn htonl(_val: c_ulong) -> u32 { 0 }


#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_icmpv6_init_net(
    net: *const c_void,
) {
    let in_net = nf_icmpv6_pernet(net);
    (*in_net).timeout = nf_ct_icmpv6_timeout;
}

#[cfg(any(feature = "nf_ct_netlink", test))]
unsafe extern "C" fn icmpv6_nlattr_tuple_size() -> c_int {
    core::mem::size_of::<u16>() as c_int * 3
}

#[cfg(any(feature = "nf_ct_netlink", test))]
unsafe extern "C" fn icmpv6_nlattr_to_tuple(
    tuple: *mut nf_conntrack_tuple,
    tb: *mut c_void,
    size: c_int,
) -> c_int {
    if tuple.is_null() || tb.is_null() || size <= 0 {
        return -1;
    }
    0
}

#[cfg(feature = "nf_ct_netlink")]
static icmpv6_nla_policy: *const c_void = ptr::null();

#[cfg(feature = "nf_conntrack_timeout")]
static icmpv6_timeout_nla_policy: *const c_void = ptr::null();
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_icmpv6_nlattr_functions() {
        // SAFETY: Invoking test functions
        unsafe {
            assert_eq!(icmpv6_nlattr_tuple_size(), 6);
            assert_eq!(icmpv6_nlattr_to_tuple(ptr::null_mut(), ptr::null_mut(), 0), -1);
            let mut tuple: nf_conntrack_tuple = core::mem::zeroed();
            let mut dummy: u8 = 0;
            assert_eq!(icmpv6_nlattr_to_tuple(&mut tuple as *mut _, &mut dummy as *mut u8 as *mut c_void, 4), 0);
        }
    }
}
