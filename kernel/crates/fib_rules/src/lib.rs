#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::ffi::{c_int, c_uint, c_void};
use core::ptr::{self};
use core::mem;
use kernel_types::*;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOSYS: c_int = -38;
pub const ENETUNREACH: c_int = -101;
pub const EACCES: c_int = -13;
pub const EAGAIN: c_int = -11;
pub const ENOBUFS: c_int = -105;

// FRA constants
pub const FRA_SRC: c_int = 1; pub const FRA_DST: c_int = 2; pub const FRA_FLOW: c_int = 3;

// Type definitions

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib4_rule {
    pub common: fib_rule,
    pub dst_len: u8,
    pub src_len: u8,
    pub tos: u8,
    pub src: u32,
    pub srcmask: u32,
    pub dst: u32,
    pub dstmask: u32,
    #[cfg(CONFIG_IP_ROUTE_CLASSID)]
    pub tclassid: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib_lookup_arg {
    pub result: *mut fib_result,
    pub flags: c_uint,
    pub rule: *mut fib_rule,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib_rules_ops {
    pub family: c_int,
    pub rule_size: c_uint,
    pub addr_size: c_uint,
    pub action: Option<unsafe extern "C" fn(*mut fib_rule, *mut c_void, c_int, *mut fib_lookup_arg) -> c_int>,
    pub suppress: Option<unsafe extern "C" fn(*mut fib_rule, *mut fib_lookup_arg) -> bool>,
    pub match_: Option<unsafe extern "C" fn(*mut fib_rule, *mut c_void, c_int) -> bool>,
    pub configure: Option<unsafe extern "C" fn(*mut fib_rule, *mut c_void, *mut fib_rule_hdr, *mut *mut c_void, *mut netlink_ext_ack) -> c_int>,
    pub delete: Option<unsafe extern "C" fn(*mut fib_rule) -> c_int>,
    pub compare: Option<unsafe extern "C" fn(*mut fib_rule, *mut fib_rule_hdr, *mut *mut c_void) -> c_int>,
    pub fill: Option<unsafe extern "C" fn(*mut fib_rule, *mut c_void, *mut fib_rule_hdr) -> c_int>,
    pub nlmsg_payload: Option<unsafe extern "C" fn(*mut fib_rule) -> size_t>,
    pub flush_cache: Option<unsafe extern "C" fn(*mut fib_rules_ops)>,
    pub nlgroup: c_int,
    pub policy: *const c_void,
    pub owner: *const c_void,
    pub fro_net: *mut net,
}

unsafe impl Sync for fib_rules_ops {}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct flowi4 {
    pub daddr: u32,
    pub saddr: u32,
    pub flowi4_tos: u8,
    pub flowi4_proto: u8,
    pub fl4_sport: u16,
    pub fl4_dport: u16,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib_rule_hdr {
    pub dst_len: u8,
    pub src_len: u8,
    pub tos: u8,
    pub ip_proto: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nlattr { pub len: c_ushort, pub type_: c_ushort }

// Helper functions for container_of pattern
#[inline]
unsafe fn container_of(ptr: *const c_void, offset: usize) -> *const c_void {
    (ptr as usize - offset) as *const c_void
}

#[inline]
pub unsafe fn offset_of<T, F>(base: *const T, field: *const F) -> usize {
    (field as usize) - (base as usize)
}

#[inline]
pub fn inet_make_mask(logmask: u8) -> u32 {
    if logmask == 0 {
        0
    } else if logmask >= 32 {
        !0
    } else {
        let mask = !((1u32 << (32 - logmask)) - 1);
        mask.to_be()
    }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

#[cfg(not(test))]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rust_eh_personality() {}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn fib4_rule_matchall(rule: *const fib_rule) -> bool {
    let offset = core::mem::offset_of!(fib4_rule, tos);
    let r = container_of(rule as *const c_void, offset) as *const fib4_rule;

    if (*r).dst_len != 0 || (*r).src_len != 0 || (*r).tos != 0 {
        return false;
    }

    let c_rule = &(*r).common as *const fib_rule;
    fib_rule_matchall(c_rule)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn fib4_rule_default(rule: *const fib_rule) -> bool {
    if rule.is_null() {
        return false;
    }
    if !fib4_rule_matchall(rule) || (*rule).action != 0 || (*rule).l3mdev != core::ptr::null_mut() {
        return false;
    }

    let table = (*rule).table;
    if table != 254 && table != 253 && table != 255 {
        return false;
    }

    true
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn __fib_lookup(
    net: *mut net,
    flp: *mut flowi4,
    res: *mut fib_result,
    flags: c_uint,
) -> c_int {
    if net.is_null() || flp.is_null() || res.is_null() {
        return EINVAL;
    }

    let mut arg = fib_lookup_arg {
        result: res,
        flags,
        rule: core::ptr::null_mut(),
    };
    let mut err = 0;

    // update flow if oif or iif point to device enslaved to l3mdev
    l3mdev_update_flow(&mut (*net).ipv4, flp as *mut flowi);

    err = fib_rules_lookup((*net).ipv4.rules_ops.cast::<fib_rules_ops>(), flp as *mut flowi, 0, &mut arg);

    #[cfg(CONFIG_IP_ROUTE_CLASSID)]
    {
        if !arg.rule.is_null() {
            let rule4 = container_of(
                arg.rule as *const c_void,
                core::mem::offset_of!(fib4_rule, tclassid),
            ) as *const fib4_rule;
            (*res).tclassid = (*rule4).tclassid;
        } else {
            (*res).tclassid = 0;
        }
    }

    if err == -13 {
        err = -ENETUNREACH;
    }

    err
}

#[no_mangle]
pub unsafe extern "C" fn fib4_rule_action(
    rule: *mut fib_rule,
    flp: *mut c_void,
    _flags: c_int,
    arg: *mut fib_lookup_arg,
) -> c_int {
    let mut err = -EAGAIN;
    let mut tb_id = 0;
    let mut tbl: *mut fib_table = ptr::null_mut();

    match (*rule).action {
        0 => {} // FR_ACT_TO_TBL
        1 => return -ENETUNREACH, // FR_ACT_UNREACHABLE
        2 => return -EACCES, // FR_ACT_PROHIBIT
        3 => return -EINVAL, // FR_ACT_BLACKHOLE
        _ => return -EINVAL,
    }

    rcu_read_lock();

    tb_id = fib_rule_get_table(rule, arg);
    tbl = fib_get_table((*rule).fr_net, tb_id);
    if !tbl.is_null() {
        err = fib_table_lookup(
            tbl,
            flp.cast::<flowi4>(),
            (*arg).result as *mut fib_result,
            (*arg).flags,
        );
    }

    rcu_read_unlock();

    err
}

#[no_mangle]
pub unsafe extern "C" fn fib4_rule_suppress(
    rule: *mut fib_rule,
    arg: *mut fib_lookup_arg,
) -> bool {
    let result = (*arg).result as *mut fib_result;
    let mut dev: *mut net_device = ptr::null_mut();

    if !(*result).fi.is_null() {
        let nhc = fib_info_nhc((*result).fi, 0) as *mut fib_nh_common;
        dev = (*nhc).nhc_dev;
    }

    if (*result).prefixlen <= (*rule).suppress_prefixlen {
        suppress_route(result, arg, dev.cast::<c_void>());
        return true;
    }

    if (*rule).suppress_ifgroup != -1 && !dev.is_null() && (*dev).group == (*rule).suppress_ifgroup {
        suppress_route(result, arg, dev.cast::<c_void>());
        return true;
    }

    false
}

fn suppress_route(result: *mut fib_result, arg: *mut fib_lookup_arg, _dev: *mut c_void) {
    unsafe {
        if !((*arg).flags & 1) != 0 {
            fib_info_put((*result).fi);
        }
    }
}

#[no_mangle]
pub unsafe extern "C" fn fib4_rule_match(
    rule: *mut fib_rule,
    fl: *mut c_void,
    _flags: c_int,
) -> bool {
    let r = rule as *mut fib4_rule;
    let fl4 = fl.cast::<flowi4>();

    if ((((*fl4).saddr ^ (*r).src) & (*r).srcmask) != 0) ||
       ((((*fl4).daddr ^ (*r).dst) & (*r).dstmask) != 0) {
        return false;
    }

    if (*r).tos != 0 && (*r).tos != (*fl4).flowi4_tos {
        return false;
    }

    if (*rule).ip_proto != 0 && (*rule).ip_proto != (*fl4).flowi4_proto {
        return false;
    }

    if fib_rule_port_range_set((*rule).sport_range) &&
       !fib_rule_port_inrange((*rule).sport_range, (*fl4).fl4_sport) {
        return false;
    }

    if fib_rule_port_range_set((*rule).dport_range) &&
       !fib_rule_port_inrange((*rule).dport_range, (*fl4).fl4_dport) {
        return false;
    }

    true
}

// External functions (declared in other modules)
extern "C" {
    fn fib_rule_matchall(rule: *const fib_rule) -> bool;
    fn l3mdev_update_flow(net: *mut net_ipv4, fl: *mut flowi);
    fn fib_rules_lookup(ops: *mut fib_rules_ops, fl: *mut flowi, flags: c_int, arg: *mut fib_lookup_arg) -> c_int;
    fn rcu_read_lock();
    fn rcu_read_unlock();
    fn fib_rule_get_table(rule: *mut fib_rule, arg: *mut fib_lookup_arg) -> u32;
    fn fib_get_table(net: *mut net, id: u32) -> *mut fib_table;
    fn fib_table_lookup(
        tbl: *mut fib_table,
        flp: *mut flowi4,
        res: *mut fib_result,
        flags: c_uint,
    ) -> c_int;
    fn fib_info_nhc(fi: *mut c_void, index: c_int) -> *mut c_void;
    fn fib_info_put(fi: *mut c_void);
    fn fib_rule_port_range_set(range: *mut c_void) -> bool;
    fn fib_rule_port_inrange(range: *mut c_void, port: u16) -> bool;
    fn fib_unmerge(net: *mut net) -> c_int;
    fn fib_default_rule_add(ops: *mut fib_rules_ops, priority: u16, table: c_int, flags: c_int) -> c_int;
    fn fib_rules_unregister(ops: *mut fib_rules_ops);
    fn rt_cache_flush(net: *mut net);
    fn fib_rules_seq_read(net: *mut net, family: c_int) -> c_uint;
    fn fib_rules_dump(net: *mut net, nb: *mut c_void, family: c_int, extack: *mut netlink_ext_ack) -> c_int;
    fn fib_rules_register(ops: *const fib_rules_ops, net: *mut net) -> *mut fib_rules_ops;
    fn fib_default_rules_init(ops: *mut fib_rules_ops) -> c_int;
}

// Module initialization
#[no_mangle]
pub unsafe extern "C" fn fib4_rules_init(net: *mut net) -> c_int {
    let mut ops: *mut fib_rules_ops = ptr::null_mut();
    let mut err = 0;

    ops = fib_rules_register(&FIB4_RULES_OPS_TEMPLATE, net);
    if ops.is_null() {
        return -ENOMEM;
    }

    err = fib_default_rules_init(ops);
    if err < 0 {
        fib_rules_unregister(ops);
        return err;
    }

    (*net).ipv4.rules_ops = ops.cast::<c_void>();
    (*net).ipv4.fib_has_custom_rules = false;
    (*net).ipv4.fib_rules_require_fldissect = 0;

    0
}

#[no_mangle]
pub unsafe extern "C" fn fib4_rules_exit(net: *mut net) {
    fib_rules_unregister((*net).ipv4.rules_ops.cast::<fib_rules_ops>());
}

// Static rules_ops template
static FIB4_RULES_OPS_TEMPLATE: fib_rules_ops = fib_rules_ops {
    family: 2, // AF_INET
    rule_size: mem::size_of::<fib4_rule>() as c_uint,
    addr_size: 4, // sizeof(u32)
    action: Some(fib4_rule_action),
    suppress: Some(fib4_rule_suppress),
    match_: Some(fib4_rule_match),
    configure: Some(fib4_rule_configure),
    delete: Some(fib4_rule_delete),
    compare: Some(fib4_rule_compare),
    fill: Some(fib4_rule_fill),
    nlmsg_payload: Some(fib4_rule_nlmsg_payload),
    flush_cache: Some(fib4_rule_flush_cache),
    nlgroup: 5, // RTNLGRP_IPV4_RULE
    policy: ptr::null(),
    owner: ptr::null(),
    fro_net: ptr::null_mut(),
};

// Helper functions
#[no_mangle]
pub unsafe extern "C" fn fib4_rules_seq_read(net: *mut net) -> c_uint {
    fib_rules_seq_read(net, 2) // AF_INET
}

#[no_mangle]
pub unsafe extern "C" fn fib4_rules_dump(
    net: *mut net,
    nb: *mut c_void,
    extack: *mut netlink_ext_ack,
) -> c_int {
    fib_rules_dump(net, nb, 2, extack) // AF_INET
}

#[no_mangle]
pub unsafe extern "C" fn fib4_rule_flush_cache(ops: *mut fib_rules_ops) {
    rt_cache_flush((*ops).fro_net);
}

#[no_mangle]
pub unsafe extern "C" fn fib4_rule_configure(
    rule: *mut fib_rule,
    skb: *mut c_void,
    frh: *mut fib_rule_hdr,
    tb: *mut *mut c_void,
    extack: *mut netlink_ext_ack,
) -> c_int {
    let net = sock_net((*skb.cast::<sk_buff>()).sk);
    let rule4 = rule as *mut fib4_rule;
    let mut err = -EINVAL;

    if (*frh).tos & !0x0F != 0 {
        NL_SET_ERR_MSG(extack, "Invalid tos\0".as_ptr() as *const c_char);
        return err;
    }

    err = fib_unmerge(net);
    if err < 0 {
        return err;
    }

    if (*rule).table == 0 && (*rule).l3mdev == core::ptr::null_mut() && (*rule).action == 0 {
        let table = fib_empty_table(net);
        if table.is_null() {
            return -ENOBUFS;
        }
        (*rule).table = (*table).tb_id;
    }

    if (*frh).src_len != 0 {
        (*rule4).src = nla_get_in_addr(*tb.offset(FRA_SRC as isize));
    }

    if (*frh).dst_len != 0 {
        (*rule4).dst = nla_get_in_addr(*tb.offset(FRA_DST as isize));
    }

    #[cfg(CONFIG_IP_ROUTE_CLASSID)]
    {
        if !(*tb.offset(FRA_FLOW as isize)).is_null() {
            (*rule4).tclassid = nla_get_u32(*tb.offset(FRA_FLOW as isize));
            if (*rule4).tclassid != 0 {
                (*net).ipv4.fib_num_tclassid_users += 1;
            }
        }
    }

    if fib_rule_requires_fldissect(rule) {
        (*net).ipv4.fib_rules_require_fldissect += 1;
    }

    (*rule4).src_len = (*frh).src_len;
    (*rule4).srcmask = inet_make_mask((*rule4).src_len);
    (*rule4).dst_len = (*frh).dst_len;
    (*rule4).dstmask = inet_make_mask((*rule4).dst_len);
    (*rule4).tos = (*frh).tos;

    (*net).ipv4.fib_has_custom_rules = true;

    0
}

#[no_mangle]
pub unsafe extern "C" fn fib4_rule_delete(rule: *mut fib_rule) -> c_int {
    let net = (*rule).fr_net;
    let mut err = 0;

    err = fib_unmerge(net);
    if err < 0 {
        return err;
    }

    #[cfg(CONFIG_IP_ROUTE_CLASSID)]
    {
        let rule4 = rule as *mut fib4_rule;
        if (*rule4).tclassid != 0 {
            (*net).ipv4.fib_num_tclassid_users -= 1;
        }
    }

    (*net).ipv4.fib_has_custom_rules = true;

    if (*net).ipv4.fib_rules_require_fldissect != 0 && fib_rule_requires_fldissect(rule) {
        (*net).ipv4.fib_rules_require_fldissect -= 1;
    }

    0
}

#[no_mangle]
pub unsafe extern "C" fn fib4_rule_compare(
    rule: *mut fib_rule,
    frh: *mut fib_rule_hdr,
    tb: *mut *mut c_void,
) -> c_int {
    let rule4 = rule as *mut fib4_rule;

    if (*frh).src_len != 0 && (*rule4).src_len != (*frh).src_len {
        return 0;
    }

    if (*frh).dst_len != 0 && (*rule4).dst_len != (*frh).dst_len {
        return 0;
    }

    if (*frh).tos != 0 && (*rule4).tos != (*frh).tos {
        return 0;
    }

    #[cfg(CONFIG_IP_ROUTE_CLASSID)]
    {
        if !(*tb.offset(FRA_FLOW as isize)).is_null() && (*rule4).tclassid != nla_get_u32(*tb.offset(FRA_FLOW as isize)) {
            return 0;
        }
    }

    if (*frh).src_len != 0 && (*rule4).src != nla_get_in_addr(*tb.offset(FRA_SRC as isize)) {
        return 0;
    }

    if (*frh).dst_len != 0 && (*rule4).dst != nla_get_in_addr(*tb.offset(FRA_DST as isize)) {
        return 0;
    }

    1
}

#[no_mangle]
pub unsafe extern "C" fn fib4_rule_fill(
    rule: *mut fib_rule,
    skb: *mut c_void,
    frh: *mut fib_rule_hdr,
) -> c_int {
    let rule4 = rule as *mut fib4_rule;

    (*frh).dst_len = (*rule4).dst_len;
    (*frh).src_len = (*rule4).src_len;
    (*frh).tos = (*rule4).tos;

    if (*rule4).dst_len != 0 && nla_put_in_addr(skb, FRA_DST, (*rule4).dst) != 0 {
        return -ENOBUFS;
    }

    if (*rule4).src_len != 0 && nla_put_in_addr(skb, FRA_SRC, (*rule4).src) != 0 {
        return -ENOBUFS;
    }

    #[cfg(CONFIG_IP_ROUTE_CLASSID)]
    {
        if (*rule4).tclassid != 0 && nla_put_u32(skb, FRA_FLOW, (*rule4).tclassid) != 0 {
            return -ENOBUFS;
        }
    }

    0
}

#[no_mangle]
pub unsafe extern "C" fn fib4_rule_nlmsg_payload(_rule: *mut fib_rule) -> size_t {
    nla_total_size(4) /* dst */
        + nla_total_size(4) /* src */
        + nla_total_size(4) /* flow */
}

// External helper functions
extern "C" {
    fn sock_net(sk: *mut c_void) -> *mut net;
    fn fib_empty_table(net: *mut net) -> *mut fib_table;
    fn nla_get_in_addr(attr: *mut c_void) -> u32;
    fn nla_get_u32(attr: *mut c_void) -> u32;
    fn nla_put_in_addr(skb: *mut c_void, type_: c_int, data: u32) -> c_int;
    fn nla_total_size(len: size_t) -> size_t;
    fn fib_rule_requires_fldissect(rule: *mut fib_rule) -> bool;
    fn NL_SET_ERR_MSG(extack: *mut netlink_ext_ack, msg: *const c_char);
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── FFI stubs (linker satisfaction) ──────────────────────────────────────
    // All extern "C" symbols referenced by code paths reachable from these
    // tests must be defined here so the test binary links without a kernel.

    #[no_mangle] extern "C" fn fib_rule_matchall(_r: *const fib_rule) -> bool {
    let _ret = false;
    _ret
}
    #[no_mangle] extern "C" fn l3mdev_update_flow(_net: *mut net_ipv4, _fl: *mut flowi) {}
    #[no_mangle] extern "C" fn fib_rules_lookup(_o: *mut fib_rules_ops, _fl: *mut flowi, _f: c_int, _a: *mut fib_lookup_arg) -> c_int {
    let _ret = 0;
    _ret
}
    #[no_mangle] extern "C" fn rcu_read_lock() {}
    #[no_mangle] extern "C" fn rcu_read_unlock() {}
    #[no_mangle] extern "C" fn fib_rule_get_table(_r: *mut fib_rule, _a: *mut fib_lookup_arg) -> u32 {
    let _ret = 0;
    _ret
}
    #[no_mangle] extern "C" fn fib_get_table(_n: *mut net, _id: u32) -> *mut fib_table {
    let _ret = core::ptr::null_mut();
    _ret
}
    #[no_mangle] extern "C" fn fib_table_lookup(_t: *mut fib_table, _f: *mut flowi4, _r: *mut fib_result, _g: c_uint) -> c_int {
    let _ret = 0;
    _ret
}
    #[no_mangle] extern "C" fn fib_info_nhc(_fi: *mut c_void, _i: c_int) -> *mut c_void {
    let _ret = core::ptr::null_mut();
    _ret
}
    #[no_mangle] extern "C" fn fib_info_put(_fi: *mut c_void) {}
    #[no_mangle] extern "C" fn fib_rule_port_range_set(_r: *mut c_void) -> bool {
    let _ret = false;
    _ret
}
    #[no_mangle] extern "C" fn fib_rule_port_inrange(_r: *mut c_void, _p: u16) -> bool {
    let _ret = false;
    _ret
}
    #[no_mangle] extern "C" fn fib_unmerge(_n: *mut net) -> c_int {
    let _ret = 0;
    _ret
}
    #[no_mangle] extern "C" fn fib_default_rule_add(_o: *mut fib_rules_ops, _p: u16, _t: c_int, _f: c_int) -> c_int {
    let _ret = 0;
    _ret
}
    #[no_mangle] extern "C" fn fib_rules_unregister(_o: *mut fib_rules_ops) {}
    #[no_mangle] extern "C" fn rt_cache_flush(_n: *mut net) {}
    #[no_mangle] extern "C" fn fib_rules_seq_read(_n: *mut net, _f: c_int) -> c_uint {
    let _ret = 0;
    _ret
}
    #[no_mangle] extern "C" fn fib_rules_dump(_n: *mut net, _nb: *mut c_void, _f: c_int, _e: *mut netlink_ext_ack) -> c_int {
    let _ret = 0;
    _ret
}
    #[no_mangle] extern "C" fn fib_rules_register(_o: *const fib_rules_ops, _n: *mut net) -> *mut fib_rules_ops {
    let _ret = core::ptr::null_mut();
    _ret
}
    #[no_mangle] extern "C" fn fib_default_rules_init(_o: *mut fib_rules_ops) -> c_int {
    let _ret = 0;
    _ret
}
    #[no_mangle] extern "C" fn sock_net(_sk: *mut c_void) -> *mut net {
    let _ret = core::ptr::null_mut();
    _ret
}
    #[no_mangle] extern "C" fn fib_empty_table(_n: *mut net) -> *mut fib_table {
    let _ret = core::ptr::null_mut();
    _ret
}
    #[no_mangle] extern "C" fn nla_get_in_addr(_a: *mut c_void) -> u32 {
    let _ret = 0;
    _ret
}
    #[no_mangle] extern "C" fn nla_get_u32(_a: *mut c_void) -> u32 {
    let _ret = 0;
    _ret
}
    #[no_mangle] extern "C" fn nla_put_in_addr(_s: *mut c_void, _t: c_int, _d: u32) -> c_int {
    let _ret = 0;
    _ret
}
    #[no_mangle] extern "C" fn nla_total_size(_l: size_t) -> size_t {
    let _ret = 0;
    _ret
}
    #[no_mangle] extern "C" fn fib_rule_requires_fldissect(_r: *mut fib_rule) -> bool {
    let _ret = false;
    _ret
}
    #[no_mangle] extern "C" fn NL_SET_ERR_MSG(_e: *mut netlink_ext_ack, _m: *const c_char) {}

    // ── constant / ABI invariant tests ───────────────────────────────────────

    #[test]
    fn test_errno_constants() {
        assert_eq!(EINVAL, -22);
        assert_eq!(ENOMEM, -12);
        assert_eq!(ENOSYS, -38);
        assert_eq!(ENETUNREACH, -101);
        assert_eq!(EACCES, -13);
        assert_eq!(EAGAIN, -11);
        assert_eq!(ENOBUFS, -105);
    }

    #[test]
    fn test_fra_attribute_constants() {
        assert_eq!(FRA_SRC, 1);
        assert_eq!(FRA_DST, 2);
        assert_eq!(FRA_FLOW, 3);
    }

    // ── inet_make_mask boundary tests ────────────────────────────────────────

    #[test]
    fn test_inet_make_mask_zero_prefix() {
        assert_eq!(inet_make_mask(0), 0);
    }

    #[test]
    fn test_inet_make_mask_full_prefix() {
        assert_eq!(inet_make_mask(32), !0u32);
    }

    #[test]
    fn test_inet_make_mask_twenty_four() {
        let expected = 0xFFFF_FF00u32.to_be();
        assert_eq!(inet_make_mask(24), expected);
    }

    #[test]
    fn test_inet_make_mask_sixteen() {
        let expected = 0xFFFF_0000u32.to_be();
        assert_eq!(inet_make_mask(16), expected);
    }

    // ── struct layout / size tests ───────────────────────────────────────────

    #[test]
    fn test_flowi4_field_sizes() {
        assert!(core::mem::size_of::<flowi4>() >= 12);
    }

    #[test]
    fn test_fib_rule_hdr_field_count() {
        assert_eq!(core::mem::size_of::<fib_rule_hdr>(), 4);
    }

    // ── null-ptr guard (pure Rust logic, no extern calls) ────────────────────

    #[test]
    fn test_fib4_rule_default_null_returns_false() {
        // fib4_rule_default checks rule.is_null() before any dereference
        let result = unsafe { fib4_rule_default(core::ptr::null()) };
        assert!(!result, "null rule must not be considered a default rule");
    }
}

