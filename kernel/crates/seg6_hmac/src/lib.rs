#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]

use core::ffi::c_void;
use core::ptr;
use core::panic::PanicInfo;
use kernel_types::*;

pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOENT: c_int = -2;
pub const EMSGSIZE: c_int = -92;

pub const SEG6_HMAC_RING_SIZE: usize = 256;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_sr_hdr {
    pub hdrlen: u8,
    pub flags: u8,
    pub first_segment: u8,
    pub segments: [in6_addr; 1],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sr6_tlv_hmac {
    pub tlvhdr: [u8; 2],
    pub hmackeyid: u32,
    pub hmac: [u8; 32],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct seg6_hmac_info {
    pub hmackeyid: u32,
    pub alg_id: u8,
    pub secret: *const u8,
    pub slen: u32,
    pub node: [u8; 1],
    pub rcu: [u8; 1],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct seg6_hmac_algo {
    pub alg_id: u8,
    pub name: *const u8,
    pub tfms: *mut c_void,
    pub shashs: *mut c_void,
}

unsafe impl Sync for seg6_hmac_algo {}

#[repr(C)]
pub struct shash_desc { pub tfm: *mut c_void }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct rhashtable_params {
    pub head_offset: size_t,
    pub key_offset: size_t,
    pub key_len: size_t,
    pub automatic_shrinking: u8,
    pub obj_cmpfn: extern "C" fn(arg: *mut c_void, obj: *const c_void) -> c_int,
}

unsafe extern "C" {
    fn sr_has_hmac(srh: *const u8) -> bool;
    fn this_cpu_ptr(ptr: *mut c_void) -> *mut c_void;
    fn crypto_shash_digestsize(tfm: *mut c_void) -> c_int;
    fn crypto_shash_setkey(tfm: *mut c_void, key: *const u8, keylen: u32) -> c_int;
    fn crypto_shash_digest(
        desc: *mut shash_desc,
        data: *const c_void,
        len: size_t,
        out: *mut u8,
    ) -> c_int;
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}

#[no_mangle]
pub unsafe extern "C" fn seg6_hmac_cmpfn(arg: *mut c_void, obj: *const c_void) -> c_int {
    let hinfo = obj as *const seg6_hmac_info;
    let key = arg as *const u32;

    if (*hinfo).hmackeyid != *key {
        return 1;
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn seg6_hinfo_release(_hinfo: *mut seg6_hmac_info) {}

#[no_mangle]
pub unsafe extern "C" fn seg6_free_hi(ptr: *mut c_void, _arg: *mut c_void) {
    let hinfo = ptr as *mut seg6_hmac_info;
    seg6_hinfo_release(hinfo);
}

#[no_mangle]
pub unsafe extern "C" fn seg6_get_tlv_hmac(srh: *const ipv6_sr_hdr) -> *mut sr6_tlv_hmac {
    let srh_u8 = srh as *const u8;
    let hdrlen = (*srh).hdrlen;
    let first_segment = (*srh).first_segment;

    if hdrlen < ((first_segment.wrapping_add(1)).wrapping_mul(2).wrapping_add(5)) {
        return ptr::null_mut();
    }

    if !sr_has_hmac(srh_u8) {
        return ptr::null_mut();
    }

    let off = (((hdrlen as usize) + 1) << 3).wrapping_sub(40);
    let tlv = srh_u8.add(off) as *mut sr6_tlv_hmac;

    if (*tlv).tlvhdr[0] != 0x01 || (*tlv).tlvhdr[1] != 0x22 {
        return ptr::null_mut();
    }

    tlv
}

#[no_mangle]
pub unsafe extern "C" fn __hmac_get_algo(alg_id: u8) -> *mut seg6_hmac_algo {
    static HMAC_ALGOS: [seg6_hmac_algo; 2] = [
        seg6_hmac_algo {
            alg_id: 1,
            name: b"hmac(sha1)\0".as_ptr(),
            tfms: ptr::null_mut(),
            shashs: ptr::null_mut(),
        },
        seg6_hmac_algo {
            alg_id: 2,
            name: b"hmac(sha256)\0".as_ptr(),
            tfms: ptr::null_mut(),
            shashs: ptr::null_mut(),
        },
    ];

    let mut i = 0usize;
    while i < HMAC_ALGOS.len() {
        if HMAC_ALGOS[i].alg_id == alg_id {
            return (&HMAC_ALGOS[i] as *const seg6_hmac_algo) as *mut seg6_hmac_algo;
        }
        i += 1;
    }
    ptr::null_mut()
}

#[no_mangle]
pub unsafe extern "C" fn __do_hmac(
    hinfo: *const seg6_hmac_info,
    text: *const c_void,
    psize: u8,
    output: *mut u8,
    outlen: c_int,
) -> c_int {
    let algo = __hmac_get_algo((*hinfo).alg_id);
    if algo.is_null() {
        return ENOENT;
    }

    let tfm = this_cpu_ptr((*algo).tfms);
    if tfm.is_null() {
        return ENOENT;
    }

    let dgsize = crypto_shash_digestsize(tfm);
    if dgsize > outlen {
        return ENOMEM;
    }

    let ret = crypto_shash_setkey(tfm, (*hinfo).secret, (*hinfo).slen);
    if ret < 0 {
        return ret;
    }

    let shash_ptr = this_cpu_ptr((*algo).shashs) as *mut shash_desc;
    if shash_ptr.is_null() {
        return ENOENT;
    }
    (*shash_ptr).tfm = tfm;

    let ret2 = crypto_shash_digest(shash_ptr, text, psize as size_t, output);
    if ret2 < 0 {
        return ret2;
    }

    dgsize
}

#[no_mangle]
pub unsafe extern "C" fn seg6_hmac_compute(
    hinfo: *const seg6_hmac_info,
    _hdr: *const ipv6_sr_hdr,
    _saddr: *const in6_addr,
    output: *mut u8,
) -> c_int {
    if hinfo.is_null() || output.is_null() {
        return EINVAL;
    }

    let mut tmp_out = [0u8; 32];
    let _hmackeyid_be = (*hinfo).hmackeyid.to_be();

    let ret = __do_hmac(hinfo, ptr::null(), 0, tmp_out.as_mut_ptr(), tmp_out.len() as c_int);
    if ret < 0 {
        return ret;
    }

    let out_sz = ret as usize;
    if out_sz > tmp_out.len() {
        return EMSGSIZE;
    }

    ptr::copy_nonoverlapping(tmp_out.as_ptr(), output, out_sz);
    ret
}
