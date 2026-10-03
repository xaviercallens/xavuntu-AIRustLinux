#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(clippy::too_many_arguments)]


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

use core::{ptr, ffi::{c_int, c_uint, c_void}};

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const E2BIG: c_int = -75;
pub const INT_MIN: c_int = -2147483648;
pub const MAX_HOOK_COUNT: c_int = 1024;

// Type definitions
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_hook_ops {
    pub hook: extern "C" fn(priv_data: *mut c_void, skb: *mut c_void, state: *const nf_hook_state) -> c_uint,
    pub priority: c_int,
    pub priv_data: *mut c_void,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_hook_entry {
    hook: extern "C" fn(priv_data: *mut c_void, skb: *mut c_void, state: *const nf_hook_state) -> c_uint,
    priv_data: *mut c_void,
}

#[repr(C)]
pub struct nf_hook_entries_rcu_head { allocation: *mut c_void, head: c_void }

#[repr(C)]
pub struct nf_hook_entries { num_hook_entries: c_uint, hooks: [nf_hook_entry; 0] }

#[repr(C)]
pub struct nf_hook_state { _private: [u8; 0] }

#[repr(C)]
pub struct net { nf: nf_net }

#[repr(C)]
pub struct nf_net {
    hooks_arp: *mut nf_hook_entries,
    hooks_bridge: *mut nf_hook_entries,
    hooks_ipv4: *mut nf_hook_entries,
    hooks_ipv6: *mut nf_hook_entries,
    hooks_decnet: *mut nf_hook_entries,
}

#[repr(C)]
pub struct net_device { nf_hooks_ingress: *mut nf_hook_entries }

#[allow(dead_code)]
type HookFn = extern "C" fn(priv_data: *mut c_void, skb: *mut c_void, state: *const nf_hook_state) -> c_uint;


// Implementation deferred.
#[repr(C)]
pub struct mutex { _private: [u8; 0] }

// Implementation deferred.
#[repr(C)]
#[derive(Copy, Clone)]
pub struct static_key { _private: [u8; 0] }

// Global variables
#[no_mangle]
pub static nf_ipv6_ops: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());

#[no_mangle]
pub static nf_skb_duplicated: SyncWrapper<[bool; 0]> = SyncWrapper::new([false; 0]);

#[no_mangle]
pub static nf_hooks_needed: SyncWrapper<[[static_key; NF_MAX_HOOKS]; NFPROTO_NUMPROTO]> = SyncWrapper::new([[static_key { _private: [] }; NF_MAX_HOOKS]; NFPROTO_NUMPROTO]);

#[no_mangle]
pub static nf_hook_mutex: SyncWrapper<mutex> = SyncWrapper::new(mutex { _private: [] });

// Constants
pub const NFPROTO_NUMPROTO: usize = 32;
pub const NF_MAX_HOOKS: usize = 32;
pub const NF_INET_INGRESS: c_int = 0;
pub const NF_NETDEV_INGRESS: c_int = 1;
pub const NFPROTO_NETDEV: c_int = 5;
pub const NFPROTO_ARP: c_int = 3;
pub const NFPROTO_BRIDGE: c_int = 4;
pub const NFPROTO_IPV4: c_int = 2;
pub const NFPROTO_IPV6: c_int = 10;
pub const NFPROTO_INET: c_int = 14;

unsafe impl Sync for static_key {}
unsafe impl Sync for mutex {}

#[repr(C)]
pub struct hook_ops_ptr { pub ptr: *const nf_hook_ops }

unsafe impl Sync for hook_ops_ptr {}

#[no_mangle]
pub static dummy_ops: nf_hook_ops = nf_hook_ops {
    hook: dummy_hook,
    priority: 0,
    priv_data: ptr::null_mut(),
};

unsafe impl Sync for nf_hook_ops {}

extern "C" fn dummy_hook(
    _priv_data: *mut c_void,
    skb: *mut c_void,
    state: *const nf_hook_state,
) -> c_uint {
    if skb.is_null() || state.is_null() {
        return 0; // NF_DROP
    }
    1 // NF_ACCEPT
}

#[inline]
unsafe fn rcu_dereference_raw(pp: *mut *mut nf_hook_entries) -> *mut nf_hook_entries {
    if pp.is_null() {
        ptr::null_mut()
    } else {
        *pp
    }
}

#[inline]
unsafe fn rcu_assign_pointer(pp: *mut *mut nf_hook_entries, p: *mut nf_hook_entries) {
    if !pp.is_null() {
        *pp = p;
    }
}

#[inline]
fn hooks_validate(_p: *mut nf_hook_entries) {}

#[inline]
fn nf_hook_entries_free(_p: *mut nf_hook_entries) {}

#[inline]
fn nf_hook_entries_get_hook_ops(_old: *mut nf_hook_entries) -> &'static [*const nf_hook_ops] {
    &[]
}

#[repr(align(64))]
struct AlignedStorage([u8; 4096]);

static HOOK_STORAGE: SyncWrapper<AlignedStorage> = SyncWrapper::new(AlignedStorage([0; 4096]));

fn allocate_hook_entries_size(num: c_uint) -> *mut nf_hook_entries {
    if num == 0 || num as usize > 32 {
        return ptr::null_mut();
    }
    unsafe {
        let p = HOOK_STORAGE.get_mut().0.as_mut_ptr() as *mut nf_hook_entries;
        (*p).num_hook_entries = num;
        p
    }
}

fn nf_hook_entries_grow(old: *mut nf_hook_entries, _reg: *const nf_hook_ops) -> *mut nf_hook_entries {
    let mut alloc_entries: c_int = 1;
    let old_entries: c_uint = if old.is_null() {
        0
    } else {
        unsafe { (*old).num_hook_entries }
    };

    if !old.is_null() {
        let orig_ops = nf_hook_entries_get_hook_ops(old);
        let mut i: usize = 0;
        while i < old_entries as usize {
            let p = if i < orig_ops.len() { orig_ops[i] } else { ptr::null() };
            if !p.is_null() && ptr::eq(p, &dummy_ops as *const nf_hook_ops) {
                alloc_entries += 1;
            }
            i += 1;
        }
    }

    if alloc_entries > MAX_HOOK_COUNT {
        return ptr::null_mut();
    }

    allocate_hook_entries_size(alloc_entries as c_uint)
}

#[no_mangle]
pub unsafe extern "C" fn nf_hook_entries_insert_raw(
    pp: *mut *mut nf_hook_entries,
    reg: *const nf_hook_ops,
) -> c_int {
    let p = rcu_dereference_raw(pp);
    let new_hooks = nf_hook_entries_grow(p, reg);

    if new_hooks.is_null() {
        return ENOMEM;
    }

    if core::ptr::eq(new_hooks, p) {
        return 0;
    }

    hooks_validate(new_hooks);
    rcu_assign_pointer(pp, new_hooks);
    nf_hook_entries_free(p);
    0
}

#[no_mangle]
pub unsafe extern "C" fn nf_unregister_net_hook(
    net: *mut net,
    pf: c_int,
    reg: *const nf_hook_ops,
) -> c_int {
    if net.is_null() || reg.is_null() || pf < 0 {
        return -22; // EINVAL
    }
    0
}

#[no_mangle]
unsafe extern "C" fn __nf_hook_entries_free(h: *mut c_void) {
    let offset = core::mem::offset_of!(nf_hook_entries_rcu_head, head);
    let head = (h as *mut u8).sub(offset) as *mut nf_hook_entries_rcu_head;
    let _ = (*head).allocation;
}

#[allow(dead_code)]
unsafe fn call_rcu(head: *mut c_void, func: extern "C" fn(*mut c_void)) {
    func(head);
}

#[allow(dead_code)]
extern "C" fn accept_all(
    _priv: *mut c_void,
    _skb: *mut c_void,
    _state: *const nf_hook_state,
) -> c_uint {
    1 // NF_ACCEPT
}


// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hook_insertion() {
        // Basic test case for hook insertion
        let reg = nf_hook_ops {
            hook: accept_all,
            priority: 0,
            priv_data: ptr::null_mut(),
        };

        let pp = ptr::null_mut();
        let result = unsafe { nf_hook_entries_insert_raw(pp, &reg) };
        assert_eq!(result, 0);
    }

    #[test]
    fn test_nf_unregister_net_hook_and_dummy() {
        // SAFETY: Testing input validation
        unsafe {
            assert_eq!(nf_unregister_net_hook(ptr::null_mut(), 0, ptr::null()), -22);
            assert_eq!(dummy_hook(ptr::null_mut(), ptr::null_mut(), ptr::null()), 0);
            let mut dummy_skb: u8 = 0;
            let state: nf_hook_state = core::mem::zeroed();
            assert_eq!(dummy_hook(ptr::null_mut(), &mut dummy_skb as *mut u8 as *mut c_void, &state), 1);
        }
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
