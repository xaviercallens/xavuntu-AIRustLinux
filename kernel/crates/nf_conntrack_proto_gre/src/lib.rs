#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(static_mut_refs)]
#![allow(dead_code)]

use core::{mem, ptr, ffi::{c_int, c_uint, c_void}};

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

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

// Constants from C
pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOSYS: c_int = -38;
pub const EEXIST: c_int = -17;

// Constants
pub const GRE_CT_UNREPLIED: usize = 0;
pub const GRE_CT_REPLIED: usize = 1;
pub const GRE_CT_MAX: usize = 2;
pub const IP_CT_DIR_ORIGINAL: usize = 0;
pub const IP_CT_DIR_REPLY: usize = 1;
pub const IP_CT_DIR_MAX: usize = 2;
pub const IPPROTO_GRE: u8 = 47;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_inet_addr { pub all: [u32; 4] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_ipv4 { pub u3: nf_inet_addr, pub protonum: u8 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple {
    pub src: nf_conntrack_tuple_ipv4,
    pub dst: nf_conntrack_tuple_ipv4,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_gre { pub key: u16 }

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
pub struct nf_ct_gre_keymap {
    pub tuple: nf_conntrack_tuple,
    pub list: list_head,
    pub rcu: rcu_head,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_gre_net { pub keymap_list: list_head, pub timeouts: [c_uint; GRE_CT_MAX] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_gre { pub timeout: c_uint }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_ct_pptp_master { pub keymap: [*mut nf_ct_gre_keymap; IP_CT_DIR_MAX] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_l4proto { pub l4proto: u8 }

#[repr(C)]
pub struct sk_buff { _priv: [u8; 0] }

unsafe extern "C" {
    fn nf_ct_net(ct: *const nf_conn) -> *mut c_void;
    fn nfct_help_data(ct: *const nf_conn) -> *mut nf_ct_pptp_master;
    fn nf_ct_timeout_lookup(ct: *const nf_conn) -> *const c_uint;
    fn nf_ct_refresh_acct(ct: *mut nf_conn, ctinfo: c_int, skb: *mut sk_buff, timeout: c_uint);
    fn nf_conntrack_event_cache(event: c_int, ct: *mut nf_conn);
    fn skb_header_pointer(
        skb: *const sk_buff,
        dataoff: c_int,
        size: usize,
        ptr: *mut c_void,
    ) -> *mut c_void;
    fn nf_ct_dump_tuple(tuple: *const nf_conntrack_tuple);
    fn kmalloc(size: usize) -> *mut c_void;
    fn kfree(ptr: *mut c_void);
    fn list_add_tail(list: *mut list_head, entry: *mut list_head);
}

// Module-level statics
static KEYMAP_LOCK: SyncWrapper<c_int> = SyncWrapper::new(0); // Spinlock state word

fn spin_lock_bh(lock: *mut c_int) {
    unsafe { *lock = 1 }
}

fn spin_unlock_bh(lock: *mut c_int) {
    unsafe { *lock = 0 }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn nf_ct_gre_keymap_add(
    ct: *mut nf_conn,
    dir: c_int,
    t: *mut nf_conntrack_tuple,
) -> c_int {
    if ct.is_null() || t.is_null() {
        return EINVAL;
    }

    let dir_idx = dir as usize;
    if dir_idx >= IP_CT_DIR_MAX {
        return EINVAL;
    }

    let net = unsafe { nf_ct_net(ct) };
    if net.is_null() {
        return EINVAL;
    }

    let net_gre = unsafe { gre_pernet(net) };
    if net_gre.is_null() {
        return EINVAL;
    }

    let ct_pptp_info = unsafe { nfct_help_data(ct) };
    if ct_pptp_info.is_null() {
        return EINVAL;
    }

    let kmp = unsafe { &mut (*ct_pptp_info).keymap[dir_idx] };
    if !(*kmp).is_null() {
        let km = *kmp;
        if gre_key_cmpfn(km as *const nf_ct_gre_keymap, t as *const nf_conntrack_tuple) != 0 {
            return 0;
        }
        return EEXIST;
    }

    let km = unsafe { kmalloc(core::mem::size_of::<nf_ct_gre_keymap>()) as *mut nf_ct_gre_keymap };
    if km.is_null() {
        return ENOMEM;
    }

    unsafe {
        ptr::copy_nonoverlapping(t as *const nf_conntrack_tuple, &mut (*km).tuple, 1);
        (*km).list.next = ptr::null_mut();
        (*km).list.prev = ptr::null_mut();
        (*km).rcu.next = ptr::null_mut();
        (*km).rcu.func = None;

        spin_lock_bh(KEYMAP_LOCK.get_mut());
        list_add_tail(&mut (*net_gre).keymap_list, &mut (*km).list);
        spin_unlock_bh(KEYMAP_LOCK.get_mut());
    }

    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn nf_ct_gre_keymap_destroy(ct: *mut nf_conn) {
    if ct.is_null() {
        return;
    }

    let ct_pptp_info = nfct_help_data(ct);
    spin_lock_bh(KEYMAP_LOCK.get_mut());

    for i in 0..IP_CT_DIR_MAX {
        let km = unsafe { (*ct_pptp_info).keymap[i] };
        if !km.is_null() {
            unsafe {
                spin_lock_bh(KEYMAP_LOCK.get_mut());
                (*ct_pptp_info).keymap[i] = ptr::null_mut();
                spin_unlock_bh(KEYMAP_LOCK.get_mut());
                kfree(km as *mut c_void);
            }
        }
    }

    spin_unlock_bh(KEYMAP_LOCK.get_mut());
}

#[no_mangle]
pub unsafe extern "C" fn gre_pkt_to_tuple(
    skb: *const sk_buff,
    dataoff: c_int,
    net: *mut c_void,
    tuple: *mut nf_conntrack_tuple,
) -> c_int {
    if skb.is_null() || tuple.is_null() {
        return EINVAL;
    }

    let mut _grehdr: [u8; mem::size_of::<gre_base_hdr>()] = [0; mem::size_of::<gre_base_hdr>()];
    let grehdr = skb_header_pointer(
        skb,
        dataoff,
        mem::size_of::<gre_base_hdr>() as size_t,
        _grehdr.as_mut_ptr() as *mut c_void,
    ) as *mut gre_base_hdr;

    if grehdr.is_null() || (*grehdr).flags & GRE_VERSION != GRE_VERSION_1 {
        (*tuple).src.u3.all = [0; 4];
        (*tuple).dst.u3.all = [0; 4];
        return 1;
    }

    let mut _pgrehdr: [u8; 8] = [0; 8];
    let pgrehdr = skb_header_pointer(skb, dataoff, 8, _pgrehdr.as_mut_ptr() as *mut c_void)
        as *mut pptp_gre_header;

    if pgrehdr.is_null() {
        return 1;
    }

    if (*grehdr).protocol != GRE_PROTO_PPP {
        return 0;
    }

    (*tuple).dst.u3.all = [0; 4];
    (*tuple).dst.u3.all[0] = (*pgrehdr).call_id as u32;
    let srckey = gre_keymap_lookup(net, tuple);
    (*tuple).src.u3.all = [0; 4];
    (*tuple).src.u3.all[0] = srckey as u32;

    1
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_gre_packet(
    ct: *mut nf_conn,
    skb: *mut sk_buff,
    _dataoff: c_int,
    ctinfo: c_int,
    _state: *const c_void,
) -> c_int {
    if ct.is_null() {
        return EINVAL;
    }

    if ((*ct).status & IPS_SEEN_REPLY as u64) == 0 {
        let timeouts = nf_ct_timeout_lookup(ct);
        if timeouts.is_null() {
            let net = nf_ct_net(ct);
            let net_gre = gre_pernet(net);
            (*ct).timeout = (*net_gre).timeouts[GRE_CT_UNREPLIED] as u64;
        } else {
            (*ct).timeout = *timeouts.offset(GRE_CT_UNREPLIED as isize) as u64;
        }
    }

    if ((*ct).status & IPS_SEEN_REPLY as u64) != 0 {
        nf_ct_refresh_acct(ct, ctinfo, skb, (*ct).timeout as c_uint);
        if ((*ct).status & IPS_ASSURED_BIT as u64) == 0 {
            nf_conntrack_event_cache(IPCT_ASSURED, ct);
        }
    } else {
        nf_ct_refresh_acct(ct, ctinfo, skb, (*ct).timeout as c_uint);
    }

    0 // NF_ACCEPT
}

// Helper functions
static GRE_NET: SyncWrapper<nf_gre_net> = SyncWrapper::new(nf_gre_net {
    keymap_list: list_head {
        next: ptr::null_mut(),
        prev: ptr::null_mut(),
    },
    timeouts: [0; GRE_CT_MAX],
});

unsafe fn gre_pernet(_net: *mut c_void) -> *mut nf_gre_net {
    GRE_NET.get_mut() as *mut nf_gre_net
}

unsafe fn gre_keymap_lookup(net: *mut c_void, t: *mut nf_conntrack_tuple) -> u16 {
    let net_gre = gre_pernet(net);
    let mut key = 0u16;

    let mut km = (*net_gre).keymap_list.next as *mut nf_ct_gre_keymap;
    while !km.is_null() && (km as *mut list_head) != ptr::addr_of_mut!((*net_gre).keymap_list) {
        if gre_key_cmpfn(km as *const _, t) != 0 {
            key = (*km).tuple.src.u3.all[0] as u16;
            break;
        }
        km = (*km).list.next as *mut nf_ct_gre_keymap;
    }

    key
}

unsafe fn gre_key_cmpfn(km: *const nf_ct_gre_keymap, t: *const nf_conntrack_tuple) -> c_int {
    if (*km).tuple.src.u3.all != (*t).src.u3.all {
        return 0;
    }

    if (*km).tuple.dst.u3.all != (*t).dst.u3.all {
        return 0;
    }

    if (*km).tuple.dst.protonum != (*t).dst.protonum {
        return 0;
    }

    1
}

// Extern types for external dependencies
#[repr(C)]
struct gre_base_hdr { flags: u16, protocol: u16 }

#[repr(C)]
struct pptp_gre_header { call_id: u16 }

// Constants for protocol
const GRE_VERSION_1: u16 = 0x2000;
const GRE_PROTO_PPP: u16 = 0x880B;
const IPS_SEEN_REPLY: u32 = 1 << 0;
const IPS_ASSURED_BIT: u32 = 1 << 1;
const IPCT_ASSURED: c_int = 6;
const GRE_VERSION: u16 = 0x7FFF;
