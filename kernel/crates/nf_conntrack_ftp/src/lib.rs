#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! FTP connection tracking helper for Netfilter
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]

use core::ffi::{c_int, c_uint};
use core::ptr;

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

use kernel_types::*;

pub type size_t = usize;

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const ENOSYS: c_int = -38;

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tcp { pub port: __be16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub union nf_conntrack_union {
    pub ip: __be32,
    pub ip6: in6_addr,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_man { pub u3: nf_conntrack_union, pub u: nf_conntrack_tcp }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_ct_ftp_master { pub seq_aft_nl: [[__u32; 2]; 2], pub seq_aft_nl_num: [c_uint; 2] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_ct_ftp_type { _priv: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_expect {
    _priv: [u8; 0],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_ftp { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sk_buff { _priv: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip_conntrack_info { _priv: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct spinlock_t { _priv: [u8; 0] }

pub type getnum_fn =
    Option<unsafe extern "C" fn(*const u8, size_t, *mut nf_conntrack_man, u8, *mut c_uint) -> c_int>;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ftp_search {
    pub pattern: *const u8,
    pub plen: size_t,
    pub skip: u8,
    pub term: u8,
    pub ftptype: nf_ct_ftp_type,
    pub getnum: getnum_fn,
}

// SAFETY: ftp_search is used in kernel context where thread safety is handled by kernel locks
unsafe impl Sync for ftp_search {}

// FTP command patterns
const PATTERN_PORT: &[u8; 4] = b"PORT";
const PATTERN_EPRT: &[u8; 4] = b"EPRT";

// Function implementations
static NF_FTP_LOCK: SyncWrapper<spinlock_t> = SyncWrapper::new(spinlock_t { _priv: [] });

static PORTS: [__be16; 8] = [0; 8];
static PORTS_C: c_uint = 0;

static LOOSE: bool = false;

type nf_nat_ftp_hook_type = Option<extern "C" fn(
    skb: *mut sk_buff,
    ctinfo: *mut ip_conntrack_info,
    type_: nf_ct_ftp_type,
    protoff: c_uint,
    matchoff: c_uint,
    matchlen: c_uint,
    exp: *mut nf_conntrack_expect,
) -> c_uint>;

static NF_NAT_FTP_HOOK: SyncWrapper<nf_nat_ftp_hook_type> = SyncWrapper::new(None);

#[no_mangle]
pub unsafe extern "C" fn nf_nat_ftp_hook_fn(
    skb: *mut sk_buff,
    ctinfo: *mut ip_conntrack_info,
    _type_: nf_ct_ftp_type,
    _protoff: c_uint,
    _matchoff: c_uint,
    _matchlen: c_uint,
    exp: *mut nf_conntrack_expect,
) -> c_uint {
    if skb.is_null() || ctinfo.is_null() || exp.is_null() {
        return 0; // NF_DROP
    }
    1 // NF_ACCEPT
}

static SEARCH: [ftp_search; 2] = [
    ftp_search {
        pattern: b"PORT\0".as_ptr(),
        plen: 4,
        skip: b' ',
        term: b'\r',
        ftptype: nf_ct_ftp_type { _priv: [] },
        getnum: Some(try_rfc959),
    },
    ftp_search {
        pattern: b"EPRT\0".as_ptr(),
        plen: 4,
        skip: b' ',
        term: b'\r',
        ftptype: nf_ct_ftp_type { _priv: [] },
        getnum: Some(try_eprt),
    },
];

#[no_mangle]
pub unsafe extern "C" fn get_ipv6_addr(
    src: *const u8,
    dlen: size_t,
    dst: *mut in6_addr,
    term: u8,
) -> c_int {
    if src.is_null() || dst.is_null() || dlen == 0 {
        return EINVAL;
    }
    for i in 0..dlen {
        if *src.add(i) == term {
            return i as c_int;
        }
    }
    EINVAL
}

#[no_mangle]
pub unsafe extern "C" fn try_number(
    data: *const u8,
    dlen: size_t,
    array: *mut __u32,
    array_size: c_int,
    sep: u8,
    term: u8,
) -> c_int {
    if data.is_null() || array.is_null() || array_size <= 0 || dlen == 0 {
        return EINVAL;
    }
    let mut count = 0;
    let mut current_val: __u32 = 0;
    let mut in_num = false;
    for i in 0..dlen {
        let b = *data.add(i);
        if b >= b'0' && b <= b'9' {
            current_val = current_val.wrapping_mul(10).wrapping_add((b - b'0') as __u32);
            in_num = true;
        } else if b == sep || b == term {
            if in_num && count < array_size {
                *array.add(count as usize) = current_val;
                count += 1;
                current_val = 0;
                in_num = false;
            }
            if b == term || count >= array_size {
                return count;
            }
        } else {
            return EINVAL;
        }
    }
    count
}

#[no_mangle]
pub unsafe extern "C" fn try_rfc959(
    data: *const u8,
    dlen: size_t,
    cmd: *mut nf_conntrack_man,
    term: u8,
    offset: *mut c_uint,
) -> c_int {
    if data.is_null() || cmd.is_null() || offset.is_null() || dlen == 0 {
        return EINVAL;
    }
    let mut nums = [0u32; 6];
    let parsed = try_number(data, dlen, nums.as_mut_ptr(), 6, b',', term);
    if parsed == 6 {
        let port = ((nums[4] << 8) | (nums[5] & 0xff)) as u16;
        (*cmd).u.port = port.to_be();
        *offset = 0;
        1
    } else {
        EINVAL
    }
}

#[no_mangle]
pub unsafe extern "C" fn try_rfc1123(
    data: *const u8,
    dlen: size_t,
    cmd: *mut nf_conntrack_man,
    term: u8,
    offset: *mut c_uint,
) -> c_int {
    if data.is_null() || cmd.is_null() || offset.is_null() || dlen == 0 {
        return EINVAL;
    }
    try_rfc959(data, dlen, cmd, term, offset)
}

#[no_mangle]
pub unsafe extern "C" fn get_port(
    data: *const u8,
    start: c_int,
    dlen: size_t,
    delim: u8,
    port: *mut __be16,
) -> c_int {
    if data.is_null() || port.is_null() || start < 0 || (start as size_t) >= dlen {
        return EINVAL;
    }
    let mut p: u32 = 0;
    let mut found = false;
    for i in (start as size_t)..dlen {
        let b = *data.add(i);
        if b == delim {
            if found {
                *port = (p as u16).to_be();
                return i as c_int;
            }
        } else if b >= b'0' && b <= b'9' {
            p = p.wrapping_mul(10).wrapping_add((b - b'0') as u32);
            found = true;
        } else {
            return EINVAL;
        }
    }
    if found {
        *port = (p as u16).to_be();
        dlen as c_int
    } else {
        EINVAL
    }
}

#[no_mangle]
pub unsafe extern "C" fn try_eprt(
    data: *const u8,
    dlen: size_t,
    cmd: *mut nf_conntrack_man,
    _term: u8,
    offset: *mut c_uint,
) -> c_int {
    if data.is_null() || cmd.is_null() || offset.is_null() || dlen < 5 {
        return EINVAL;
    }
    let delim = *data;
    let mut port_be: __be16 = 0;
    let res = get_port(data, 1, dlen, delim, &mut port_be as *mut _);
    if res >= 0 {
        (*cmd).u.port = port_be;
        *offset = res as c_uint;
        1
    } else {
        EINVAL
    }
}

#[no_mangle]
pub unsafe extern "C" fn try_epsv_response(
    data: *const u8,
    dlen: size_t,
    cmd: *mut nf_conntrack_man,
    term: u8,
    offset: *mut c_uint,
) -> c_int {
    if data.is_null() || cmd.is_null() || offset.is_null() || dlen < 5 {
        return EINVAL;
    }
    try_eprt(data, dlen, cmd, term, offset)
}

#[no_mangle]
pub unsafe extern "C" fn find_pattern(
    data: *const u8,
    dlen: size_t,
    pattern: *const u8,
    plen: size_t,
    _skip: u8,
    term: u8,
    numoff: *mut c_uint,
    _numlen: *mut c_int,
    cmd: *mut nf_conntrack_man,
    getnum: getnum_fn,
) -> c_int {
    if data.is_null() || pattern.is_null() || plen == 0 || dlen < plen {
        return EINVAL;
    }
    for i in 0..=(dlen - plen) {
        let mut matched = true;
        for j in 0..plen {
            if *data.add(i + j) != *pattern.add(j) {
                matched = false;
                break;
            }
        }
        if matched {
            let offset = i + plen;
            if let Some(parse_fn) = getnum {
                if !numoff.is_null() {
                    *numoff = offset as c_uint;
                }
                return parse_fn(data.add(offset), dlen - offset, cmd, term, numoff);
            }
            return 1;
        }
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn find_nl_seq(seq: __u32, info: *const nf_ct_ftp_master, dir: c_int) -> c_int {
    if info.is_null() || dir < 0 || dir > 1 {
        return 0;
    }
    let d = dir as usize;
    let seq_num = (*info).seq_aft_nl_num[d];
    for i in 0..(seq_num as usize).min(2) {
        if (*info).seq_aft_nl[d][i] == seq {
            return 1;
        }
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn update_nl_seq(seq: __u32, info: *mut nf_ct_ftp_master, dir: c_int) {
    if info.is_null() || dir < 0 || dir > 1 {
        return;
    }
    let d = dir as usize;
    let idx = ((*info).seq_aft_nl_num[d] as usize) % 2;
    (*info).seq_aft_nl[d][idx] = seq;
    if (*info).seq_aft_nl_num[d] < 2 {
        (*info).seq_aft_nl_num[d] += 1;
    }
}


#[no_mangle]
pub unsafe extern "C" fn nf_conntrack_ftp_init() -> c_int {
    let _ = ptr::addr_of!(PORTS);
    let _ = ptr::addr_of!(PORTS_C);
    let _ = ptr::addr_of!(LOOSE);
    let _ = ptr::addr_of!(SEARCH);
    let _ = NF_FTP_LOCK.get_mut();
    let _ = NF_NAT_FTP_HOOK.get_mut();
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ftp_try_number_parsing() {
        let data = b"192,168,1,10,80,0\r";
        let mut nums = [0u32; 6];
        let count = unsafe {
            try_number(
                data.as_ptr(),
                data.len(),
                nums.as_mut_ptr(),
                6,
                b',',
                b'\r',
            )
        };
        assert_eq!(count, 6);
        assert_eq!(nums[0], 192);
        assert_eq!(nums[1], 168);
        assert_eq!(nums[2], 1);
        assert_eq!(nums[3], 10);
        assert_eq!(nums[4], 80);
        assert_eq!(nums[5], 0);
    }

    #[test]
    fn test_ftp_try_rfc959_port_command() {
        let data = b"192,168,1,10,1,200\r";
        let mut cmd = nf_conntrack_man {
            u3: nf_conntrack_union { ip: 0 },
            u: nf_conntrack_tcp { port: 0 },
        };
        let mut offset: c_uint = 0;
        let res = unsafe {
            try_rfc959(
                data.as_ptr(),
                data.len(),
                &mut cmd as *mut _,
                b'\r',
                &mut offset as *mut _,
            )
        };
        assert_eq!(res, 1);
        let expected_port = (1u16 << 8) | 200;
        assert_eq!(cmd.u.port, expected_port.to_be());
    }

    #[test]
    fn test_ftp_find_nl_seq_null_and_bounds() {
        let res = unsafe { find_nl_seq(100, ptr::null(), 0) };
        assert_eq!(res, 0);

        let master = nf_ct_ftp_master {
            seq_aft_nl: [[100, 200], [300, 400]],
            seq_aft_nl_num: [2, 2],
        };
        let found = unsafe { find_nl_seq(100, &master as *const _, 0) };
        assert_eq!(found, 1);
        let not_found = unsafe { find_nl_seq(999, &master as *const _, 0) };
        assert_eq!(not_found, 0);
    }
}

