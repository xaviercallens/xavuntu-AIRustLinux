#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]

use core::{ffi::c_void, panic::PanicInfo, ptr};
use kernel_types::*;

pub const EINVAL: c_int = 22; pub const ENOMEM: c_int = 12; pub const ENOSYS: c_int = 38;

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net_device {
    pub type_: c_int,
    pub addr_len: c_int,
    pub dev_addr: *const u8,
    pub broadcast: *const u8,
    pub header_ops: *const c_void,
    pub flags: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct neighbour {
    pub primary_key: [u8; 16],
    pub dev: *mut net_device,
    pub type_: c_int,
    pub nud_state: c_int,
    pub ops: *const c_void,
    pub output: *const c_void,
    pub parms: *mut c_void,
    pub ha: [u8; 16],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct neigh_parms { pub reachable_time: c_int, pub data: [c_int; 10] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nd_opt_hdr { pub nd_opt_type: u8, pub nd_opt_len: u8 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ndisc_options {
    pub nd_opt_array: [*mut nd_opt_hdr; 256],
    pub nd_opts_pi_end: *mut nd_opt_hdr,
    pub nd_opts_ri: *mut nd_opt_hdr,
    pub nd_opts_ri_end: *mut nd_opt_hdr,
    pub nd_useropts: *mut nd_opt_hdr,
    pub nd_useropts_end: *mut nd_opt_hdr,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct neigh_table {
    pub family: c_int,
    pub key_len: c_int,
    pub protocol: c_int,
    pub hash: unsafe extern "C" fn(pkey: *const c_void, dev: *const net_device, hash_rnd: *mut c_uint) -> c_int,
    pub key_eq: unsafe extern "C" fn(neigh: *const neighbour, pkey: *const c_void) -> c_int,
    pub constructor: unsafe extern "C" fn(neigh: *mut neighbour) -> c_int,
    pub pconstructor: unsafe extern "C" fn(n: *mut c_void) -> c_int,
    pub pdestructor: unsafe extern "C" fn(n: *mut c_void),
    pub proxy_redo: unsafe extern "C" fn(skb: *mut sk_buff),
    pub is_multicast: unsafe extern "C" fn(pkey: *const c_void) -> c_int,
    pub allow_add: unsafe extern "C" fn(dev: *const net_device, extack: *mut c_void) -> c_int,
    pub id: [u8; 16],
    pub parms: *mut neigh_parms,
    pub gc_interval: c_int,
    pub gc_thresh1: c_int,
    pub gc_thresh2: c_int,
    pub gc_thresh3: c_int,
}

unsafe impl Sync for neigh_table {}

unsafe extern "C" {
    fn ipv6_eth_mc_map(addr: *const in6_addr, buf: *mut u8);
    fn ipv6_arcnet_mc_map(addr: *const in6_addr, buf: *mut u8);
    fn ipv6_ib_mc_map(addr: *const in6_addr, broadcast: *const u8, buf: *mut u8);
    fn ipv6_ipgre_mc_map(addr: *const in6_addr, broadcast: *const u8, buf: *mut u8);

    fn ndisc_hash(pkey: *const c_void, dev: *const net_device, hash_rnd: *mut c_uint) -> c_int;
    fn ndisc_key_eq(neigh: *const neighbour, pkey: *const c_void) -> c_int;
    fn ndisc_constructor(neigh: *mut neighbour) -> c_int;
    fn pndisc_constructor(n: *mut c_void) -> c_int;
    fn pndisc_destructor(n: *mut c_void);
    fn pndisc_redo(skb: *mut sk_buff);
    fn ndisc_is_multicast(pkey: *const c_void) -> c_int;
    fn ndisc_allow_add(dev: *const net_device, extack: *mut c_void) -> c_int;

    fn skb_put(skb: *mut sk_buff, len: c_uint) -> *mut u8;
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn __ndisc_fill_addr_option(
    skb: *mut sk_buff,
    type_: c_int,
    data: *const c_void,
    data_len: c_int,
    pad: c_int,
) -> c_int {
    let total = if pad > data_len + 2 { pad } else { data_len + 2 };
    let opt = unsafe { skb_put(skb, total as c_uint) };
    if opt.is_null() {
        return -ENOMEM;
    }

    unsafe {
        *opt.add(0) = type_ as u8;
        *opt.add(1) = ((total + 7) >> 3) as u8;
        ptr::copy_nonoverlapping(data as *const u8, opt.add(2), data_len as usize);
    }

    let rem = total - (data_len + 2);
    if rem > 0 {
        unsafe { ptr::write_bytes(opt.add((data_len + 2) as usize), 0, rem as usize) };
    }

    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ndisc_mc_map(
    addr: *const in6_addr,
    buf: *mut u8,
    dev: *mut net_device,
    dir: c_int,
) -> c_int {
    let dev_type = unsafe { (*dev).type_ };
    match dev_type {
        1 | 7 | 15 => {
            unsafe { ipv6_eth_mc_map(addr, buf) };
            0
        }
        256 => {
            unsafe { ipv6_arcnet_mc_map(addr, buf) };
            0
        }
        776 => {
            unsafe { ipv6_ib_mc_map(addr, (*dev).broadcast, buf) };
            0
        }
        772 => {
            unsafe { ipv6_ipgre_mc_map(addr, (*dev).broadcast, buf) };
            0
        }
        _ => {
            if dir != 0 {
                unsafe {
                    ptr::copy_nonoverlapping((*dev).broadcast, buf, (*dev).addr_len as usize);
                }
                0
            } else {
                -EINVAL
            }
        }
    }
}

#[unsafe(no_mangle)]
pub static nd_tbl: neigh_table = neigh_table {
    family: 10,
    key_len: 16,
    protocol: 0x86dd,
    hash: ndisc_hash,
    key_eq: ndisc_key_eq,
    constructor: ndisc_constructor,
    pconstructor: pndisc_constructor,
    pdestructor: pndisc_destructor,
    proxy_redo: pndisc_redo,
    is_multicast: ndisc_is_multicast,
    allow_add: ndisc_allow_add,
    id: [0; 16],
    parms: ptr::null_mut(),
    gc_interval: 30,
    gc_thresh1: 128,
    gc_thresh2: 512,
    gc_thresh3: 1024,
};
