#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! Network Filter Logging Module
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs)]

use core::ffi::{c_char, c_int, c_uint, c_void};
use core::ptr;
use core::sync::atomic::AtomicI32;

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

pub const NF_LOGGER_NAME_LEN: usize = 64;
pub const NF_LOG_TYPE_MAX: usize = 16;
pub const NFPROTO_NUMPROTO: usize = 32;
pub const NFPROTO_UNSPEC: u8 = 0;
pub const NF_LOG_PREFIXLEN: usize = 128;
pub const EINVAL: c_int = -22;
pub const EOPNOTSUPP: c_int = -95;
pub const ENOENT: c_int = -2;
pub const EEXIST: c_int = -17;

// Type definitions
#[repr(C)]
#[derive(Copy, Clone)]
pub struct net_nf { pub nf_loggers: [*mut nf_logger; NFPROTO_NUMPROTO] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net { pub nf: net_nf }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_logger {
    pub name: [u8; NF_LOGGER_NAME_LEN],
    pub type_: c_int,
    pub me: *mut c_void,
    pub logfn: Option<
        extern "C" fn(
            net: *mut net,
            pf: u8,
            hooknum: c_uint,
            skb: *const c_void,
            in_: *const c_void,
            out: *const c_void,
            loginfo: *const c_void,
            prefix: *const c_char,
        ),
    >,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_log_buf { pub count: c_uint, pub buf: [u8; 1024] }

// Function pointer types
pub type nf_log_fn = extern "C" fn(
    net: *mut c_void,
    pf: u8,
    hooknum: u32,
    skb: *const sk_buff,
    in_: *const c_void,
    out: *const c_void,
    loginfo: *const c_void,
    prefix: *const u8,
);

// Implementation deferred.
#[repr(C)]
pub struct Mutex { lock: AtomicI32 }

impl Mutex {
    const fn new() -> Self {
        Mutex {
            lock: AtomicI32::new(0),
        }
    }

    fn lock(&self) {
        while self.lock.compare_exchange(
            0,
            1,
            core::sync::atomic::Ordering::Acquire,
            core::sync::atomic::Ordering::Relaxed,
        ).is_err()
        {
            // Spin until lock is available
        }
    }

    fn unlock(&self) {
        self.lock.store(0, core::sync::atomic::Ordering::Release);
    }
}

// Internal state
static LOGGERS: SyncWrapper<[[*mut nf_logger; NF_LOG_TYPE_MAX]; NFPROTO_NUMPROTO]> =
    SyncWrapper::new([[ptr::null_mut(); NF_LOG_TYPE_MAX]; NFPROTO_NUMPROTO]);
static NF_LOG_MUTEX: Mutex = Mutex::new();
static EMERGENCY_PTR: SyncWrapper<*mut nf_log_buf> = SyncWrapper::new(ptr::null_mut());
static SYSCTL_NF_LOG_ALL_NETNS: SyncWrapper<c_int> = SyncWrapper::new(0);

#[inline]
unsafe fn rcu_dereference<T>(p: *mut T) -> *mut T {
    p
}

#[inline]
unsafe fn rcu_assign_pointer<T>(dst: *mut *mut T, src: *mut T) {
    *dst = src;
}

fn __find_logger(pf: u8, str_logger: *const c_char) -> *mut nf_logger {
    if pf as usize >= NFPROTO_NUMPROTO || str_logger.is_null() {
        return ptr::null_mut();
    }

    let mut i = 0usize;
    while i < NF_LOG_TYPE_MAX {
        let logger = unsafe { rcu_dereference((*LOGGERS.get_mut())[pf as usize][i]) };
        if !logger.is_null() {
            let mut matched = true;
            let mut j = 0usize;
            while j < NF_LOGGER_NAME_LEN {
                let a = unsafe { (*logger).name[j] };
                let b = unsafe { *str_logger.add(j) as u8 };
                if a != b {
                    matched = false;
                    break;
                }
                if b == 0 {
                    break;
                }
                j += 1;
            }
            if matched {
                return logger;
            }
        }
        i += 1;
    }

    ptr::null_mut()
}

// Exported functions
/// Set network logger for specific protocol family
///
/// # Safety
/// - `net` must be a valid pointer to net structure
/// - `pf` must be valid protocol family
/// - `logger` must be a valid logger pointer
///
/// # Returns
/// 0 on success, -EOPNOTSUPP if protocol family invalid
#[no_mangle]
pub unsafe extern "C" fn nf_log_set(net: *mut c_void, pf: u8, logger: *const nf_logger) -> c_int {
    if pf == NFPROTO_UNSPEC || pf >= NFPROTO_NUMPROTO as u8 {
        return -EOPNOTSUPP;
    }

    NF_LOG_MUTEX.lock();

    let net_nf_ptr = net as *mut net_nf;
    if net_nf_ptr.is_null() {
        NF_LOG_MUTEX.unlock();
        return -EINVAL;
    }

    let current_logger = rcu_dereference((*net_nf_ptr).nf_loggers[pf as usize]);
    if current_logger.is_null() {
        rcu_assign_pointer(
            &mut (*net_nf_ptr).nf_loggers[pf as usize] as *mut *mut nf_logger,
            logger as *mut nf_logger,
        );
    }

    NF_LOG_MUTEX.unlock();

    0
}

/// Unset network logger
///
/// # Safety
/// - `net` must be a valid pointer to net structure
/// - `logger` must be a valid logger pointer
#[no_mangle]
pub unsafe extern "C" fn nf_log_unset(net: *mut c_void, logger: *const nf_logger) {
    NF_LOG_MUTEX.lock();

    let net_nf_ptr = net as *mut net_nf;
    if net_nf_ptr.is_null() {
        NF_LOG_MUTEX.unlock();
        return;
    }

    for i in 0..NFPROTO_NUMPROTO {
        let current_logger = rcu_dereference((*net_nf_ptr).nf_loggers[i]);
        if current_logger == logger as *mut nf_logger {
            rcu_assign_pointer(
                &mut (*net_nf_ptr).nf_loggers[i] as *mut *mut nf_logger,
                ptr::null_mut(),
            );
        }
    }

    NF_LOG_MUTEX.unlock();
}

#[no_mangle]
pub unsafe extern "C" fn nf_log_register(pf: u8, logger: *mut nf_logger) -> c_int {
    if pf >= NFPROTO_NUMPROTO as u8 {
        return -EINVAL;
    }

    NF_LOG_MUTEX.lock();

    let mut ret = 0;

    if pf == NFPROTO_UNSPEC {
        for i in 0..NFPROTO_NUMPROTO {
            let existing = rcu_dereference((*LOGGERS.get_mut())[i][(*logger).type_ as usize]);
            if !existing.is_null() {
                ret = -EEXIST;
                break;
            }
        }

        if ret == 0 {
            for i in 0..NFPROTO_NUMPROTO {
                rcu_assign_pointer(
                    &mut (*LOGGERS.get_mut())[i][(*logger).type_ as usize] as *mut *mut nf_logger,
                    logger,
                );
            }
        }
    } else {
        let existing = rcu_dereference((*LOGGERS.get_mut())[pf as usize][(*logger).type_ as usize]);
        if !existing.is_null() {
            ret = -EEXIST;
        } else {
            rcu_assign_pointer(
                &mut (*LOGGERS.get_mut())[pf as usize][(*logger).type_ as usize] as *mut *mut nf_logger,
                logger,
            );
        }
    }

    NF_LOG_MUTEX.unlock();
    ret
}

/// Unregister a network logger
///
/// # Safety
/// - `logger` must be a valid logger pointer
#[no_mangle]
pub unsafe extern "C" fn nf_log_unregister(logger: *mut nf_logger) {
    NF_LOG_MUTEX.lock();

    for i in 0..NFPROTO_NUMPROTO {
        let current_logger = rcu_dereference((*LOGGERS.get_mut())[i][(*logger).type_ as usize]);
        if current_logger == logger {
            rcu_assign_pointer(
                &mut (*LOGGERS.get_mut())[i][(*logger).type_ as usize] as *mut *mut nf_logger,
                ptr::null_mut(),
            );
        }
    }

    NF_LOG_MUTEX.unlock();
    synchronize_rcu();
}

// Helper function for synchronization
#[inline]
unsafe fn synchronize_rcu() {
    // Implementation deferred.
}

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_logger_registration() {
        // Basic test for logger registration
        unsafe {
            let mut logger = nf_logger {
                name: [0; NF_LOGGER_NAME_LEN],
                type_: 0,
                me: ptr::null_mut(),
                logfn: None,
            };

            // Register logger for PF_INET
            let result = nf_log_register(1, &mut logger);
            assert_eq!(result, 0);

            // Unregister logger
            nf_log_unregister(&mut logger);
        }
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
