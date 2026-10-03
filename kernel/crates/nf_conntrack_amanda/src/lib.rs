#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
// Amanda connection tracking module for Linux kernel
//
// This is an FFI-compatible Rust translation of the Linux kernel C implementation.
// ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons)]

use core::ffi::{c_char, c_int, c_uint, c_void};
use core::panic::PanicInfo;
use core::ptr;
use core::sync::atomic::{AtomicPtr, Ordering};

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

pub const IPPROTO_UDP: u8 = 17;
pub const AF_INET: u8 = 2;
pub const AF_INET6: u8 = 10;
pub const IP_CT_DIR_ORIGINAL: u8 = 0;
pub const NF_ACCEPT: c_int = 0;
pub const NF_DROP: c_int = 1;
pub const NF_CT_EXPECT_CLASS_DEFAULT: u8 = 0;
pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const IPS_NAT_MASK: u32 = 0x0000FF00;

pub type size_t = usize;

pub type socklen_t = u32;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple { pub src: nf_conntrack_tuple_ip, pub dst: nf_conntrack_tuple_ip }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_ip { pub u3: nf_conntrack_tuple_ip_u3 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_ip_u3 { pub _addr: [u8; 16] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_tuplehash { pub tuple: nf_conntrack_tuple }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn { pub tuplehash: [nf_conn_tuplehash; 2], pub status: u32 }

#[repr(C)]
pub struct nf_conntrack_expect { pub _data: [u8; 1] }

#[repr(C)]
pub struct ts_config { pub _data: [u8; 1] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_expect_policy { pub max_expected: c_uint, pub timeout: c_uint }

pub type nf_nat_amanda_hook_t = unsafe extern "C" fn(
    *mut c_void,
    c_int,
    c_uint,
    c_uint,
    c_uint,
    *mut nf_conntrack_expect,
) -> c_int;

#[repr(C)]
pub struct SearchPattern {
    pub string: *const c_char,
    pub len: size_t,
    pub ts: *mut ts_config,
}

static MASTER_TIMEOUT: SyncWrapper<c_uint> = SyncWrapper::new(300);

static TS_ALGO: &[u8] = b"kmp\0";
static HELPER_NAME: &[u8] = b"amanda\0";
static NAT_MOD_NAME: &[u8] = b"nf_nat_amanda\0";

static NF_NAT_AMANDA_HOOK: AtomicPtr<c_void> = AtomicPtr::new(ptr::null_mut());

static SEARCH: SyncWrapper<[SearchPattern; 6]> = SyncWrapper::new([
    SearchPattern {
        string: b"CONNECT ".as_ptr() as *const c_char,
        len: 8,
        ts: ptr::null_mut(),
    },
    SearchPattern {
        string: b"\n".as_ptr() as *const c_char,
        len: 1,
        ts: ptr::null_mut(),
    },
    SearchPattern {
        string: b"DATA ".as_ptr() as *const c_char,
        len: 5,
        ts: ptr::null_mut(),
    },
    SearchPattern {
        string: b"MESG ".as_ptr() as *const c_char,
        len: 5,
        ts: ptr::null_mut(),
    },
    SearchPattern {
        string: b"INDEX ".as_ptr() as *const c_char,
        len: 6,
        ts: ptr::null_mut(),
    },
    SearchPattern {
        string: b"STATE ".as_ptr() as *const c_char,
        len: 6,
        ts: ptr::null_mut(),
    },
]);

unsafe extern "C" {
    fn skb_find_text(skb: *mut c_void, from: c_uint, to: c_uint, ts: *mut ts_config) -> c_uint;
    fn nf_ct_refresh(ct: *mut nf_conn, skb: *mut c_void, timeout: c_uint);
    fn nf_ct_expect_alloc(ct: *mut nf_conn) -> *mut nf_conntrack_expect;
    fn nf_ct_expect_init(
        exp: *mut nf_conntrack_expect,
        class: u8,
        l3num: u8,
        src: *const nf_conntrack_tuple_ip_u3,
        dst: *const nf_conntrack_tuple_ip_u3,
        protonum: u8,
        l4num: *const c_void,
        port: *const u16,
    );
    fn nf_ct_expect_related(exp: *mut nf_conntrack_expect, timeout: c_int) -> c_int;
    fn nf_ct_expect_put(exp: *mut nf_conntrack_expect);

    fn nf_conntrack_helpers_register(helpers: *mut nf_conntrack_helper, nhelpers: c_int) -> c_int;
    fn nf_conntrack_helpers_unregister(helpers: *mut nf_conntrack_helper, nhelpers: c_int);

    fn textSEARCH_prepare(
        algo: *const c_char,
        pattern: *const c_char,
        len: size_t,
        gfp: c_int,
        flags: c_int,
    ) -> *mut ts_config;
    fn textSEARCH_destroy(ts: *mut ts_config);

    fn nf_ct_helper_log(skb: *mut c_void, ct: *mut nf_conn, msg: *const c_char);
    fn skb_copy_bits(skb: *const c_void, offset: c_uint, to: *mut c_void, len: c_uint) -> c_int;
    fn nf_ct_l3num(ct: *const nf_conn) -> u8;
}

#[inline]
fn CTINFO2DIR(ctinfo: c_int) -> u8 { (ctinfo as u8) & 0x01 }

#[unsafe(no_mangle)]
pub unsafe extern "C" fn amanda_help(
    skb: *mut c_void,
    protoff: c_uint,
    ct: *mut nf_conn,
    ctinfo: c_int,
) -> c_int {
    let dataoff = protoff;
    let mut ret = NF_ACCEPT;

    // Only look at packets from the Amanda server
    if CTINFO2DIR(ctinfo) == IP_CT_DIR_ORIGINAL {
        return NF_ACCEPT;
    }

    nf_ct_refresh(ct, skb, *MASTER_TIMEOUT.get_mut());

    let exp = nf_ct_expect_alloc(ct);
    if exp.is_null() {
        return NF_DROP;
    }

    let start = skb_find_text(skb, dataoff, (*(skb as *mut sk_buff)).len, (*SEARCH.get_mut())[0].ts);
    if start == c_uint::MAX {
        return NF_ACCEPT;
    }
    let start = start + dataoff + (*SEARCH.get_mut())[0].len as c_uint;

    let stop = skb_find_text(skb, start, (*(skb as *mut sk_buff)).len, (*SEARCH.get_mut())[1].ts);
    if stop == c_uint::MAX {
        return NF_ACCEPT;
    }
    let stop = stop + start;

    for i in 2..=5 {
        let off = skb_find_text(skb, start, stop, (*SEARCH.get_mut())[i].ts);
        if off == c_uint::MAX {
            continue;
        }
        let off = off + start + (*SEARCH.get_mut())[i].len as c_uint;

        let mut pbuf: [u8; 6] = [0; 6];
        let len = (stop - off).min((pbuf.len() - 1) as c_uint);
        if skb_copy_bits(skb, off, pbuf.as_mut_ptr() as *mut c_void, len) != 0 {
            break;
        }
        pbuf[len as usize] = 0;

        let port = u16::from_str_radix(core::str::from_utf8_unchecked(&pbuf[..len as usize]), 10)
            .map_or(0, |n| n as u16);
        if port == 0 || len > 5 {
            break;
        }

        let exp = nf_ct_expect_alloc(ct);
        if exp.is_null() {
            nf_ct_helper_log(skb, ct, b"cannot alloc expectation\0".as_ptr() as *const c_char);
            ret = NF_DROP;
            continue;
        }

        let tuple = &(*ct).tuplehash[IP_CT_DIR_ORIGINAL as usize].tuple;
        nf_ct_expect_init(
            exp,
            NF_CT_EXPECT_CLASS_DEFAULT,
            nf_ct_l3num(ct),
            &tuple.src.u3,
            &tuple.dst.u3,
            IPPROTO_UDP,
            ptr::null(),
            &port,
        );

        let nf_nat_amanda = NF_NAT_AMANDA_HOOK.load(Ordering::Relaxed);
        if !nf_nat_amanda.is_null() && ((*ct).status & IPS_NAT_MASK) != 0 {
            let func: extern "C" fn(*mut c_void, c_int, c_uint, c_uint, c_uint, *mut nf_conntrack_expect) -> c_int
                = core::mem::transmute(nf_nat_amanda);
            ret = func(skb, ctinfo, protoff, off - dataoff, len, exp);
        } else if nf_ct_expect_related(exp, 0) != 0 {
            nf_ct_helper_log(skb, ct, b"cannot add expectation\0".as_ptr() as *const c_char);
            ret = NF_DROP;
        }
        nf_ct_expect_put(exp);
    }

    nf_ct_expect_put(exp);
    NF_ACCEPT
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}
