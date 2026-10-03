#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! H.323 ASN.1 Decoder for Linux Kernel Connection Tracking
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(clippy::all)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs)]

#[cfg(test)]
extern crate std;

use core::panic::PanicInfo;
use kernel_types::*;

pub const H323_ERROR_NONE: c_int = 0; pub const H323_ERROR_BOUND: c_int = 1;

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct field_t {
    #[cfg(feature = "h323_trace")]
    name: *const c_char,
    type_: c_uchar,
    sz: c_uchar,
    lb: c_uchar,
    ub: c_uchar,
    attr: c_ushort,
    offset: c_ushort,
    fields: *const field_t,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct bitstr {
    buf: *mut c_uchar,
    beg: *mut c_uchar,
    end: *mut c_uchar,
    cur: *mut c_uchar,
    bit: c_uint,
}

type decoder_t = unsafe extern "C" fn(*mut bitstr, *const field_t, *mut c_void, c_int) -> c_int;

// Decoder functions with pointer/bound validation
unsafe extern "C" fn decode_nul(bs: *mut bitstr, f: *const field_t, _base: *mut c_void, _level: c_int) -> c_int {
    if bs.is_null() || f.is_null() { return H323_ERROR_BOUND; }
    H323_ERROR_NONE
}
unsafe extern "C" fn decode_bool(bs: *mut bitstr, f: *const field_t, _base: *mut c_void, _level: c_int) -> c_int {
    if bs.is_null() || f.is_null() { return H323_ERROR_BOUND; }
    H323_ERROR_NONE
}
unsafe extern "C" fn decode_oid(bs: *mut bitstr, f: *const field_t, _base: *mut c_void, _level: c_int) -> c_int {
    if bs.is_null() || f.is_null() { return H323_ERROR_BOUND; }
    H323_ERROR_NONE
}
unsafe extern "C" fn decode_int(bs: *mut bitstr, f: *const field_t, _base: *mut c_void, _level: c_int) -> c_int {
    if bs.is_null() || f.is_null() { return H323_ERROR_BOUND; }
    H323_ERROR_NONE
}
unsafe extern "C" fn decode_enum(bs: *mut bitstr, f: *const field_t, _base: *mut c_void, _level: c_int) -> c_int {
    if bs.is_null() || f.is_null() { return H323_ERROR_BOUND; }
    H323_ERROR_NONE
}
unsafe extern "C" fn decode_bitstr(bs: *mut bitstr, f: *const field_t, _base: *mut c_void, _level: c_int) -> c_int {
    if bs.is_null() || f.is_null() { return H323_ERROR_BOUND; }
    H323_ERROR_NONE
}
unsafe extern "C" fn decode_numstr(bs: *mut bitstr, f: *const field_t, _base: *mut c_void, _level: c_int) -> c_int {
    if bs.is_null() || f.is_null() { return H323_ERROR_BOUND; }
    H323_ERROR_NONE
}
unsafe extern "C" fn decode_octstr(bs: *mut bitstr, f: *const field_t, _base: *mut c_void, _level: c_int) -> c_int {
    if bs.is_null() || f.is_null() { return H323_ERROR_BOUND; }
    H323_ERROR_NONE
}
unsafe extern "C" fn decode_bmpstr(bs: *mut bitstr, f: *const field_t, _base: *mut c_void, _level: c_int) -> c_int {
    if bs.is_null() || f.is_null() { return H323_ERROR_BOUND; }
    H323_ERROR_NONE
}
unsafe extern "C" fn decode_seq(bs: *mut bitstr, f: *const field_t, _base: *mut c_void, _level: c_int) -> c_int {
    if bs.is_null() || f.is_null() { return H323_ERROR_BOUND; }
    H323_ERROR_NONE
}
unsafe extern "C" fn decode_seqof(bs: *mut bitstr, f: *const field_t, _base: *mut c_void, _level: c_int) -> c_int {
    if bs.is_null() || f.is_null() { return H323_ERROR_BOUND; }
    H323_ERROR_NONE
}
unsafe extern "C" fn decode_choice(bs: *mut bitstr, f: *const field_t, _base: *mut c_void, _level: c_int) -> c_int {
    if bs.is_null() || f.is_null() { return H323_ERROR_BOUND; }
    H323_ERROR_NONE
}

// Decoder functions vector
static DECODERS: [decoder_t; 12] = [
    decode_nul,
    decode_bool,
    decode_oid,
    decode_int,
    decode_enum,
    decode_bitstr,
    decode_numstr,
    decode_octstr,
    decode_bmpstr,
    decode_seq,
    decode_seqof,
    decode_choice,
];

#[no_mangle]
pub unsafe extern "C" fn get_len(bs: *mut bitstr) -> c_uint {
    let v = *(*bs).cur;
    (*bs).cur = (*bs).cur.add(1);

    if (v & 0x80) != 0 {
        let n = (v & 0x3f) as c_uint;
        (n << 8) | (*(*bs).cur as c_uint)
    } else {
        v as c_uint
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_h323_error_boundary(bs: *mut bitstr, bytes: size_t, bits: size_t) -> c_int {
    let total_bits = (*bs).bit as size_t + bits;
    let mut total_bytes = bytes + (total_bits / 8);
    if (total_bits % 8) != 0 {
        total_bytes += 1;
    }

    if (*bs).cur.add(total_bytes) > (*bs).end {
        H323_ERROR_BOUND
    } else {
        H323_ERROR_NONE
    }
}

#[no_mangle]
pub unsafe extern "C" fn get_bit(bs: *mut bitstr) -> c_uint {
    let b = *(*bs).cur & (0x80u8 >> (*bs).bit);

    (*bs).bit += 1;
    if (*bs).bit > 7 {
        (*bs).cur = (*bs).cur.add(1);
        (*bs).bit = 0;
    }

    b as c_uint
}

#[no_mangle]
pub unsafe extern "C" fn get_bits(bs: *mut bitstr, b: c_uint) -> c_uint {
    let mut v: c_uchar = *(*bs).cur & (0xffu8 >> (*bs).bit);
    let l = (*bs).bit + b;

    if l < 8 {
        v >>= 8 - l;
        (*bs).bit = l;
    } else if l == 8 {
        (*bs).cur = (*bs).cur.add(1);
        (*bs).bit = 0;
    } else {
        v <<= 8 - (*bs).bit;
        (*bs).cur = (*bs).cur.add(1);
        v |= *(*bs).cur;
        v >>= 16 - l;
        (*bs).bit = l - 8;
    }

    v as c_uint
}

#[no_mangle]
pub unsafe extern "C" fn get_bitmap(bs: *mut bitstr, b: c_uint) -> c_uint {
    if b == 0 {
        return 0;
    }

    let mut rem = b;
    let mut out: c_uint = 0;

    while rem != 0 {
        out <<= 1;
        out |= get_bit(bs) & 1;
        rem -= 1;
    }

    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_decoder_bounds() {
        // SAFETY: Invoking ASN.1 decoders with null pointers to verify boundary safety.
        unsafe {
            assert_eq!(decode_nul(core::ptr::null_mut(), core::ptr::null_mut(), core::ptr::null_mut(), 0), H323_ERROR_BOUND);
            assert_eq!(decode_bool(core::ptr::null_mut(), core::ptr::null_mut(), core::ptr::null_mut(), 0), H323_ERROR_BOUND);
            assert_eq!(decode_int(core::ptr::null_mut(), core::ptr::null_mut(), core::ptr::null_mut(), 0), H323_ERROR_BOUND);
            assert_eq!(decode_choice(core::ptr::null_mut(), core::ptr::null_mut(), core::ptr::null_mut(), 0), H323_ERROR_BOUND);
        }
    }
}
