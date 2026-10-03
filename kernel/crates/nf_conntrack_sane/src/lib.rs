#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

use core::{{mem, ptr}, ffi::{c_char, c_int, c_uint, c_void}};
use kernel_types::*;

pub type size_t = usize;
pub type c_size_t = usize;
pub type socklen_t = u32;

// Constants from C
pub const IPPROTO_TCP: c_int = 6;
pub const NF_ACCEPT: c_int = 1;
pub const NF_DROP: c_int = 2;
pub const IP_CT_DIR_ORIGINAL: c_int = 0;
pub const IP_CT_DIR_REPLY: c_int = 1;
pub const IP_CT_ESTABLISHED: c_int = 1 << 1;
pub const IP_CT_ESTABLISHED_REPLY: c_int = IP_CT_ESTABLISHED | (1 << 2);
pub const fn ctinfo2_dir(ctinfo: c_int) -> c_int {
    (ctinfo >> 1) & 1
}
pub const SANE_PORT: u16 = 6566;

// SANE protocol constants
pub const SANE_NET_START: u32 = 7; pub const SANE_STATUS_SUCCESS: u32 = 0;

// Error codes
pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12;

// Missing kernel FFI opaque types
#[repr(C)]
pub struct nf_conntrack_expect_policy { _priv: [u8; 0] }

#[repr(C)]
pub struct nf_conntrack_expect { _priv: [u8; 0] }

#[repr(C)]
pub struct nf_conntrack_tuple { _priv: [u8; 0] }

// C struct translations
#[repr(C)]
#[derive(Copy, Clone)]
pub struct tcphdr {
    pub source: u16,
    pub dest: u16,
    pub doff: u8,
    pub _pad: [u8; 3],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sane_request { pub rpc_code: u32, pub handle: u32 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sane_reply_net_start {
    pub status: u32,
    pub zero: u16,
    pub port: u16,
}

// Helper data structure
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_ct_sane_master { pub state: c_int }

// Opaque helper type
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_helper { _priv: [u8; 0] }

// Extern declarations for kernel functions
unsafe extern "C" {
    fn skb_header_pointer(
        skb: *mut sk_buff,
        offset: c_int,
        size: c_int,
        buffer: *mut c_void,
    ) -> *mut c_void;
    fn nf_ct_expect_alloc(ct: *mut nf_conn) -> *mut nf_conntrack_expect;
    fn nf_ct_expect_init(
        exp: *mut nf_conntrack_expect,
        class: c_int,
        l3num: c_int,
        src: *mut c_void,
        dst: *mut c_void,
        protonum: c_int,
        mask: *mut c_void,
        port: *mut u16,
    );
    fn nf_ct_expect_related(exp: *mut nf_conntrack_expect, strict: c_int) -> c_int;
    fn nf_ct_expect_put(exp: *mut nf_conntrack_expect);
    fn nf_conntrack_helpers_register(helpers: *const nf_conntrack_helper, count: c_int) -> c_int;
    fn nf_conntrack_helpers_unregister(helpers: *const nf_conntrack_helper, count: c_int);
    fn nf_ct_l3num(ct: *mut nf_conn) -> c_int;
    fn nf_ct_help_data(ct: *mut nf_conn) -> *mut nf_ct_sane_master;
    fn nf_ct_dump_tuple(tuple: *mut nf_conntrack_tuple);
    fn nf_ct_helper_log(skb: *mut sk_buff, ct: *mut nf_conn, msg: *const c_char);
    fn spin_lock_bh(lock: *mut c_void);
    fn spin_unlock_bh(lock: *mut c_void);
}

// Implementation deferred.
unsafe fn nf_ct_helper_init(
    _helper: *mut nf_conntrack_helper,
    _af: c_int,
    _proto: c_int,
    _name: *const c_char,
    _def_port: u16,
    _port: u16,
    _timeout: c_int,
    _policy: *const nf_conntrack_expect_policy,
    _flags: c_int,
    _help_fn: Option<unsafe extern "C" fn(*mut sk_buff, c_uint, *mut nf_conn, c_int) -> c_int>,
    _from_nlattr: *mut c_void,
    _nat_module: *mut c_void,
) {
    // Implementation deferred.
}

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
        // For FFI globals, the kernel handles external synchronization.
        unsafe { &mut *self.0.get() }
    }
}

// Module parameters
static PORTS: SyncWrapper<[u16; 8]> = SyncWrapper::new([0; 8]);
static PORTS_C: SyncWrapper<c_int> = SyncWrapper::new(0);

// Spinlock and buffer
static NF_SANE_LOCK: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());
static SANE_STORAGE: SyncWrapper<[u8; 65536]> = SyncWrapper::new([0; 65536]);
static SANE_BUFFER: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());

// Helper array
static SANE: SyncWrapper<[nf_conntrack_helper; 16]> = SyncWrapper::new(unsafe { [mem::zeroed(); 16] });

// Helper function
#[unsafe(no_mangle)]
pub unsafe extern "C" fn help(
    skb: *mut sk_buff,
    protoff: c_uint,
    ct: *mut nf_conn,
    ctinfo: c_int,
) -> c_int {
    let dir: c_int = ctinfo2_dir(ctinfo);
    let ct_sane_info = nf_ct_help_data(ct);
    let mut ret = NF_ACCEPT;

    if ctinfo != IP_CT_ESTABLISHED && ctinfo != IP_CT_ESTABLISHED_REPLY {
        return NF_ACCEPT;
    }

    let mut th: tcphdr = unsafe { mem::zeroed() };
    let th_ptr: *mut c_void = &mut th as *mut _ as *mut c_void;
    let th_result = unsafe {
        skb_header_pointer(
            skb,
            protoff as c_int,
            mem::size_of::<tcphdr>() as c_int,
            th_ptr,
        )
    };
    if th_result.is_null() {
        return NF_ACCEPT;
    }

    let dataoff: c_int = protoff as c_int + (th.doff as c_int) * 4;
    let skb_len: c_int = unsafe { (*skb).len as c_int };
    if dataoff >= skb_len {
        return NF_ACCEPT;
    }

    let datalen: c_int = skb_len - dataoff;

    // Acquire spinlock
    spin_lock_bh(*NF_SANE_LOCK.get_mut());

    // Get data pointer
    let sb_ptr: *mut c_void = skb_header_pointer(skb, dataoff, datalen, *SANE_BUFFER.get_mut());
    if sb_ptr.is_null() {
        spin_unlock_bh(*NF_SANE_LOCK.get_mut());
        return NF_ACCEPT;
    }

    if dir == IP_CT_DIR_ORIGINAL {
        if datalen != mem::size_of::<sane_request>() as c_int {
            spin_unlock_bh(*NF_SANE_LOCK.get_mut());
            return NF_ACCEPT;
        }

        let req = sb_ptr as *mut sane_request;
        if (*req).rpc_code != SANE_NET_START {
            (*ct_sane_info).state = 0; // SANE_STATE_NORMAL
            spin_unlock_bh(*NF_SANE_LOCK.get_mut());
            return NF_ACCEPT;
        }

        (*ct_sane_info).state = 1; // SANE_STATE_START_REQUESTED
    }

    // Is it a reply to an uninteresting command?
    if (*ct_sane_info).state != 1 {
        spin_unlock_bh(*NF_SANE_LOCK.get_mut());
        return NF_ACCEPT;
    }

    (*ct_sane_info).state = 0; // SANE_STATE_NORMAL

    if datalen < mem::size_of::<sane_reply_net_start>() as c_int {
        spin_unlock_bh(*NF_SANE_LOCK.get_mut());
        return NF_ACCEPT;
    }

    let reply = sb_ptr as *mut sane_reply_net_start;
    if (*reply).status != SANE_STATUS_SUCCESS {
        spin_unlock_bh(*NF_SANE_LOCK.get_mut());
        return NF_ACCEPT;
    }

    if (*reply).zero != 0 {
        spin_unlock_bh(*NF_SANE_LOCK.get_mut());
        return NF_ACCEPT;
    }

    let exp = nf_ct_expect_alloc(ct);
    if exp.is_null() {
        nf_ct_helper_log(skb, ct, c"cannot alloc expectation".as_ptr());
        spin_unlock_bh(*NF_SANE_LOCK.get_mut());
        return NF_DROP;
    }

    let _tuple = &(*ct).tuplehash[0].tuple;
    let mut port = (*reply).port;
    nf_ct_expect_init(
        exp,
        0, // NF_CT_EXPECT_CLASS_DEFAULT
        nf_ct_l3num(ct),
        ptr::null_mut(),
        ptr::null_mut(),
        IPPROTO_TCP,
        ptr::null_mut(),
        &mut port as *mut u16,
    );

    // nf_ct_dump_tuple(&(*exp).tuple);

    // Can't expect this?  Best to drop packet now.
    if nf_ct_expect_related(exp, 0) != 0 {
        nf_ct_helper_log(skb, ct, c"cannot add expectation".as_ptr());
        ret = NF_DROP;
    }

    nf_ct_expect_put(exp);

    spin_unlock_bh(*NF_SANE_LOCK.get_mut());
    ret
}

// Spinlock operations - already defined in extern block above

// Module init/exit
#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_sane_init() -> c_int {
    let _i: c_int = 0;

    *SANE_BUFFER.get_mut() = SANE_STORAGE.get_mut().as_mut_ptr().cast();

    if *PORTS_C.get_mut() == 0 {
        (*PORTS.get_mut())[0] = SANE_PORT;
        *PORTS_C.get_mut() = 1;
    }

    for i in 0..*PORTS_C.get_mut() {
        nf_ct_helper_init(
            &mut (*SANE.get_mut())[(2 * i) as usize],
            2, // AF_INET
            IPPROTO_TCP,
            "sane" as *const str as *const c_char,
            SANE_PORT,
            (*PORTS.get_mut())[i as usize],
            5 * 60,
            &SANE_EXP_POLICY,
            0,
            Some(help as _),
            ptr::null_mut(),
            ptr::null_mut(),
        );
        nf_ct_helper_init(
            &mut (*SANE.get_mut())[(2 * i + 1) as usize],
            10, // AF_INET6
            IPPROTO_TCP,
            "sane" as *const str as *const c_char,
            SANE_PORT,
            (*PORTS.get_mut())[i as usize],
            5 * 60,
            &SANE_EXP_POLICY,
            0,
            Some(help as _),
            ptr::null_mut(),
            ptr::null_mut(),
        );
    }

    let ret = nf_conntrack_helpers_register(SANE.get_mut().as_mut_ptr() as *const nf_conntrack_helper, (*PORTS_C.get_mut()) * 2);
    if ret < 0 {
        *SANE_BUFFER.get_mut() = ptr::null_mut();
        return ret;
    }

    0
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_sane_fini() {
    nf_conntrack_helpers_unregister(SANE.get_mut().as_mut_ptr() as *const nf_conntrack_helper, (*PORTS_C.get_mut()) * 2);
    *SANE_BUFFER.get_mut() = ptr::null_mut();
}

// Expectation policy
static SANE_EXP_POLICY: nf_conntrack_expect_policy = nf_conntrack_expect_policy {
    _priv: [],
};

// Module macros
#[no_mangle]
pub static NF_CONNTRACK_SANE_INIT_FN: unsafe extern "C" fn() -> c_int = nf_conntrack_sane_init;
#[no_mangle]
pub static NF_CONNTRACK_SANE_FINI_FN: unsafe extern "C" fn() = nf_conntrack_sane_fini;

// Module license
#[no_mangle]
pub static NF_CONNTRACK_SANE_LICENSE: [u8; 4] = *b"GPL\0";
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
