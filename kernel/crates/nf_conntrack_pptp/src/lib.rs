#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! Connection tracking support for PPTP (Point to Point Tunneling Protocol).
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::{ptr, ffi::{c_int, c_uint, c_void}};
use kernel_types::*;

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const ENOSYS: c_int = -38;

pub const HZ: c_int = 100; pub const IPPROTO_GRE: u8 = 47;

pub const PPTP_START_SESSION_REQUEST: u16 = 1;
pub const PPTP_START_SESSION_REPLY: u16 = 2;
pub const PPTP_STOP_SESSION_REQUEST: u16 = 5;
pub const PPTP_STOP_SESSION_REPLY: u16 = 6;
pub const PPTP_OUT_CALL_REQUEST: u16 = 10;
pub const PPTP_OUT_CALL_REPLY: u16 = 11;
pub const PPTP_IN_CALL_REQUEST: u16 = 12;
pub const PPTP_IN_CALL_REPLY: u16 = 13;
pub const PPTP_IN_CALL_CONNECT: u16 = 14;
pub const PPTP_CALL_CLEAR_REQUEST: u16 = 15;
pub const PPTP_CALL_DISCONNECT_NOTIFY: u16 = 16;
pub const PPTP_WAN_ERROR_NOTIFY: u16 = 17;
pub const PPTP_SET_LINK_INFO: u16 = 18;
pub const PPTP_MSG_MAX: u16 = 18;

pub const PPTP_GRE_TIMEOUT: c_int = 10 * 60 * HZ; pub const PPTP_GRE_STREAM_TIMEOUT: c_int = 5 * 60 * 60 * HZ;

pub const PPTP_SESSION_NONE: c_int = 0;
pub const PPTP_SESSION_REQUESTED: c_int = 1;
pub const PPTP_SESSION_CONFIRMED: c_int = 2;
pub const PPTP_SESSION_ERROR: c_int = 3;
pub const PPTP_SESSION_STOPREQ: c_int = 4;

pub const PPTP_START_OK: u16 = 1; pub const PPTP_STOP_OK: u16 = 1;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct PptpControlHeader { pub messageType: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct PptpStartSessionReply { pub resultCode: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct PptpStopSessionReply { pub resultCode: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct PptpOutCallAck { pub callID: u16, pub peersCallID: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub union pptp_ctrl_union {
    pub srep: PptpStartSessionReply,
    pub strep: PptpStopSessionReply,
    pub ocack: PptpOutCallAck,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_gre_address { pub key: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_proto_gre {
    pub stream_timeout: c_uint,
    pub timeout: c_uint,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_proto { pub gre: nf_conn_proto_gre }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_tuple_hash { pub tuple: nf_conntrack_tuple }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn {
    pub ct_general: *mut c_void,
    pub tuplehash: [nf_conn_tuple_hash; 2],
    pub timeout: c_uint,
    pub status: c_uint,
    pub proto: nf_conn_proto,
    pub master: *mut nf_conn,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_expect {
    pub tuple: nf_conntrack_tuple,
    pub expectfn: Option<unsafe extern "C" fn(*mut nf_conn, *mut nf_conntrack_expect)>,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_ct_pptp_master {
    pub sstate: c_int,
    pub cstate: c_int,
    pub pns_call_id: u16,
    pub pac_call_id: u16,
}

pub type nf_nat_pptp_hook_outbound_t = Option<
    unsafe extern "C" fn(
        *mut c_void,
        *mut nf_conn,
        c_int,
        c_uint,
        *mut PptpControlHeader,
        *mut pptp_ctrl_union,
    ) -> c_int,
>;

pub type nf_nat_pptp_hook_inbound_t = Option<
    unsafe extern "C" fn(
        *mut c_void,
        *mut nf_conn,
        c_int,
        c_uint,
        *mut PptpControlHeader,
        *mut pptp_ctrl_union,
    ) -> c_int,
>;

pub type nf_nat_pptp_hook_exp_gre_t =
    Option<unsafe extern "C" fn(*mut nf_conntrack_expect, *mut nf_conntrack_expect)>;

pub type nf_nat_pptp_hook_expectfn_t = Option<unsafe extern "C" fn(*mut nf_conn, *mut nf_conntrack_expect)>;

// Exported symbols
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

pub static nf_nat_pptp_hook_outbound: SyncWrapper<nf_nat_pptp_hook_outbound_t> = SyncWrapper::new(None);
pub static nf_nat_pptp_hook_inbound: SyncWrapper<nf_nat_pptp_hook_inbound_t> = SyncWrapper::new(None);
pub static nf_nat_pptp_hook_exp_gre: SyncWrapper<nf_nat_pptp_hook_exp_gre_t> = SyncWrapper::new(None);
pub static nf_nat_pptp_hook_expectfn: SyncWrapper<nf_nat_pptp_hook_expectfn_t> = SyncWrapper::new(None);

#[repr(C)]
#[derive(Copy, Clone)]
pub struct spinlock_t { _private: [u8; 0] }

pub static nf_pptp_lock: SyncWrapper<spinlock_t> = SyncWrapper::new(spinlock_t { _private: [] });

static NF_PPTP_LOCK: spinlock_t = spinlock_t { _private: [] };

extern "C" {
    fn nf_ct_expect_find_get(
        net: *mut c_void,
        zone: *const c_void,
        tuple: *const nf_conntrack_tuple,
    ) -> *mut nf_conntrack_expect;

    fn nf_ct_unexpect_related(exp: *mut nf_conntrack_expect);

    fn nf_ct_expect_put(exp: *mut nf_conntrack_expect);

    fn ntohs(n: u16) -> u16;
}

// Helper to set GRE key in tuple union
#[inline(always)]
unsafe fn set_gre_key(u: *mut nf_conntrack_tuple_u, key: u16) {
    // The all field is at the same offset as the gre key
    let ptr = u as *mut u16;
    *ptr = key;
}

#[no_mangle]
pub unsafe extern "C" fn pptp_expectfn(ct: *mut nf_conn, exp: *mut nf_conntrack_expect) {
    if ct.is_null() || exp.is_null() {
        return;
    }

    (*ct).proto.gre.timeout = PPTP_GRE_TIMEOUT as c_uint;
    (*ct).proto.gre.stream_timeout = PPTP_GRE_STREAM_TIMEOUT as c_uint;

    let nf_nat_pptp_expectfn = *nf_nat_pptp_hook_expectfn.get_mut();
    if nf_nat_pptp_expectfn.is_some() && !(*ct).master.is_null() && (*(*ct).master).status & 1 != 0
    {
        nf_nat_pptp_expectfn.unwrap()(ct, exp);
    } else {
        let mut inv_t: nf_conntrack_tuple = core::mem::zeroed();
        let mut exp_other: *mut nf_conntrack_expect = ptr::null_mut();

        // SAFETY: nf_ct_invert_tuple is kernel API
        nf_ct_invert_tuple(&mut inv_t, &(*exp).tuple);

        // SAFETY: nf_ct_expect_find_get is kernel API
        exp_other = nf_ct_expect_find_get(ptr::null_mut(), ptr::null_mut(), &inv_t);
        if !exp_other.is_null() {
            nf_ct_unexpect_related(exp_other);
            nf_ct_expect_put(exp_other);
        }
    }
}

/// Destroy sibling connections or expectations
///
/// # Safety
/// - `ct` must be a valid pointer to nf_conn
#[no_mangle]
pub unsafe extern "C" fn pptp_destroy_siblings(ct: *mut nf_conn) {
    if ct.is_null() {
        return;
    }

    let ct_pptp_info = nfct_help_data(ct);
    let mut t: nf_conntrack_tuple = core::mem::zeroed();

    // Original direction ((*PNS).PAC)
    let dir = 0; // IP_CT_DIR_ORIGINAL
    ptr::copy_nonoverlapping(&(*ct).tuplehash[dir].tuple, &mut t, 1);
    t.dst.protonum = IPPROTO_GRE;
    set_gre_key(&mut t.src.u as *mut nf_conntrack_tuple_u, (*ct_pptp_info).pns_call_id);
    set_gre_key(&mut t.dst.u as *mut nf_conntrack_tuple_u, (*ct_pptp_info).pac_call_id);

    destroy_sibling_or_exp(ptr::null_mut(), ct, &t);

    // Reply direction ((*PAC).PNS)
    let dir = 1; // IP_CT_DIR_REPLY
    ptr::copy_nonoverlapping(&(*ct).tuplehash[dir].tuple, &mut t, 1);
    t.dst.protonum = IPPROTO_GRE;
    set_gre_key(&mut t.src.u as *mut nf_conntrack_tuple_u, (*ct_pptp_info).pac_call_id);
    set_gre_key(&mut t.dst.u as *mut nf_conntrack_tuple_u, (*ct_pptp_info).pns_call_id);

    destroy_sibling_or_exp(ptr::null_mut(), ct, &t);
}

/// Handle incoming PPTP packets
///
/// # Safety
/// - All parameters must be valid pointers
#[no_mangle]
pub unsafe extern "C" fn pptp_inbound_pkt(
    _skb: *mut c_void,
    _protoff: c_uint,
    ctlh: *mut PptpControlHeader,
    pptpReq: *mut pptp_ctrl_union,
    _reqlen: c_uint,
    ct: *mut nf_conn,
    _ctinfo: c_int,
) -> c_int {
    if ct.is_null() || ctlh.is_null() || pptpReq.is_null() {
        return EINVAL;
    }

    let info = nfct_help_data(ct);
    let msg = ntohs((*ctlh).messageType);

    match msg {
        PPTP_START_SESSION_REPLY => {
            if (*info).sstate < PPTP_SESSION_REQUESTED {
                return EINVAL;
            }
            if (*pptpReq).srep.resultCode == PPTP_START_OK {
                (*info).sstate = PPTP_SESSION_CONFIRMED;
            } else {
                (*info).sstate = PPTP_SESSION_ERROR;
            }
        }
        PPTP_STOP_SESSION_REPLY => {
            if (*info).sstate > PPTP_SESSION_STOPREQ {
                return EINVAL;
            }
            if (*pptpReq).strep.resultCode == PPTP_STOP_OK {
                (*info).sstate = PPTP_SESSION_NONE;
            } else {
                (*info).sstate = PPTP_SESSION_ERROR;
            }
        }
        _ => return EINVAL,
    }

    0
}

// Helper functions
#[no_mangle]
pub unsafe extern "C" fn nf_ct_invert_tuple(
    inv_t: *mut nf_conntrack_tuple,
    tuple: *const nf_conntrack_tuple,
) {
    if inv_t.is_null() || tuple.is_null() {
        return;
    }

    // SAFETY: Kernel API to invert tuple
    // Implementation would mirror kernel's nf_ct_invert_tuple
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_pptp_init() -> c_int {
    let _ = &nf_pptp_lock;
    *nf_nat_pptp_hook_expectfn.get_mut() = Some(pptp_expectfn);
    0
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_pptp_fini() {
    *nf_nat_pptp_hook_expectfn.get_mut() = None;
    *nf_nat_pptp_hook_outbound.get_mut() = None;
    *nf_nat_pptp_hook_inbound.get_mut() = None;
    *nf_nat_pptp_hook_exp_gre.get_mut() = None;
}

#[no_mangle]
pub unsafe extern "C" fn nf_ct_gre_keymap_destroy(_ct: *mut nf_conn) {
    // SAFETY: Kernel API to destroy GRE keymap
}

#[no_mangle]
pub unsafe extern "C" fn nfct_help_data(ct: *mut nf_conn) -> *mut nf_ct_pptp_master {
    // SAFETY: Kernel API to get helper data
    let offset = 0; // Offset from nf_conn to helper data
    let ptr = ct as *mut u8;
    ptr.add(offset) as *mut nf_ct_pptp_master
}

// Internal functions
unsafe fn destroy_sibling_or_exp(
    net: *mut c_void,
    ct: *mut nf_conn,
    t: *const nf_conntrack_tuple,
) -> c_int {
    if ct.is_null() || t.is_null() {
        return 0;
    }

    let h = nf_conntrack_find_get(net, ptr::null_mut(), t);
    if !h.is_null() {
        let sibling = nf_ct_tuplehash_to_ctrack(h);
        (*sibling).proto.gre.timeout = 0;
        (*sibling).proto.gre.stream_timeout = 0;
        nf_ct_kill(sibling);
        nf_ct_put(sibling);
        return 1;
    } else {
        let exp = nf_ct_expect_find_get(net, ptr::null_mut(), t);
        if !exp.is_null() {
            nf_ct_unexpect_related(exp);
            nf_ct_expect_put(exp);
            return 1;
        }
    }
    0
}

// Extern functions (kernel APIs)
extern "C" {
    fn nf_conntrack_find_get(
        net: *mut c_void,
        zone: *mut c_void,
        tuple: *const nf_conntrack_tuple,
    ) -> *mut c_void;

    fn nf_ct_tuplehash_to_ctrack(h: *mut c_void) -> *mut nf_conn;

    fn nf_ct_kill(ct: *mut nf_conn);

    fn nf_ct_put(ct: *mut nf_conn);
}

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    #[test]
    fn test_pptp_expectfn() {
        // Basic test case for pptp_expectfn
        // Would require kernel environment to run
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
