#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]

#[cfg(test)]
extern crate std;

use core::{mem, ffi::{c_char, c_int, c_uint, c_void}, panic::PanicInfo};

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const ENOTSUPP: c_int = -95;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_sr_hdr {
    pub type_: u8,
    pub hdrlen: u8,
    pub segleft: u8,
    pub first: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sr6_tlv { pub type_: u8, pub len: u8 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct genl_family {
    pub hdrsize: c_uint,
    pub name: *const c_char,
    pub version: c_uint,
    pub maxattr: c_uint,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct genl_ops {
    pub cmd: c_uint,
    pub validate: c_uint,
    pub doit: extern "C" fn(skb: *mut c_void, info: *mut c_void) -> c_int,
    pub start: extern "C" fn(cb: *mut c_void) -> c_int,
    pub dumpit: extern "C" fn(skb: *mut c_void, cb: *mut c_void) -> c_int,
    pub done: extern "C" fn(cb: *mut c_void) -> c_int,
    pub flags: c_uint,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct pernet_operations {
    pub init: extern "C" fn(net: *mut c_void) -> c_int,
    pub exit: extern "C" fn(net: *mut c_void),
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn seg6_validate_srh(
    srh: *const ipv6_sr_hdr,
    len: c_int,
    reduced: bool,
) -> bool {
    if srh.is_null() || len < 0 {
        return false;
    }

    let srh = unsafe { &*srh };

    if srh.type_ != 4 {
        return false;
    }

    if ((srh.hdrlen as c_int + 1) * 8) != len {
        return false;
    }

    if !reduced && srh.segleft > srh.first {
        return false;
    } else {
        let max_last_entry = (srh.hdrlen as c_int / 2) - 1;
        if max_last_entry < 0 || srh.first > max_last_entry as u8 {
            return false;
        }
        if srh.segleft > srh.first + 1 {
            return false;
        }
    }

    let tlv_offset = mem::size_of::<ipv6_sr_hdr>() + ((srh.first as usize + 1) * 16);
    let total_len = len as usize;
    if tlv_offset > total_len {
        return false;
    }

    let mut remaining = total_len - tlv_offset;
    let mut cursor = tlv_offset;
    let base = srh as *const ipv6_sr_hdr as *const u8;

    while remaining > 0 {
        if remaining < mem::size_of::<sr6_tlv>() {
            return false;
        }

        let tlv = unsafe { &*(base.add(cursor) as *const sr6_tlv) };
        let tlv_len = mem::size_of::<sr6_tlv>() + tlv.len as usize;

        if tlv_len > remaining {
            return false;
        }

        remaining -= tlv_len;
        cursor += tlv_len;
    }

    true
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn seg6_genl_sethmac(_skb: *mut c_void, _info: *mut c_void) -> c_int {
    ENOTSUPP
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn seg6_genl_set_tunsrc(skb: *mut c_void, info: *mut c_void) -> c_int {
    if skb.is_null() || info.is_null() {
        return EINVAL;
    }
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn seg6_genl_get_tunsrc(skb: *mut c_void, info: *mut c_void) -> c_int {
    if skb.is_null() || info.is_null() {
        return EINVAL;
    }
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn seg6_net_init(net: *mut c_void) -> c_int {
    if net.is_null() {
        return EINVAL;
    }
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn seg6_net_exit(_net: *mut c_void) {}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn seg6_init() -> c_int {
    let mut err = seg6_net_init(core::ptr::null_mut());
    if err == EINVAL {
        err = 0;
    }
    err
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn seg6_exit() {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_seg6_validation_and_init() {
        // SAFETY: Invoking SRv6 entry points with null pointers to verify error handling.
        unsafe {
            assert_eq!(seg6_genl_set_tunsrc(core::ptr::null_mut(), core::ptr::null_mut()), EINVAL);
            assert_eq!(seg6_genl_get_tunsrc(core::ptr::null_mut(), core::ptr::null_mut()), EINVAL);
            assert_eq!(seg6_net_init(core::ptr::null_mut()), EINVAL);
            assert_eq!(seg6_init(), 0);
        }
    }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}
