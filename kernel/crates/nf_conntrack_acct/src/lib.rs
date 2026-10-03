#![allow(clippy::all, clippy::pedantic)]

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(clippy::manual_c_str_literals)]

use core::{ptr, ffi::{c_int, c_char, c_void}};

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOSYS: c_int = -38;
pub const NF_CT_EXT_ACCT: u32 = 1;

#[repr(C)]
struct nf_conn_acct { _priv: [u8; 0] }

#[repr(C)]
struct nf_ct_ext_type {
    len: usize,
    align: usize,
    id: u32,
}

#[repr(C)]
pub struct net { pub ct: net_ct }

#[repr(C)]
pub struct net_ct { pub sysctl_acct: u8 }

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

static NF_CT_ACCT: SyncWrapper<u8> = SyncWrapper::new(0);

// FFI-compatible static variables (pointers to avoid zeroed function type issue)
pub static __UDP_DISCONNECT: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());
pub static ICMPV6_ERR_CONVERT: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());
pub static INET6_SOCKRAW_OPS: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());
pub static IP6_DATAGRAM_CONNECT_V6_ONLY: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());
pub static IP6_DATAGRAM_RECV_COMMON_CTL: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());

// Extern declarations
extern "C" {
    fn nf_ct_extend_register(ext: *const nf_ct_ext_type) -> c_int;
    fn nf_ct_extend_unregister(ext: *const nf_ct_ext_type);
    fn pr_err(msg: *const c_char);
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_acct_pernet_init(net: *mut net) {
    if !net.is_null() {
        (*net).ct.sysctl_acct = *NF_CT_ACCT.get_mut();
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_acct_init() -> c_int {
    let acct_extend = nf_ct_ext_type {
        len: core::mem::size_of::<nf_conn_acct>(),
        align: core::mem::align_of::<nf_conn_acct>(),
        id: NF_CT_EXT_ACCT,
    };

    let ret = nf_ct_extend_register(&acct_extend as *const nf_ct_ext_type);

    if ret < 0 {
        pr_err(b"Unable to register extension\n\0".as_ptr() as *const c_char);
    }

    ret
}

#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_acct_fini() {
    let acct_extend = nf_ct_ext_type {
        len: core::mem::size_of::<nf_conn_acct>(),
        align: core::mem::align_of::<nf_conn_acct>(),
        id: NF_CT_EXT_ACCT,
    };

    nf_ct_extend_unregister(&acct_extend as *const nf_ct_ext_type);
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {
        core::hint::spin_loop();
    }
}
