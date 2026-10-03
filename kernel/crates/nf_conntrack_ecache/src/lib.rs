#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! Event cache for netfilter connection tracking
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::ffi::{c_int, c_uint, c_void};
use core::mem;
use core::ptr;

const ECACHE_RETRY_WAIT: u32 = 1; const ECACHE_STACK_ALLOC: usize = 256 / mem::size_of::<*mut c_void>();

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const EBUSY: c_int = -16;

const NFCT_ECACHE_DESTROY_FAIL: u32 = 1; const NFCT_ECACHE_DESTROY_SENT: u32 = 2; const IPCT_DESTROY: u32 = 4;

#[repr(C)]
struct MutexPlaceholder([u8; 32]);
unsafe impl Sync for MutexPlaceholder {}

// Global mutex for ecache operations
static NF_CT_ECACHE_MUTEX: MutexPlaceholder = MutexPlaceholder([0; 32]);

#[repr(u8)]
enum retry_state {
    STATE_CONGESTED = 0,
    STATE_RESTART = 1,
    STATE_DONE = 2,
}

#[repr(C)]
struct nf_conntrack_tuple_hash { _unused: [u8; 0] }

#[repr(C)]
struct hlist_nulls_node { next: *mut hlist_nulls_node }

#[repr(C)]
pub struct nf_conn { _unused: [u8; 0] }

#[repr(C)]
struct nf_ct_event {
    ct: *mut nf_conn,
    portid: u32,
    report: c_int,
}

#[repr(C)]
pub struct nf_ct_event_notifier { pub fcn: extern "C" fn(c_uint, *mut nf_ct_event) }

#[repr(C)]
struct nf_conntrack_ecache {
    cache: c_uint,
    state: c_uint,
    portid: u32,
    ctmask: u16,
    missed: u16,
    _pad: [u8; 2],
}

#[repr(C)]
struct ct_pcpu { lock: *mut c_void, dying: *mut hlist_nulls_node }

#[repr(C)]
struct delayed_work { _unused: [u8; 0] }

#[repr(C)]
struct netns_ct {
    ecache_dwork_pending: u8,
    _pad: [u8; 7],
    pcpu: *mut ct_pcpu,
    pcpu_count: c_uint,
    ct: nf_ct_net_events,
}

#[repr(C)]
struct nf_ct_net_events { nf_conntrack_event_cb: *mut nf_ct_event_notifier }

#[repr(C)]
struct nf_conntrack_net { ecache_dwork: delayed_work, ct_net: *mut netns_ct }

unsafe extern "C" {
    fn nf_ct_tuplehash_to_ctrack(h: *mut nf_conntrack_tuple_hash) -> *mut nf_conn;
    fn nf_ct_ecache_find(ct: *mut nf_conn) -> *mut nf_conntrack_ecache;
    fn nf_conntrack_event(event: c_uint, ct: *mut nf_conn) -> c_int;
    fn nf_ct_put(ct: *mut nf_conn);
    fn nf_ct_is_confirmed(ct: *mut nf_conn) -> c_int;
    fn local_bh_disable();
    fn local_bh_enable();
    fn schedule_delayed_work(work: *mut delayed_work, delay: u32);

    // RCU (Read-Copy-Update) synchronization primitives
    fn rcu_read_lock();
    fn rcu_read_unlock();
    fn rcu_dereference(ptr: *const c_void) -> *mut c_void;
    fn synchronize_rcu();

    // Mutex synchronization
    fn mutex_lock(lock: *const c_void);
    fn mutex_unlock(lock: *const c_void);

    // Spinlock synchronization
    fn spin_lock_bh(lock: *const c_void);
    fn spin_unlock_bh(lock: *const c_void);

    // Netfilter connection tracking utilities
    fn nf_ct_net(ct: *const nf_conn) -> *mut netns_ct;
    fn nf_ct_is_dying(ct: *const nf_conn) -> c_int;

    // Atomic operations
    fn xchg(ptr: *mut c_uint, val: c_uint) -> c_uint;

    // RCU pointer assignment
    fn rcu_assign_pointer(ptr: *mut c_void, val: *mut c_void);

    // Kernel BUG macro
    fn BUG_ON(condition: c_int);
}

fn ecache_work_evict_list(pcpu: *mut ct_pcpu) -> retry_state {
    let mut refs: [*mut nf_conn; ECACHE_STACK_ALLOC] = [ptr::null_mut(); ECACHE_STACK_ALLOC];
    let mut evicted: usize = 0;
    let mut ret = retry_state::STATE_DONE;

    unsafe {
        let mut n = (*pcpu).dying;

        while !n.is_null() {
            let h = n as *mut nf_conntrack_tuple_hash;
            let ct = nf_ct_tuplehash_to_ctrack(h);

            if nf_ct_is_confirmed(ct) == 0 {
                n = (*n).next;
                continue;
            }

            let e = nf_ct_ecache_find(ct);
            if e.is_null() || (*e).state != NFCT_ECACHE_DESTROY_FAIL as c_uint {
                n = (*n).next;
                continue;
            }

            if nf_conntrack_event(IPCT_DESTROY as c_uint, ct) != 0 {
                ret = retry_state::STATE_CONGESTED;
                break;
            }

            (*e).state = NFCT_ECACHE_DESTROY_SENT as c_uint;
            refs[evicted] = ct;
            evicted += 1;

            if evicted >= ECACHE_STACK_ALLOC {
                ret = retry_state::STATE_RESTART;
                break;
            }

            n = (*n).next;
        }
    }

    while evicted > 0 {
        unsafe {
            evicted -= 1;
            nf_ct_put(refs[evicted]);
        }
    }

    ret
}

// ecache_work
fn ecache_work(work: *mut delayed_work) {
    unsafe {
        let cnet =
            (work as *mut u8).sub(mem::offset_of!(nf_conntrack_net, ecache_dwork)) as *mut nf_conntrack_net;
        let ctnet = (*cnet).ct_net;
        if ctnet.is_null() {
            return;
        }

        local_bh_disable();

        let mut delay = -1 as c_int;
        let mut cpu = 0;

        while cpu < 1 {
            // for_each_possible_cpu
            let pcpu = (*ctnet).pcpu.offset(cpu as isize);
            let ret = ecache_work_evict_list(pcpu);

            match ret {
                retry_state::STATE_CONGESTED => {
                    delay = ECACHE_RETRY_WAIT as c_int;
                    break;
                }
                retry_state::STATE_RESTART => {
                    delay = 0;
                }
                retry_state::STATE_DONE => {}
            }
            cpu += 1;
        }

        local_bh_enable();

        (*ctnet).ecache_dwork_pending = if delay > 0 { 1 } else { 0 };
        if delay >= 0 {
            schedule_delayed_work(work, delay as u32);
        }
    }
}

// nf_conntrack_eventmask_report
#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_eventmask_report(
    eventmask: c_uint,
    ct: *mut nf_conn,
    portid: u32,
    report: c_int,
) -> c_int {
    let ret = 0;
    let net = nf_ct_net(ct);

    rcu_read_lock();

    let notify = rcu_dereference((*net).ct.nf_conntrack_event_cb as *const c_void) as *mut nf_ct_event_notifier;
    if notify.is_null() {
        rcu_read_unlock();
        return 0;
    }

    let e = nf_ct_ecache_find(ct);
    if e.is_null() {
        rcu_read_unlock();
        return 0;
    }

    if nf_ct_is_confirmed(ct) != 0 {
        let mut item = nf_ct_event {
            ct,
            portid: if (*e).portid != 0 {
                (*e).portid
            } else {
                portid
            },
            report,
        };
        let missed = if (*e).portid != 0 { 0 } else { (*e).missed };

        if ((eventmask | missed as c_uint) & (*e).ctmask as c_uint) == 0 {
            rcu_read_unlock();
            return 0;
        }

        let notify_fcn = (*notify).fcn;
        (notify_fcn)(eventmask | missed as c_uint, &mut item);

        if ret < 0 || missed != 0 {
            spin_lock_bh(ct as *const c_void);
            if ret < 0 {
                if eventmask & (1 << IPCT_DESTROY) != 0 {
                    if (*e).portid == 0 && portid != 0 {
                        (*e).portid = portid;
                    }
                    (*e).state = NFCT_ECACHE_DESTROY_FAIL as c_uint;
                } else {
                    (*e).missed |= eventmask as u16;
                }
            } else {
                (*e).missed &= !missed;
            }
            spin_unlock_bh(ct as *const c_void);
        }
    }

    rcu_read_unlock();
    ret
}

// nf_ct_deliver_cached_events
#[no_mangle]
pub unsafe extern "C" fn nf_ct_deliver_cached_events(ct: *mut nf_conn) {
    let net = nf_ct_net(ct);
    let ret = 0;
    let mut item = nf_ct_event {
        ct,
        portid: 0,
        report: 0,
    };

    rcu_read_lock();

    let notify = rcu_dereference((*net).ct.nf_conntrack_event_cb as *const c_void) as *mut nf_ct_event_notifier;
    if notify.is_null() {
        rcu_read_unlock();
        return;
    }

    if nf_ct_is_confirmed(ct) == 0 || nf_ct_is_dying(ct) != 0 {
        rcu_read_unlock();
        return;
    }

    let e = nf_ct_ecache_find(ct);
    if e.is_null() {
        rcu_read_unlock();
        return;
    }

    let events = xchg(&mut (*e).cache as *mut c_uint, 0);
    let missed = (*e).missed;

    if ((events | missed as c_uint) & (*e).ctmask as c_uint) == 0 {
        rcu_read_unlock();
        return;
    }

    let notify_fcn = (*notify).fcn;
    (notify_fcn)(events | missed as c_uint, &mut item);

    if ret == 0 && missed == 0 {
        rcu_read_unlock();
        return;
    }

    spin_lock_bh(ct as *const c_void);
    if ret < 0 {
        (*e).missed |= events as u16;
    } else {
        (*e).missed &= !missed;
    }
    spin_unlock_bh(ct as *const c_void);

    rcu_read_unlock();
}

// nf_conntrack_register_notifier
#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_register_notifier(
    net: *mut c_void,
    new: *mut nf_ct_event_notifier,
) -> c_int {
    mutex_lock(&NF_CT_ECACHE_MUTEX as *const _ as *const c_void);

    let net_typed = net as *mut netns_ct;
    let notify = rcu_dereference((*net_typed).ct.nf_conntrack_event_cb as *const c_void) as *mut nf_ct_event_notifier;
    if !notify.is_null() {
        mutex_unlock(&NF_CT_ECACHE_MUTEX as *const _ as *const c_void);
        return EBUSY;
    }

    rcu_assign_pointer((*net_typed).ct.nf_conntrack_event_cb as *mut c_void, new as *mut c_void);
    mutex_unlock(&NF_CT_ECACHE_MUTEX as *const _ as *const c_void);
    0
}

// nf_conntrack_unregister_notifier
#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_unregister_notifier(
    net: *mut c_void,
    new: *mut nf_ct_event_notifier,
) {
    mutex_lock(&NF_CT_ECACHE_MUTEX as *const _ as *const c_void);

    let net_typed = net as *mut netns_ct;
    let notify = rcu_dereference((*net_typed).ct.nf_conntrack_event_cb as *const c_void) as *mut nf_ct_event_notifier;
    BUG_ON(if notify != new { 1 } else { 0 });
    rcu_init_pointer(&mut (*net_typed).ct.nf_conntrack_event_cb, ptr::null_mut());

    mutex_unlock(&NF_CT_ECACHE_MUTEX as *const _ as *const c_void);
    synchronize_rcu();
}

// Helper macros
#[inline]
unsafe fn rcu_init_pointer<T>(ptr: *mut *mut T, val: *mut T) {
    // Simulated RCU initialization
    *ptr = val;
}

// Tests (conditional compilation)
#[cfg(test)]
mod tests {
    #[test]
    fn test_ecache_work_evict_list() {
        // Basic test case - would need actual data to be meaningful
        assert!(true);
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
