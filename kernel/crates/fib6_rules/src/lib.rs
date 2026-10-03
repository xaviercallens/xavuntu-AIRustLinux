#![cfg_attr(not(target_arch = "x86_64"), no_std)]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::missing_safety_doc)]
#![allow(clippy::not_unsafe_ptr_arg_deref)]

use kernel_types::*;

const FR_ACT_TO_TBL: u32 = 0;
pub const EINVAL: core::ffi::c_int = 22;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib6_rule {
    pub common: fib_rule_common,
    pub src: in6_addr,
    pub src_len: u8,
    pub dst: in6_addr,
    pub dst_len: u8,
    pub tos: u8,
    pub table: u32,
    pub l3mdev: u32,
    pub pref: u32,
    pub action: u32,
    pub flags: u32,
    pub suppress_ifgroup: u32,
    pub suppress_prefixlen: u32,
    pub priority: u32,
    pub fwmark: u32,
    pub fwmask: u32,
    pub ifname: [c_char; 16],
    pub goto: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib_rule_common {
    pub action: u32,
    pub flags: u32,
    pub suppress_ifgroup: u32,
    pub suppress_prefixlen: u32,
    pub priority: u32,
    pub fwmark: u32,
    pub fwmask: u32,
    pub ifname: [c_char; 16],
    pub goto: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib6_info {
    pub f6i_family: u16,
    pub f6i_tclassid: u32,
    pub f6i_flowinfo: u32,
    pub f6i_secid: u32,
    pub f6i_mark: u32,
    pub f6i_ifindex: i32,
    pub f6i_nh_sel: u32,
    pub f6i_nh: *mut fib6_nh,
    pub f6i_dev: *mut c_void,
    pub f6i_flags: u32,
    pub f6i_expires: u64,
    pub f6i_protocol: u8,
    pub f6i_pmtu: u32,
    pub f6i_advmss: u32,
    pub f6i_mtu: u32,
    pub f6i_idev: *mut c_void,
    pub f6i_rt: *mut c_void,
    pub f6i_rtnl: *mut c_void,
    pub f6i_nh_sel_cnt: u32,
    pub f6i_nh_cnt: u32,
    pub f6i_nhs: *mut fib6_nh,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib6_nh {
    pub nh_common: fib_nh_common,
    pub nh_gw: in6_addr,
    pub nh_oif: i32,
    pub nh_hops: u8,
    pub nh_flags: u8,
    pub nh_scope: u8,
    pub nh_dev: *mut c_void,
    pub nh_idev: *mut c_void,
    pub nh_sdev: *mut c_void,
    pub nh_rt: *mut c_void,
    pub nh_rtnl: *mut c_void,
    pub nh_expires: u64,
    pub nh_pmtu: u32,
    pub nh_advmss: u32,
    pub nh_mtu: u32,
    pub nh_protocol: u8,
    pub nh_nh_sel: u32,
    pub nh_nh: *mut fib6_nh,
    pub nh_nh_cnt: u32,
    pub nh_nhs: *mut fib6_nh,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib_nh_common {
    pub nh_flags: u8,
    pub nh_scope: u8,
    pub nh_protocol: u8,
    pub nh_nh_sel: u32,
    pub nh_nh: *mut c_void,
    pub nh_nh_cnt: u32,
    pub nh_nhs: *mut c_void,
}


pub struct SafeFib6Rule<'a> {
    ptr: *const fib6_rule,
    _marker: core::marker::PhantomData<&'a fib6_rule>,
}
impl<'a> SafeFib6Rule<'a> {
    pub unsafe fn new(ptr: *const fib6_rule) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}

pub struct SafeFlowi6<'a> {
    ptr: *const flowi6,
    _marker: core::marker::PhantomData<&'a flowi6>,
}
impl<'a> SafeFlowi6<'a> {
    pub unsafe fn new(ptr: *const flowi6) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}

#[no_mangle]
pub unsafe extern "C" fn fib6_rule_match(
    rule: *const fib6_rule,
    fl6: *const flowi6,
    _flags: u32,
) -> bool {
    requires!(!rule.is_null(), "fib6_rule_match: rule invariant violated");
    requires!(!fl6.is_null(), "fib6_rule_match: fl6 invariant violated");
    let safe_rule = SafeFib6Rule::new(rule).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let safe_fl6 = SafeFlowi6::new(fl6).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    unsafe {
        let rule = &*(safe_rule.ptr);
        let fl6 = &*(safe_fl6.ptr);
        if rule.action != FR_ACT_TO_TBL { return false; }
        if rule.src_len > 0 {
            let src_mask = !((1 << (128 - rule.src_len)) - 1);
            let src = rule.src.in6_u.u6_addr32[0] & src_mask;
            let fl6_src = fl6.saddr.in6_u.u6_addr32[0] & src_mask;
            if src != fl6_src { return false; }
        }
        if rule.dst_len > 0 {
            let dst_mask = !((1 << (128 - rule.dst_len)) - 1);
            let dst = rule.dst.in6_u.u6_addr32[0] & dst_mask;
            let fl6_dst = fl6.daddr.in6_u.u6_addr32[0] & dst_mask;
            if dst != fl6_dst { return false; }
        }
        if rule.fwmark != 0 && (rule.fwmark & rule.fwmask) != (fl6.flowi6_mark & rule.fwmask) {
            return false;
        }
        true
    }
}


#[no_mangle]
pub unsafe extern "C" fn fib6_rule_action(
    rule: *const fib6_rule,
    fl6: *const flowi6,
    res: *mut fib6_rule_action_result,
) -> c_int {
    requires!(!rule.is_null(), "fib6_rule_action: rule invariant violated");
    requires!(!fl6.is_null(), "fib6_rule_action: fl6 invariant violated");
    requires!(!res.is_null(), "fib6_rule_action: res invariant violated");
    let safe_rule = SafeFib6Rule::new(rule).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let safe_fl6 = SafeFlowi6::new(fl6).unwrap_or_else(|| unsafe { core::hint::unreachable_unchecked() });
    let result = unsafe {
        let rule = &*(safe_rule.ptr);
        let fl6 = &*(safe_fl6.ptr);
        let res = &mut *res;
        if rule.action != FR_ACT_TO_TBL {
            -EINVAL
        } else {
            res.table = rule.table;
            res.oif = fl6.flowi6_oif;
            res.mark = fl6.flowi6_mark;
            res.tos = 0;
            0
        }
    };
    ensures!(result == 0 || result == -EINVAL, "fib6_rule_action: return value bounds");
    result
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib6_rule_action_result {
    pub table: u32,
    pub oif: i32,
    pub mark: u32,
    pub tos: u8,
}

#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
