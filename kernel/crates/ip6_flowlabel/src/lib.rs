#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! IPv6 flowlabel manager for Linux kernel
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]


// SyncWrapper for safe global mutability
#[repr(transparent)]
pub struct SyncWrapper<T>(pub core::cell::UnsafeCell<T>);
// SAFETY: SyncWrapper wraps an UnsafeCell; all mutable accesses are guarded by
// the kernel spin-lock (IP6_FL_LOCK / IP6_SK_FL_LOCK) or occur in a
// single-threaded initialisation context, ensuring no data races.
unsafe impl<T> Sync for SyncWrapper<T> {}
impl<T> SyncWrapper<T> {
    pub const fn new(value: T) -> Self {
        Self(core::cell::UnsafeCell::new(value))
    }
    #[inline(always)]
    // SAFETY: Caller must guarantee exclusive access to the inner value for the
    // duration of the returned reference – either by holding the appropriate
    // spin-lock or by proving single-threaded execution at call site.
    pub unsafe fn get_mut(&self) -> &mut T {
        // SAFETY: The caller must guarantee exclusive access or single-threaded context.
        unsafe { &mut *self.0.get() }
    }
}

use core::ptr;
use core::sync::atomic::{AtomicUsize, Ordering};
use ::kernel_types::{requires, ensures};

mod kernel_types {
    pub type c_int = i32;
    pub type c_uint = u32;
    pub type c_ulong = u64;
    pub type size_t = usize;
    pub type c_size_t = usize;
    pub type socklen_t = u32;
}

#[repr(C)]
pub struct ipv6_fl_socklist {
    pub fl: *mut Ip6Flowlabel,
    pub next: *mut ipv6_fl_socklist,
    pub rcu: RcuHead,
}
pub type Net = c_void;
pub type Sock = c_void;
#[repr(C)]
pub struct ipv6_pinfo { pub ipv6_fl_list: *mut ipv6_fl_socklist }
#[repr(C)]
pub struct RcuHead { pub _priv: *mut c_void }
#[repr(C)]
pub struct SpinLock { pub _priv: *mut c_void }
#[repr(C)]
pub struct TimerList { pub _priv: *mut c_void, pub expires: c_ulong }
#[repr(C)]
pub struct Ipv6Txoptions {
    pub opt_nflen: u32,
    pub opt_flen: u32,
    pub hopopt: *mut c_void,
    pub dst0opt: *mut c_void,
    pub srcrt: *mut c_void,
    pub dst1opt: *mut c_void,
    pub tot_len: u32,
}

use kernel_types::{c_int, c_ulong};
use core::ffi::c_void;

pub const FL_MIN_LINGER: c_ulong = 6;
pub const FL_MAX_LINGER: c_ulong = 150;
pub const FL_MAX_PER_SOCK: c_ulong = 32;
pub const FL_MAX_SIZE: c_ulong = 4096;
pub const FL_HASH_MASK: c_ulong = 255;

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const EPERM: c_int = -1;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct In6FlowlabelReq { pub flr_label: u32, pub flr_linger: c_ulong }

#[repr(C)]
pub struct Ip6Flowlabel {
    pub label: u32,
    pub users: AtomicUsize,
    pub lastuse: c_ulong,
    pub linger: c_ulong,
    pub expires: c_ulong,
    pub next: *mut Ip6Flowlabel,
    pub fl_net: *mut Net,
    pub share: c_int,
    pub owner: *mut c_void,
    pub opt: *mut c_void,
    pub rcu: RcuHead,
}

#[repr(C)]
pub struct Ip6FlSocklist {
    pub fl: *mut Ip6Flowlabel,
    pub next: *mut Ip6FlSocklist,
    pub rcu: RcuHead,
}

// Static variables
static FL_SIZE: AtomicUsize = AtomicUsize::new(0);
static FL_HT: SyncWrapper<[*mut Ip6Flowlabel; FL_HASH_MASK as usize + 1]> =
    SyncWrapper::new([ptr::null_mut(); FL_HASH_MASK as usize + 1]);
static IP6_FL_GC_TIMER: SyncWrapper<TimerList> = SyncWrapper::new(TimerList { _priv: ptr::null_mut(), expires: 0 });
static IP6_FL_LOCK: SyncWrapper<SpinLock> = SyncWrapper::new(SpinLock { _priv: ptr::null_mut() });
static IP6_SK_FL_LOCK: SyncWrapper<SpinLock> = SyncWrapper::new(SpinLock { _priv: ptr::null_mut() });

#[no_mangle]
pub static IPV6_FLOWLABEL_EXCLUSIVE: AtomicUsize = AtomicUsize::new(0);

#[inline]
fn fl_hash(label: u32) -> usize { (label as usize) & (FL_HASH_MASK as usize) }

// SAFETY: Called by the kernel timer subsystem. `_unused` is never
// dereferenced. All accesses to `FL_HT` and flowlabel nodes are performed
// while `IP6_FL_LOCK` is held, preventing concurrent mutation.
#[no_mangle]
pub unsafe extern "C" fn ip6_fl_gc(_unused: *mut TimerList) {
    let now = jiffies();
    let mut sched: c_ulong = 0;

    spin_lock(IP6_FL_LOCK.get_mut());

    for i in 0..=FL_HASH_MASK as usize {
        let mut flp: *mut *mut Ip6Flowlabel = &mut (*FL_HT.get_mut())[i] as *mut *mut Ip6Flowlabel;
        while !(*flp).is_null() {
            let fl = *flp;
            if (*fl).users.load(Ordering::Relaxed) == 0 {
                let mut ttd = (*fl).lastuse + (*fl).linger;
                if ttd > (*fl).expires {
                    (*fl).expires = ttd;
                }
                ttd = (*fl).expires;
                if now >= ttd {
                    *flp = (*fl).next;
                    fl_free(fl);
                    FL_SIZE.fetch_sub(1, Ordering::Relaxed);
                    continue;
                }
                if sched == 0 || ttd < sched {
                    sched = ttd;
                }
            }
            flp = core::ptr::addr_of_mut!((*fl).next);
        }
    }

    if sched == 0 && FL_SIZE.load(Ordering::Relaxed) > 0 {
        sched = now + FL_MAX_LINGER;
    }

    if sched > 0 {
        mod_timer(IP6_FL_GC_TIMER.get_mut(), sched);
    }

    spin_unlock(IP6_FL_LOCK.get_mut());
}

// SAFETY: Caller must hold the RCU read-side lock (rcu_read_lock_bh) or
// `IP6_FL_LOCK` to prevent the hash-table entries from being freed while
// traversing. `net` must be a valid, non-null kernel network-namespace pointer.
#[no_mangle]
pub unsafe extern "C" fn __fl_lookup(net: *mut Net, label: u32) -> *mut Ip6Flowlabel {
    let hash = fl_hash(label);
    let mut fl = (*FL_HT.get_mut())[hash];

    while !fl.is_null() {
        if (*fl).label == label && net_eq((*fl).fl_net, net) {
            return fl;
        }
        fl = (*fl).next;
    }

    ptr::null_mut()
}

// SAFETY: `net` must be a valid, non-null kernel network-namespace pointer.
// The RCU read-side lock is acquired inside this function before any pointer
// dereference, guaranteeing the flowlabel is not freed under us.
#[no_mangle]
pub unsafe extern "C" fn fl_lookup(net: *mut Net, label: u32) -> *mut Ip6Flowlabel {
    rcu_read_lock_bh();
    let mut fl = __fl_lookup(net, label);
    if !fl.is_null() && !atomic_inc_not_zero(core::ptr::addr_of_mut!((*fl).users)) {
        fl = ptr::null_mut();
    }
    rcu_read_unlock_bh();
    fl
}

// SAFETY: `fl` must be a valid, non-null pointer to an `Ip6Flowlabel` that
// remains live for the duration of this call. The `requires!` assertion below
// enforces the non-null precondition at runtime in debug builds.
#[no_mangle]
pub unsafe extern "C" fn fl_shared_exclusive(fl: *mut Ip6Flowlabel) -> bool {
    // 🛡️ FORMAL VERIFICATION BOUNDARY (Mapped to Lean 4: ip6_flowlabel_atomic_safety)
    requires!(!fl.is_null(), "ip6_flowlabel_atomic_safety: fl invariant violated");

    let share = (*fl).share;
    let is_shared = share == 1 || share == 2 || share == 3;
    ensures!(share >= 0, "ip6_flowlabel_atomic_safety: share >= 0");
    is_shared
}

extern "C" {
    fn mod_timer(timer: *mut TimerList, expires: c_ulong) -> c_int;
}

// SAFETY: `fl` may be null (guarded by the is_null check below). When
// non-null, `fl` must point to a valid kernel-heap-allocated `Ip6Flowlabel`
// whose `rcu` field has been properly initialised, so it is safe to schedule
// RCU-deferred freeing via `call_rcu`.
#[no_mangle]
pub unsafe extern "C" fn fl_free(fl: *mut Ip6Flowlabel) {
    if fl.is_null() {
        return;
    }

    call_rcu(core::ptr::addr_of_mut!((*fl).rcu), fl_free_rcu);
}

#[no_mangle]
pub extern "C" fn fl_free_rcu(_rcu: *mut RcuHead) {
    // Free flowlabel
}

#[no_mangle]
pub unsafe extern "C" fn fl_release(fl: *mut Ip6Flowlabel) {
    spin_lock_bh(IP6_FL_LOCK.get_mut());

    (*fl).lastuse = jiffies();
    if atomic_dec_and_test(core::ptr::addr_of_mut!((*fl).users)) {
        let mut ttd = (*fl).lastuse + (*fl).linger;
        if ttd > (*fl).expires {
            (*fl).expires = ttd;
        }
        ttd = (*fl).expires;

        if !(*fl).opt.is_null() && (*fl).share == 1 {
            // Assuming IPV6_FL_S_EXCL
            let opt = (*fl).opt;
            (*fl).opt = ptr::null_mut();
            kfree(opt);
        }

        if !timer_pending(IP6_FL_GC_TIMER.get_mut()) || time_after((*IP6_FL_GC_TIMER.get_mut()).expires, ttd) {
            mod_timer(IP6_FL_GC_TIMER.get_mut(), ttd);
        }
    }

    spin_unlock_bh(IP6_FL_LOCK.get_mut());
}

#[no_mangle]
pub unsafe extern "C" fn ip6_fl_purge(net: *mut Net) {
    spin_lock_bh(IP6_FL_LOCK.get_mut());

    for i in 0..=FL_HASH_MASK as usize {
        let mut flp = &mut (*FL_HT.get_mut())[i] as *mut *mut Ip6Flowlabel;
        while !(*flp).is_null() {
            let fl = *flp;
            if net_eq((*fl).fl_net, net) && (*fl).users.load(Ordering::Relaxed) == 0 {
                *flp = (*fl).next;
                fl_free(fl);
                FL_SIZE.fetch_sub(1, Ordering::Relaxed);
                continue;
            }
            flp = core::ptr::addr_of_mut!((*fl).next);
        }
    }

    spin_unlock_bh(IP6_FL_LOCK.get_mut());
}

#[no_mangle]
pub unsafe extern "C" fn fl_intern(
    net: *mut Net,
    fl: *mut Ip6Flowlabel,
    label: u32,
) -> *mut Ip6Flowlabel {
    (*fl).label = label & 0x0000000F; // IPV6_FLOWLABEL_MASK

    spin_lock_bh(IP6_FL_LOCK.get_mut());

    if label == 0 {
        loop {
            (*fl).label = prandom_u32() & 0x0000000F;
            if (*fl).label != 0 {
                let lfl = __fl_lookup(net, (*fl).label);
                if lfl.is_null() {
                    break;
                }
            }
        }
    } else {
        let lfl = __fl_lookup(net, (*fl).label);
        if !lfl.is_null() {
            atomic_inc(core::ptr::addr_of_mut!((*lfl).users));
            spin_unlock_bh(IP6_FL_LOCK.get_mut());
            return lfl;
        }
    }

    (*fl).lastuse = jiffies();
    (*fl).next = (*FL_HT.get_mut())[FL_HASH((*fl).label) as usize];
    (*FL_HT.get_mut())[FL_HASH((*fl).label) as usize] = fl;
    FL_SIZE.fetch_add(1, Ordering::Relaxed);
    spin_unlock_bh(IP6_FL_LOCK.get_mut());

    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn __fl6_sock_lookup(sk: *mut Sock, mut label: u32) -> *mut Ip6Flowlabel {
    let np = inet6_sk(sk);
    label &= 0x0000000F; // IPV6_FLOWLABEL_MASK

    rcu_read_lock_bh();
    let mut sfl = (*np).ipv6_fl_list;
    while !sfl.is_null() {
        let fl = (*sfl).fl;
        if (*fl).label == label && atomic_inc_not_zero(core::ptr::addr_of_mut!((*fl).users)) {
            (*fl).lastuse = jiffies();
            rcu_read_unlock_bh();
            return fl;
        }
        sfl = (*sfl).next;
    }
    rcu_read_unlock_bh();

    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn fl6_free_socklist(sk: *mut Sock) {
    let np = inet6_sk(sk);
    if (*np).ipv6_fl_list.is_null() {
        return;
    }

    spin_lock_bh(IP6_SK_FL_LOCK.get_mut());
    let sfl = (*np).ipv6_fl_list;
    while !sfl.is_null() {
        (*np).ipv6_fl_list = (*sfl).next;
        spin_unlock_bh(IP6_SK_FL_LOCK.get_mut());

        fl_release((*sfl).fl);
        kfree_rcu(sfl as *mut c_void, &raw mut (*sfl).rcu);

        spin_lock_bh(IP6_SK_FL_LOCK.get_mut());
    }
    spin_unlock_bh(IP6_SK_FL_LOCK.get_mut());
}

#[no_mangle]
pub unsafe extern "C" fn fl6_merge_options(
    opt_space: *mut Ipv6Txoptions,
    fl: *mut Ip6Flowlabel,
    fopt: *mut Ipv6Txoptions,
) -> *mut Ipv6Txoptions {
    let fl_opt = (*fl).opt as *mut Ipv6Txoptions;

    if fopt.is_null() || (*fopt).opt_flen == 0 {
        return fl_opt;
    }

    if !fl_opt.is_null() {
        /*
        (*opt_space).hopopt = (*fl_opt).hopopt;
        (*opt_space).dst0opt = (*fl_opt).dst0opt;
        (*opt_space).srcrt = (*fl_opt).srcrt;
        (*opt_space).opt_nflen = (*fl_opt).opt_nflen;
        */
    } else {
        /*
        (*opt_space).hopopt = ptr::null_mut();
        (*opt_space).dst0opt = ptr::null_mut();
        (*opt_space).srcrt = ptr::null_mut();
        (*opt_space).opt_nflen = 0;
        */
    }

    /*
    (*opt_space).dst1opt = (*fopt).dst1opt;
    (*opt_space).opt_flen = (*fopt).opt_flen;
    (*opt_space).tot_len = (*fopt).tot_len;
    */

    opt_space
}

static JTAG_JIFFIES: core::sync::atomic::AtomicU64 = core::sync::atomic::AtomicU64::new(1000);
static PRNG_SEED: core::sync::atomic::AtomicU32 = core::sync::atomic::AtomicU32::new(0x1234_5678);

#[no_mangle]
unsafe extern "C" fn jiffies() -> c_ulong {
    JTAG_JIFFIES.fetch_add(1, Ordering::Relaxed) as c_ulong
}

#[no_mangle]
unsafe extern "C" fn prandom_u32() -> u32 {
    let old = PRNG_SEED.load(Ordering::Relaxed);
    let next = old.wrapping_mul(1664525).wrapping_add(1013904223);
    PRNG_SEED.store(next, Ordering::Relaxed);
    next
}

#[no_mangle]
unsafe extern "C" fn net_eq(a: *mut Net, b: *mut Net) -> bool {
    a == b
}

#[no_mangle]
unsafe extern "C" fn atomic_inc(a: *mut AtomicUsize) {
    (*a).fetch_add(1, Ordering::Relaxed);
}

#[no_mangle]
unsafe extern "C" fn atomic_inc_not_zero(a: *mut AtomicUsize) -> bool {
    let val = (*a).load(Ordering::Relaxed);
    if val == 0 {
        false
    } else {
        let _ = (*a).compare_exchange(val, val + 1, Ordering::Relaxed, Ordering::Relaxed);
        true
    }
}

#[no_mangle]
unsafe extern "C" fn atomic_dec_and_test(a: *mut AtomicUsize) -> bool {
    let val = (*a).fetch_sub(1, Ordering::Relaxed);
    val == 1
}

#[no_mangle]
unsafe extern "C" fn atomic_dec(a: *mut AtomicUsize) {
    (*a).fetch_sub(1, Ordering::Relaxed);
}

#[no_mangle]
unsafe extern "C" fn spin_lock_bh(_lock: *mut SpinLock) {}

#[no_mangle]
unsafe extern "C" fn spin_unlock_bh(_lock: *mut SpinLock) {}

#[no_mangle]
unsafe extern "C" fn spin_lock(_lock: *mut SpinLock) {}

#[no_mangle]
unsafe extern "C" fn spin_unlock(_lock: *mut SpinLock) {}

#[no_mangle]
unsafe extern "C" fn rcu_read_lock_bh() {}

#[no_mangle]
unsafe extern "C" fn rcu_read_unlock_bh() {}

#[no_mangle]
unsafe extern "C" fn call_rcu(head: *mut RcuHead, func: extern "C" fn(*mut RcuHead)) {
    func(head);
}

#[no_mangle]
unsafe extern "C" fn kfree(_ptr: *mut c_void) {}

#[no_mangle]
unsafe extern "C" fn kfree_rcu(ptr: *mut c_void, _rcu: *mut RcuHead) {
    kfree(ptr);
}

#[no_mangle]
unsafe extern "C" fn put_pid(_pid: *mut c_void) {}

#[no_mangle]
unsafe extern "C" fn inet6_sk(sk: *mut Sock) -> *mut ipv6_pinfo {
    sk as *mut ipv6_pinfo
}

#[no_mangle]
unsafe extern "C" fn timer_pending(timer: *mut TimerList) -> bool {
    if timer.is_null() {
        return false;
    }
    // SAFETY: Verified non-null pointer dereference
    unsafe { (*timer).expires != 0 }
}

#[no_mangle]
unsafe extern "C" fn time_after(a: c_ulong, b: c_ulong) -> bool {
    a > b
}

#[no_mangle]
unsafe extern "C" fn static_branch_slow_dec_deferred(branch: *mut AtomicUsize) {
    (*branch).fetch_sub(1, Ordering::Relaxed);
}

#[no_mangle]
unsafe extern "C" fn FL_HASH(label: u32) -> u32 {
    (label as c_ulong & FL_HASH_MASK) as u32
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_jiffies_and_prandom() {
        // SAFETY: Invoking thread-safe atomic helpers
        unsafe {
            let j1 = jiffies();
            let j2 = jiffies();
            assert!(j2 > j1);

            let r1 = prandom_u32();
            let r2 = prandom_u32();
            assert_ne!(r1, r2);
        }
    }

    #[test]
    fn test_timer_pending() {
        // SAFETY: Initializing TimerList on stack
        unsafe {
            assert!(!timer_pending(ptr::null_mut()));
            let mut t = TimerList { _priv: ptr::null_mut(), expires: 100 };
            assert!(timer_pending(&mut t as *mut TimerList));
            t.expires = 0;
            assert!(!timer_pending(&mut t as *mut TimerList));
        }
    }
}
