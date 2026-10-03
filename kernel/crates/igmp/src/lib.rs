#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]

use core::panic::PanicInfo;
use kernel_types::*;

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const ENOSYS: c_int = -38;

pub const HZ: c_int = 100;
pub const IGMP_QUERY_INTERVAL: c_int = 125 * HZ;
pub const IGMP_QUERY_RESPONSE_INTERVAL: c_int = 10 * HZ;
pub const IGMP_INITIAL_REPORT_DELAY: c_int = 1;

pub const IGMP_V1: c_int = 1; pub const IGMP_V2: c_int = 2; pub const IGMP_V3: c_int = 3;

pub const IGMPV2_UNSOLICITED_REPORT_INTERVAL: c_int = 10_000;
pub const IGMPV3_UNSOLICITED_REPORT_INTERVAL: c_int = 1_000;
pub const FORCE_IGMP_VERSION: c_int = 0;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct atomic_t { pub counter: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct spinlock_t { pub raw_lock: c_uint }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct timer_list { pub _opaque: *mut c_void }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct in_device {
    pub mr_v1_seen: c_ulong,
    pub mr_v2_seen: c_ulong,
    pub mr_maxdelay: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip_mc_list {
    pub interface: *mut in_device,
    pub timer: timer_list,
    pub refcnt: atomic_t,
    pub lock: spinlock_t,
    pub tm_running: c_int,
    pub reporter: c_int,
    pub unsolicit_count: c_int,
}

#[no_mangle]
pub unsafe extern "C" fn unsolicited_report_interval(in_dev: *mut in_device) -> c_int {
    let interval_ms = if IGMP_V1_SEEN(in_dev) || IGMP_V2_SEEN(in_dev) {
        IN_DEV_CONF_GET(in_dev, IGMPV2_UNSOLICITED_REPORT_INTERVAL)
    } else {
        IN_DEV_CONF_GET(in_dev, IGMPV3_UNSOLICITED_REPORT_INTERVAL)
    };

    let mut interval_jiffies = msecs_to_jiffies(interval_ms);
    if interval_jiffies <= 0 {
        interval_jiffies = 1;
    }
    interval_jiffies
}

#[inline]
unsafe fn IGMP_V1_SEEN(in_dev: *mut in_device) -> bool {
    let dev_net = get_dev_net(in_dev);
    let force_version = IPV4_DEVCONF_ALL(dev_net, FORCE_IGMP_VERSION);
    if force_version == IGMP_V1 {
        return true;
    }

    let in_dev_force_version = IN_DEV_CONF_GET(in_dev, FORCE_IGMP_VERSION);
    if in_dev_force_version == IGMP_V1 {
        return true;
    }

    let mr_v1_seen = (*in_dev).mr_v1_seen;
    mr_v1_seen != 0 && time_before(jiffies(), mr_v1_seen)
}

#[inline]
unsafe fn IGMP_V2_SEEN(in_dev: *mut in_device) -> bool {
    let dev_net = get_dev_net(in_dev);
    let force_version = IPV4_DEVCONF_ALL(dev_net, FORCE_IGMP_VERSION);
    if force_version == IGMP_V2 {
        return true;
    }

    let in_dev_force_version = IN_DEV_CONF_GET(in_dev, FORCE_IGMP_VERSION);
    if in_dev_force_version == IGMP_V2 {
        return true;
    }

    let mr_v2_seen = (*in_dev).mr_v2_seen;
    mr_v2_seen != 0 && time_before(jiffies(), mr_v2_seen)
}

#[inline]
fn msecs_to_jiffies(msecs: c_int) -> c_int { (msecs.saturating_mul(HZ)) / 1000 }

#[inline]
unsafe fn jiffies() -> c_ulong { 0 }

#[inline]
unsafe fn time_before(a: c_ulong, b: c_ulong) -> bool {
    (a as c_long).wrapping_sub(b as c_long) < 0
}

#[inline]
unsafe fn get_dev_net(_in_dev: *mut in_device) -> *mut c_void {
    core::ptr::null_mut()
}

#[inline]
unsafe fn IN_DEV_CONF_GET(_in_dev: *mut in_device, conf: c_int) -> c_int { conf }

#[inline]
unsafe fn IPV4_DEVCONF_ALL(_net: *mut c_void, _conf: c_int) -> c_int { 0 }

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}
