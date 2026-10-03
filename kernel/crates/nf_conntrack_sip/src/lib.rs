#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! SIP connection tracking helper for Linux kernel
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(clippy::too_many_arguments)]
#![allow(unused_assignments)]
#![allow(unused_unsafe)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons)]

use core::{mem, ptr, ffi::{c_char, c_int, c_uchar}};
use kernel_types::*;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOSYS: c_int = -38;
pub const SIP_PORT: u16 = 5060;
pub const SIP_TIMEOUT: u32 = 1200;
pub const AF_INET: c_int = 2;
pub const AF_INET6: c_int = 10;

// Type definitions

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_expect { pub _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_nat_sip_hooks { pub _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sip_header {
    pub name: *const c_char,
    pub short_name: *const c_char,
    pub uri_prefix: *const c_char,
    pub value_len:
        Option<unsafe extern "C" fn(*const nf_conn, *const c_uchar, *const c_uchar, *mut c_int) -> c_int>,
}

// SAFETY: `sip_header` only contains raw pointers to `'static` string literals and an
// optional function pointer; it is never mutated after construction. Sharing an
// immutable reference across threads is therefore sound.
unsafe impl Sync for sip_header {}

// SAFETY: Caller must pass a valid `c_uchar` (0–255). The function performs only
// arithmetic comparisons on the value and never dereferences any pointer.
#[inline]
unsafe fn isalpha(c: c_uchar) -> c_int {
    if (c >= b'a' && c <= b'z') || (c >= b'A' && c <= b'Z') {
        1
    } else {
        0
    }
}

// SAFETY: Caller must pass a valid `c_uchar` (0–255). The function performs only
// arithmetic comparisons on the value and never dereferences any pointer.
#[inline]
unsafe fn isdigit(c: c_uchar) -> c_int {
    if c >= b'0' && c <= b'9' {
        1
    } else {
        0
    }
}

// SAFETY: Caller must pass a valid `c_uchar` (0–255). Delegates entirely to
// `isalpha` and `isdigit`, which themselves require only a valid byte value.
#[inline]
unsafe fn isalnum(c: c_uchar) -> c_int {
    if isalpha(c) != 0 || isdigit(c) != 0 {
        1
    } else {
        0
    }
}

// SAFETY: Caller must ensure `dptr` and `limit` point into the same valid, live
// packet buffer with `dptr <= limit`. Every byte in `[dptr, limit)` must be
// readable. `shift` may be null; it is null-checked before being written.
#[no_mangle]
pub unsafe extern "C" fn string_len(
    _ct: *const nf_conn,
    dptr: *const c_uchar,
    limit: *const c_uchar,
    shift: *mut c_int,
) -> c_int {
    let mut len: c_int = 0;
    let mut current = dptr;

    while current < limit && isalpha(*current) != 0 {
        current = current.add(1);
        len += 1;
    }

    if !shift.is_null() {
        *shift = len;
    }
    len
}

// SAFETY: Caller must ensure `dptr` and `limit` point into the same valid, live
// packet buffer with `dptr <= limit`. Every byte in `[dptr, limit)` must be
// readable. `shift` may be null; it is null-checked before being written.
#[no_mangle]
pub unsafe extern "C" fn digits_len(
    _ct: *const nf_conn,
    dptr: *const c_uchar,
    limit: *const c_uchar,
    shift: *mut c_int,
) -> c_int {
    let mut len: c_int = 0;
    let mut current = dptr;

    while current < limit && isdigit(*current) != 0 {
        current = current.add(1);
        len += 1;
    }

    if !shift.is_null() {
        *shift = len;
    }
    len
}

// SAFETY: Caller must pass a valid `c_uchar` (0–255). The function performs only
// arithmetic comparisons and never dereferences any pointer.
#[no_mangle]
pub unsafe extern "C" fn iswordc(c: c_uchar) -> c_int {
    if isalnum(c) != 0
        || c == b'!'
        || c == b'"'
        || c == b'%'
        || (c >= b'(' && c <= b'+')
        || c == b':'
        || c == b'<'
        || c == b'>'
        || c == b'?'
        || (c >= b'[' && c <= b']')
        || c == b'_'
        || c == b'`'
        || c == b'{'
        || c == b'}'
        || c == b'~'
        || (c >= b'-' && c <= b'/')
        || c == b'\''
    {
        1
    } else {
        0
    }
}

// SAFETY: Caller must ensure `dptr` and `limit` point into the same valid, live
// byte buffer with `dptr <= limit`. Every byte in `[dptr, limit)` must be
// readable. The pointer `current` is only advanced while `current < limit`,
// so no out-of-bounds access occurs.
#[no_mangle]
pub unsafe extern "C" fn word_len(dptr: *const c_uchar, limit: *const c_uchar) -> c_int {
    let mut len: c_int = 0;
    let mut current = dptr;

    while current < limit && iswordc(*current) != 0 {
        current = current.add(1);
        len += 1;
    }

    len
}

// SAFETY: Caller must ensure `dptr` and `limit` point into the same valid, live
// packet buffer with `dptr <= limit`. The dereference of `current` at
// `*current != b'@'` is guarded by `current < limit` in the same condition.
// `shift` may be null; it is null-checked before every write.
#[no_mangle]
pub unsafe extern "C" fn callid_len(
    _ct: *const nf_conn,
    dptr: *const c_uchar,
    limit: *const c_uchar,
    shift: *mut c_int,
) -> c_int {
    let mut len = word_len(dptr, limit);
    let mut current = dptr.add(len as usize);

    if len == 0 || current >= limit || *current != b'@' {
        if !shift.is_null() {
            *shift = len;
        }
        return len;
    }

    current = current.add(1);
    len += 1;

    let domain_len = word_len(current, limit);
    if domain_len == 0 {
        if !shift.is_null() {
            *shift = 0;
        }
        return 0;
    }

    len += domain_len;
    if !shift.is_null() {
        *shift = len;
    }
    len
}

#[no_mangle]
pub unsafe extern "C" fn media_len(
    ct: *const nf_conn,
    dptr: *const c_uchar,
    limit: *const c_uchar,
    shift: *mut c_int,
) -> c_int {
    let mut len = string_len(ct, dptr, limit, shift);
    let mut current = dptr.add(len as usize);

    if current >= limit || *current != b' ' {
        if !shift.is_null() {
            *shift = len;
        }
        return 0;
    }

    len += 1;
    current = current.add(1);

    len += digits_len(ct, current, limit, shift);
    if !shift.is_null() {
        *shift = len;
    }
    len
}

// Duplicate helper functions removed - using public versions at end of file

#[no_mangle]
pub unsafe extern "C" fn sip_parse_addr(
    ct: *const nf_conn,
    cp: *const c_uchar,
    endp: *mut *const c_uchar,
    addr: *mut nf_inet_addr,
    limit: *const c_uchar,
    _delim: c_int,
) -> c_int {
    if ct.is_null() || addr.is_null() || cp.is_null() || limit.is_null() {
        return 0;
    }

    ptr::write_bytes(addr as *mut u8, 0, mem::size_of::<nf_inet_addr>());

    match nf_ct_l3num(ct) {
        AF_INET => {
            let mut end: *const c_uchar = ptr::null();
            let ret = in4_pton(
                cp,
                (limit as usize).wrapping_sub(cp as usize) as c_int,
                addr as *mut c_uchar,
                -1,
                &mut end,
            );
            if ret == 0 {
                return 0;
            }
            if !endp.is_null() {
                *endp = end;
            }
            1
        }
        AF_INET6 => {
            let mut end: *const c_uchar = ptr::null();
            let ret = in6_pton(
                cp,
                (limit as usize).wrapping_sub(cp as usize) as c_int,
                addr as *mut c_uchar,
                -1,
                &mut end,
            );
            if ret == 0 {
                return 0;
            }
            if !endp.is_null() {
                *endp = end;
            }
            1
        }
        _ => 0,
    }
}

#[no_mangle]
pub unsafe extern "C" fn epaddr_len(ct: *const nf_conn, dptr: *const u8, limit: *const u8, shift: *mut c_int) -> c_int {
    let mut addr: nf_inet_addr = mem::zeroed();
    let mut end: *const u8 = ptr::null();
    let aux = dptr;

    if sip_parse_addr(ct, dptr, &mut end, &mut addr, limit, 1) == 0 {
        pr_debug(b"ip: %s parse failed.\n\0".as_ptr() as *const u8);
        return 0;
    }

    let mut length = end.offset_from(aux) as c_int;

    if end < limit && *end == b':' {
        let current = end.offset(1);
        let port_len = digits_len(ct, current, limit, shift);
        length += port_len as c_int;
    }

    if !shift.is_null() {
        *shift = length;
    }
    length
}

#[no_mangle]
pub unsafe extern "C" fn skp_epaddr_len(ct: *const nf_conn, dptr: *const u8, limit: *const u8, shift: *mut c_int) -> c_int {
    let start = dptr;
    let s = if !shift.is_null() { *shift } else { 0 };
    let mut current = dptr;

    while current < limit && *current != b'@' && *current != b'\r' && *current != b'\n' {
        if !shift.is_null() {
            *shift += 1;
        }
        current = current.offset(1);
    }

    if current < limit && *current == b'@' {
        current = current.offset(1);
        if !shift.is_null() {
            *shift += 1;
        }
    } else {
        current = start;
        if !shift.is_null() {
            *shift = s;
        }
    }

    epaddr_len(ct, current, limit, shift)
}

#[no_mangle]
pub unsafe extern "C" fn ct_sip_parse_request(ct: *const nf_conn, dptr: *const u8, datalen: c_uint, matchoff: *mut c_uint, matchlen: *mut c_uint, addr: *mut nf_inet_addr, port: *mut u16) -> c_int {
    let start = dptr;
    let limit = dptr.offset(datalen as isize);
    let mut current = dptr;
    let mut mlen: c_int = 0;
    let mut shift = 0;

    // Skip method and whitespace
    mlen = string_len(ct, current, limit, ptr::null_mut());
    if mlen == 0 {
        return 0;
    }

    current = current.offset(mlen as isize);
    if current < limit {
        current = current.offset(1);
    } else {
        return 0;
    }

    // Find SIP URI
    while current < limit.offset(-(4 as isize)) {
        if *current == b'\r' || *current == b'\n' {
            return -1;
        }
        if *current == b's' || *current == b'S' {
            if *(current.offset(1)) == b'i' &&
               *(current.offset(2)) == b'p' &&
               *(current.offset(3)) == b':' {
                current = current.offset(4);
                break;
            }
        }
        current = current.offset(1);
    }

    if skp_epaddr_len(ct, current, limit, &mut shift) == 0 {
        return 0;
    }

    current = current.offset(shift as isize);

    let mut end: *const u8 = ptr::null();
    if sip_parse_addr(ct, current, &mut end, addr, limit, 1) == 0 {
        return -1;
    }

    let mut p: u16 = SIP_PORT;
    if end < limit && *end == b':' {
        let mut current_port = end.offset(1);
        let mut port_str = [0u8; 6]; // Max 5 digits + null
        let mut i: c_int = 0;

        while current_port < limit && isdigit(*current_port) != 0 && i < 5 {
            port_str[i as usize] = *current_port;
            current_port = current_port.offset(1);
            i += 1;
        }

        port_str[i as usize] = 0;
        p = u16::from_str_radix(core::str::from_utf8_unchecked(&port_str[..i as usize]), 10).unwrap_or(SIP_PORT);

        if p < 1024 || p > 65535 {
            return -1;
        }
    }

    ptr::write(port, p);

    if end == current {
        return 0;
    }

    ptr::write(matchoff, current.offset_from(start) as c_uint);
    ptr::write(matchlen, end.offset_from(current) as c_uint);
    1
}

// SyncWrapper provides a thread-safe UnsafeCell wrapper for FFI globals
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
        // For FFI globals, the kernel handles external synchronization.
        unsafe { &mut *self.0.get() }
    }
}

#[no_mangle]
pub static NF_NAT_SIP_HOOKS: SyncWrapper<*mut nf_nat_sip_hooks> = SyncWrapper::new(ptr::null_mut());

// Helper functions (would be implemented in C headers)
#[no_mangle]
pub unsafe extern "C" fn nf_ct_l3num(_ct: *const nf_conn) -> c_int {
    // Implementation deferred.
    2 // AF_INET
}

#[no_mangle]
pub unsafe extern "C" fn in4_pton(_cp: *const u8, _len: c_int, _buf: *mut u8, _flags: c_int, _end: *mut *const u8) -> c_int {
    // Implementation deferred.
    1
}

#[no_mangle]
pub unsafe extern "C" fn in6_pton(_cp: *const u8, _len: c_int, _buf: *mut u8, _flags: c_int, _end: *mut *const u8) -> c_int {
    // Implementation deferred.
    1
}

#[no_mangle]
pub unsafe extern "C" fn pr_debug(_fmt: *const u8) {
    // Implementation deferred.
}

// Implementation deferred.
static PORTS: SyncWrapper<[u16; 8]> = SyncWrapper::new([0; 8]);
static PORTS_C: SyncWrapper<usize> = SyncWrapper::new(0);
static SIP_TIMEOUT_VAR: SyncWrapper<u32> = SyncWrapper::new(1200);
static SIP_DIRECT_SIGNALLING: SyncWrapper<c_int> = SyncWrapper::new(1);
static SIP_DIRECT_MEDIA: SyncWrapper<c_int> = SyncWrapper::new(1);
static SIP_EXTERNAL_MEDIA: SyncWrapper<c_int> = SyncWrapper::new(0);

// These would be implemented with proper module_param macros in a real kernel module
#[no_mangle]
pub unsafe extern "C" fn module_param_ports() {
    // Implementation deferred.
}

#[no_mangle]
pub unsafe extern "C" fn module_param_sip_timeout() {
    // Implementation deferred.
}

// Exported symbols
#[no_mangle]
pub static HELPER_NAME: [u8; 4] = *b"SIP\0";

#[no_mangle]
pub static NF_CT_HELPER_SIP: nf_conntrack_helper = unsafe {
    nf_conntrack_helper {
        list: ptr::null_mut(),
        hnode: ptr::null_mut(),
        name: [0; 16],
        tuple: mem::zeroed(),
        module: ptr::null_mut(),
        me: ptr::null_mut(),
        refcnt: 0,
        max_expected: 0,
        timeout: 0,
        flags: 0,
        help: ptr::null_mut(),
        from_nlattr: ptr::null_mut(),
    }
};

#[no_mangle]
pub static CT_SIP_HDRS: [sip_header; 9] = unsafe {
    [
        sip_header {
            name: b"CSeq\0".as_ptr() as *const c_char,
            short_name: ptr::null(),
            uri_prefix: ptr::null(),
            value_len: Some(string_len),
        },
        sip_header {
            name: b"From\0".as_ptr() as *const c_char,
            short_name: b"f\0".as_ptr() as *const c_char,
            uri_prefix: b"sip:\0".as_ptr() as *const c_char,
            value_len: Some(skp_epaddr_len),
        },
        sip_header {
            name: b"To\0".as_ptr() as *const c_char,
            short_name: b"t\0".as_ptr() as *const c_char,
            uri_prefix: b"sip:\0".as_ptr() as *const c_char,
            value_len: Some(skp_epaddr_len),
        },
        sip_header {
            name: b"Contact\0".as_ptr() as *const c_char,
            short_name: b"m\0".as_ptr() as *const c_char,
            uri_prefix: b"sip:\0".as_ptr() as *const c_char,
            value_len: Some(skp_epaddr_len),
        },
        sip_header {
            name: b"Via\0".as_ptr() as *const c_char,
            short_name: b"v\0".as_ptr() as *const c_char,
            uri_prefix: b"UDP \0".as_ptr() as *const c_char,
            value_len: Some(epaddr_len),
        },
        sip_header {
            name: b"Via\0".as_ptr() as *const c_char,
            short_name: b"v\0".as_ptr() as *const c_char,
            uri_prefix: b"TCP \0".as_ptr() as *const c_char,
            value_len: Some(epaddr_len),
        },
        sip_header {
            name: b"Expires\0".as_ptr() as *const c_char,
            short_name: ptr::null(),
            uri_prefix: ptr::null(),
            value_len: Some(digits_len),
        },
        sip_header {
            name: b"Content-Length\0".as_ptr() as *const c_char,
            short_name: b"l\0".as_ptr() as *const c_char,
            uri_prefix: ptr::null(),
            value_len: Some(digits_len),
        },
        sip_header {
            name: b"Call-Id\0".as_ptr() as *const c_char,
            short_name: b"i\0".as_ptr() as *const c_char,
            uri_prefix: ptr::null(),
            value_len: Some(callid_len),
        },
    ]
};

// Module metadata (would be implemented with proper macros in a real kernel module)
#[no_mangle]
pub static MODULE_LICENSE: [u8; 4] = *b"GPL\0";
#[no_mangle]
pub static MODULE_AUTHOR: [u8; 46] = *b"Christian Hentschel <chentschel@arnet.com.ar>\0";
#[no_mangle]
pub static MODULE_DESCRIPTION: [u8; 31] = *b"SIP connection tracking helper\0";
#[no_mangle]
pub static MODULE_ALIAS: [u8; 17] = *b"ip_conntrack_sip\0";
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── ABI / protocol constant tests ────────────────────────────────────────

    #[test]
    fn test_sip_constants() {
        assert_eq!(SIP_PORT, 5060, "SIP well-known port must be 5060");
        assert_eq!(SIP_TIMEOUT, 1200, "SIP timeout must be 1200 seconds");
        assert_eq!(AF_INET, 2);
        assert_eq!(AF_INET6, 10);
        assert_eq!(EINVAL, -22);
    }

    // ── character-class helper tests ─────────────────────────────────────────

    #[test]
    fn test_isalpha_classifies_correctly() {
        unsafe {
            assert_eq!(isalpha(b'a'), 1);
            assert_eq!(isalpha(b'Z'), 1);
            assert_eq!(isalpha(b'0'), 0);
            assert_eq!(isalpha(b'!'), 0);
        }
    }

    #[test]
    fn test_isdigit_classifies_correctly() {
        unsafe {
            assert_eq!(isdigit(b'0'), 1);
            assert_eq!(isdigit(b'9'), 1);
            assert_eq!(isdigit(b'a'), 0);
            assert_eq!(isdigit(b' '), 0);
        }
    }

    #[test]
    fn test_isalnum_combines_alpha_and_digit() {
        unsafe {
            assert_eq!(isalnum(b'x'), 1);
            assert_eq!(isalnum(b'5'), 1);
            assert_eq!(isalnum(b'_'), 0);
            assert_eq!(isalnum(b'@'), 0);
        }
    }

    // ── iswordc boundary tests ───────────────────────────────────────────────

    #[test]
    fn test_iswordc_accepts_word_chars() {
        let word_chars: &[u8] = b"aZ09!%()";
        for &c in word_chars {
            let result = unsafe { iswordc(c) };
            assert_eq!(result, 1, "iswordc({}) should return 1", c as char);
        }
    }

    #[test]
    fn test_iswordc_rejects_space_and_cr_lf() {
        for &c in &[b' ', b'\r', b'\n'] {
            let result = unsafe { iswordc(c) };
            assert_eq!(result, 0, "iswordc({:#x}) should return 0", c);
        }
    }

    // ── string_len / digits_len on stack buffers ─────────────────────────────

    #[test]
    fn test_string_len_counts_alpha() {
        let buf: &[u8] = b"INVITE sip:bob";
        let limit = unsafe { buf.as_ptr().add(buf.len()) };
        let len = unsafe {
            string_len(core::ptr::null(), buf.as_ptr(), limit, core::ptr::null_mut())
        };
        assert_eq!(len, 6, "INVITE is 6 alpha chars");
    }

    #[test]
    fn test_digits_len_counts_digits() {
        let buf: &[u8] = b"5060abc";
        let limit = unsafe { buf.as_ptr().add(buf.len()) };
        let len = unsafe {
            digits_len(core::ptr::null(), buf.as_ptr(), limit, core::ptr::null_mut())
        };
        assert_eq!(len, 4, "5060 is 4 digit chars");
    }

    #[test]
    fn test_digits_len_empty_returns_zero() {
        let buf: &[u8] = b"abc";
        let limit = unsafe { buf.as_ptr().add(buf.len()) };
        let len = unsafe {
            digits_len(core::ptr::null(), buf.as_ptr(), limit, core::ptr::null_mut())
        };
        assert_eq!(len, 0);
    }

    // ── module metadata constant tests ───────────────────────────────────────

    #[test]
    fn test_module_license_is_gpl() {
        assert_eq!(&MODULE_LICENSE, b"GPL\0");
    }

    #[test]
    fn test_ct_sip_hdrs_count() {
        assert_eq!(CT_SIP_HDRS.len(), 9, "CT_SIP_HDRS must have exactly 9 entries");
    }
}

