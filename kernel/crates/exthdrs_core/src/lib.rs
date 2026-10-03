#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(clippy::all)]

use kernel_types::*;
use core::mem;
use core::ptr;

pub const NEXTHDR_HOP: u8 = 0;
pub const NEXTHDR_ROUTING: u8 = 43;
pub const NEXTHDR_FRAGMENT: u8 = 44;
pub const NEXTHDR_AUTH: u8 = 51;
pub const NEXTHDR_NONE: u8 = 59;
pub const NEXTHDR_DEST: u8 = 60;

pub const EBADMSG: c_int = -74; pub const ENOENT: c_int = -2; pub const ENOMEM: c_int = -12;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_opt_hdr { pub nexthdr: u8, pub hdrlen: u8 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_rt_hdr {
    pub nexthdr: u8,
    pub hdrlen: u8,
    pub type_: u8,
    pub segments_left: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct frag_hdr {
    pub nexthdr: u8,
    pub reserved: u8,
    pub frag_off: u16,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6hdr {
    pub priority_version: u32,
    pub payload_len: u16,
    pub nexthdr: u8,
    pub hop_limit: u8,
    pub saddr: [u8; 16],
    pub daddr: [u8; 16],
}

#[unsafe(no_mangle)]
pub extern "C" fn rust_eh_personality() {}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ipv6_ext_hdr(nexthdr: u8) -> bool {
    matches!(nexthdr, NEXTHDR_HOP | NEXTHDR_ROUTING | NEXTHDR_FRAGMENT | NEXTHDR_AUTH | NEXTHDR_NONE | NEXTHDR_DEST)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ipv6_authlen(hp: *const ipv6_opt_hdr) -> c_int {
    let hdrlen = (*hp).hdrlen as c_int;
    (hdrlen + 2) * 4
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ipv6_optlen(hp: *const ipv6_opt_hdr) -> c_int {
    let hdrlen = (*hp).hdrlen as c_int;
    (hdrlen + 1) << 3
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ipv6_skip_exthdr(
    skb: *const c_void,
    mut start: c_int,
    nexthdrp: *mut u8,
    frag_offp: *mut u16,
) -> c_int {
    let mut nexthdr = *nexthdrp;
    *frag_offp = 0;

    while ipv6_ext_hdr(nexthdr) {
        let mut _hdr: ipv6_opt_hdr = mem::zeroed();
        let hp = skb_header_pointer(skb, start, mem::size_of_val(&_hdr) as _, &mut _hdr as *mut _ as *mut c_void);

        if hp.is_null() {
            return -1;
        }

        if nexthdr == NEXTHDR_NONE {
            return -1;
        }

        let hp = hp.cast::<ipv6_opt_hdr>();
        let hdrlen: c_int;

        if nexthdr == NEXTHDR_FRAGMENT {
            let mut frag: frag_hdr = mem::zeroed();
            let fhp = skb_header_pointer(
                skb,
                start + mem::size_of::<u8>() as c_int * 2,
                mem::size_of_val(&frag) as _,
                &mut frag as *mut _ as *mut c_void,
            ) as *mut frag_hdr;

            if fhp.is_null() {
                return -1;
            }

            *frag_offp = (*fhp).frag_off;

            if ((*frag_offp as u32) & 0xFFF8) != 0 {
                break;
            }
            hdrlen = 8;
        } else if nexthdr == NEXTHDR_AUTH {
            hdrlen = ipv6_authlen(hp);
        } else {
            hdrlen = ipv6_optlen(hp);
        }

        nexthdr = (*hp).nexthdr;
        start += hdrlen;
    }

    *nexthdrp = nexthdr;
    start
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ipv6_find_tlv(skb: *const c_void, offset: c_int, type_: c_int) -> c_int {
    let nh = skb_network_header(skb);
    if nh.is_null() {
        return -1;
    }

    let tail = skb_tail_pointer(skb);
    if tail.is_null() || (tail as usize) < (nh as usize) {
        return -1;
    }

    let packet_len = (tail as usize) - (nh as usize);
    let mut off = offset as usize;

    if off + 2 > packet_len {
        return -1;
    }

    let hdr = (nh as usize + off) as *const ipv6_opt_hdr;
    let hdr_bytes = (((*hdr).hdrlen as usize) + 1) << 3;

    if off + hdr_bytes > packet_len || hdr_bytes < 2 {
        return -1;
    }

    off += 2;
    let mut left = hdr_bytes - 2;

    while left > 0 {
        if off >= packet_len {
            return -1;
        }

        let opttype = ptr::read((nh as usize + off) as *const u8) as c_int;

        if opttype == type_ {
            return off as c_int;
        }

        let optlen: usize = if opttype == 0 {
            1
        } else {
            if off + 1 >= packet_len {
                return -1;
            }
            (ptr::read((nh as usize + off + 1) as *const u8) as usize) + 2
        };

        if optlen == 0 || optlen > left {
            return -1;
        }

        off += optlen;
        left -= optlen;
    }

    -1
}

/// Find specific header in IPv6 packet
///
/// # Safety
/// - `skb` must be a valid pointer to sk_buff
/// - `offset` must be a valid pointer to unsigned int
///
/// # Returns
/// Header type or -1 on error
#[no_mangle]
pub unsafe extern "C" fn ipv6_find_hdr(
    skb: *const c_void,
    offset: *mut c_int,
    target: c_int,
    fragoff: *mut c_int,
    flags: *mut c_int,
) -> c_int {
    let mut start = skb_network_offset(skb) as c_int + mem::size_of::<ipv6hdr>() as c_int;
    let mut nexthdr = (*ipv6_hdr(skb)).nexthdr;
    let mut found;

    if !fragoff.is_null() {
        *fragoff = 0;
    }

    if !offset.is_null() && *offset != 0 {
        let mut _ip6: ipv6hdr = mem::zeroed();
        let ip6 = skb_header_pointer(skb, *offset, mem::size_of_val(&_ip6) as _, &mut _ip6 as *mut _ as *mut c_void)
            as *const ipv6hdr;

        if ip6.is_null() || ((*ip6).priority_version >> 4) != 6 {
            return EBADMSG;
        }

        start = *offset + mem::size_of::<ipv6hdr>() as c_int;
        nexthdr = (*ip6).nexthdr;
    }

    loop {
        let mut _hdr: ipv6_opt_hdr = mem::zeroed();
        let hp = skb_header_pointer(skb, start, mem::size_of_val(&_hdr) as _, &mut _hdr as *mut _ as *mut c_void)
            as *const ipv6_opt_hdr;

        if hp.is_null() {
            return EBADMSG;
        }

        found = (nexthdr == target as u8) as c_int;

        if !ipv6_ext_hdr(nexthdr) || nexthdr == NEXTHDR_NONE {
            if target < 0 || found != 0 {
                break;
            }
            return ENOENT;
        }

        if nexthdr == NEXTHDR_ROUTING {
            let mut _rh: ipv6_rt_hdr = mem::zeroed();
            let rh = skb_header_pointer(skb, start, mem::size_of_val(&_rh) as _, &mut _rh as *mut _ as *mut c_void)
                as *const ipv6_rt_hdr;

            if rh.is_null() {
                return EBADMSG;
            }

            if !flags.is_null() && (*flags & 1) != 0 && (*rh).segments_left == 0 {
                found = 0;
            }
        }

        if nexthdr == NEXTHDR_FRAGMENT {
            if !flags.is_null() {
                *flags |= 2;
            }

            let mut _frag_off: u16 = 0;
            let frag_off = skb_header_pointer(
                skb,
                start + mem::size_of::<u8>() as c_int * 2,
                mem::size_of_val(&_frag_off) as _,
                &mut _frag_off as *mut _ as *mut c_void,
            ) as *mut u16;

            if frag_off.is_null() {
                return EBADMSG;
            }

            let frag_off_val = (*frag_off as u32) & 0x7FF8;
            if frag_off_val != 0 {
                if target < 0 && (!ipv6_ext_hdr((*hp).nexthdr) || (*hp).nexthdr == NEXTHDR_NONE) {
                    if !fragoff.is_null() {
                        *fragoff = frag_off_val as c_int;
                    }
                    return (*hp).nexthdr as c_int;
                }

                if found == 0 {
                    return ENOENT;
                }

                if !fragoff.is_null() {
                    *fragoff = frag_off_val as c_int;
                }
                break;
            }
            let hdrlen = 8;
            if found == 0 {
                nexthdr = (*hp).nexthdr;
                start += hdrlen;
            }
        } else if nexthdr == NEXTHDR_AUTH {
            if !flags.is_null() && (*flags & 4) != 0 && target < 0 {
                break;
            }
            let hdrlen = ipv6_authlen(hp as *const _) as c_int;
            if found == 0 {
                nexthdr = (*hp).nexthdr;
                start += hdrlen;
            }
        } else {
            let hdrlen = ipv6_optlen(hp as *const _) as c_int;
            if found == 0 {
                nexthdr = (*hp).nexthdr;
                start += hdrlen;
            }
        }
    }

    if !offset.is_null() {
        *offset = start;
    }
    nexthdr as c_int
}

// Helper functions (assumed to exist in the kernel)
#[no_mangle]
pub unsafe extern "C" fn skb_network_header(skb: *const c_void) -> *const c_void {
    // Implementation would depend on sk_buff structure
    skb
}

#[no_mangle]
pub unsafe extern "C" fn skb_network_offset(_skb: *const c_void) -> c_int {
    let _ret = 0;
    _ret
}

#[no_mangle]
pub unsafe extern "C" fn skb_tail_pointer(skb: *const c_void) -> *const c_void {
    skb
}

#[no_mangle]
pub unsafe extern "C" fn skb_header_pointer(
    skb: *const c_void,
    offset: c_int,
    size: c_int,
    data: *mut c_void,
) -> *mut c_void {
    // SAFETY: Caller guarantees valid offset and size
    let ptr = (skb as usize + offset as usize) as *mut c_void;
    if ptr.is_null() {
        return ptr;
    }

    // SAFETY: Copy data from skb to buffer
    ptr::copy_nonoverlapping(ptr, data, size as usize);
    data
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_hdr(skb: *const c_void) -> *const ipv6hdr {
    skb as *const ipv6hdr
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_ipv6_ext_hdr() {
        assert!(super::ipv6_ext_hdr(super::NEXTHDR_HOP));
        assert!(super::ipv6_ext_hdr(super::NEXTHDR_ROUTING));
        assert!(super::ipv6_ext_hdr(super::NEXTHDR_FRAGMENT));
        assert!(super::ipv6_ext_hdr(super::NEXTHDR_AUTH));
        assert!(super::ipv6_ext_hdr(super::NEXTHDR_NONE));
        assert!(super::ipv6_ext_hdr(super::NEXTHDR_DEST));
        assert!(!super::ipv6_ext_hdr(100));
    }
}
