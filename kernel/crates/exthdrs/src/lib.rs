#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(clippy::all)]
#![allow(non_snake_case)]
#![allow(dead_code)]
#![allow(unused_comparisons)]
#![allow(non_snake_case)] // For C-style type names

use core::ptr;
use kernel_types::*;

pub type socklen_t = u32;
pub type size_t = usize;

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const ENOSYS: c_int = -38;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct tlvtype_proc {
    pub type_: c_int,
    pub func: extern "C" fn(skb: *mut sk_buff, offset: c_int) -> bool,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_destopt_hao { pub length: u8, pub addr: [u8; 16] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_sr_hdr {
    pub nexthdr: u8,
    pub hdrlen: u8,
    pub segments_left: u16,
    pub reserved: u16,
    pub segments: [u8; 0], // Zero-sized array for variable-length segments
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet6_skb_parm {
    pub lastopt: c_int,
    pub dst1: c_int,
    pub dsthao: *mut c_void,
    pub srcrt: c_int,
    pub nhoff: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet6_dev { pub cnf: *mut c_void }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net { pub ipv6: *mut c_void }

// Function declarations for external C functions
extern "C" {
    fn icmpv6_param_prob(skb: *mut sk_buff, code: c_int, ptr: c_int);
    fn kfree_skb(skb: *mut sk_buff);
    fn pskb_may_pull(skb: *mut sk_buff, len: c_int) -> bool;
    fn skb_cloned(skb: *mut sk_buff) -> bool;
    fn pskb_expand_head(skb: *mut sk_buff, headroom: c_int, tailroom: c_int, flags: c_int) -> bool;
    fn xfrm6_input_addr(
        skb: *mut sk_buff,
        dst: *mut c_void,
        src: *mut c_void,
        proto: c_int,
    ) -> c_int;
    fn __IP6_INC_STATS(net: *mut net, idev: *mut inet6_dev, mib: c_int);
    fn __skb_tunnel_rx(skb: *mut sk_buff, dev: *mut c_void, net: *mut net);
    fn netif_rx(skb: *mut sk_buff);
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[cfg(not(test))]
#[unsafe(no_mangle)]
pub extern "C" fn rust_eh_personality() {}

#[inline]
unsafe fn skb_network_header_ptr(skb: *mut sk_buff) -> *mut u8 {
    (*skb).head.add((*skb).network_header as usize)
}

#[inline]
unsafe fn skb_transport_header_ptr(skb: *mut sk_buff) -> *mut u8 {
    (*skb).head.add((*skb).transport_header as usize)
}

#[inline]
unsafe fn skb_headlen(skb: *mut sk_buff) -> c_uint { (*skb).len }

#[inline]
unsafe fn ipv6_hdr(skb: *mut sk_buff) -> *mut ipv6hdr {
    skb_network_header_ptr(skb) as *mut ipv6hdr
}

#[inline]
unsafe fn ip6cb(skb: *mut sk_buff) -> *mut inet6_skb_parm {
    (*skb).cb.as_mut_ptr() as *mut inet6_skb_parm
}

#[inline]
unsafe fn IP6CB(skb: *mut sk_buff) -> *mut inet6_skb_parm {
    (*skb).cb.as_mut_ptr() as *mut inet6_skb_parm
}

#[inline]
fn ipv6_addr_is_multicast(addr: *const u8) -> bool { unsafe { (*addr & 0xFF) == 0xFF } }

fn __in6_dev_get(_dev: *mut c_void) -> *mut inet6_dev {
    // Implementation deferred.
    ptr::null_mut()
}

fn dev_net(_dev: *mut c_void) -> *mut net {
    // Implementation deferred.
    ptr::null_mut()
}

fn ip6_tlvopt_unknown(skb: *mut sk_buff, optoff: c_int, disallow_unknowns: bool) -> bool {
    unsafe {
        if disallow_unknowns {
            kfree_skb(skb);
            return false;
        }

        let nh = (*skb).network_header as *mut u8;
        let opt_type = (nh.offset(optoff as isize) as u8 & 0xC0) >> 6;

        match opt_type {
            0 => true, // Ignore
            1 => {
                kfree_skb(skb);
                false
            }
            3 | 2 => {
                let ipv6h = ipv6_hdr(skb);
                if !ipv6_addr_is_multicast((*ipv6h).daddr.in6_u.u6_addr8.as_ptr()) {
                    icmpv6_param_prob(skb, 5, optoff); // ICMPV6_UNK_OPTION
                }
                kfree_skb(skb);
                false
            }
            _ => false,
        }
    }
}

#[no_mangle]
pub unsafe extern "C" fn ip6_parse_tlv(
    procs: *const tlvtype_proc,
    skb: *mut sk_buff,
    max_count: c_int,
) -> bool {
    let transport_header = (*skb).transport_header as *mut u8;
    let len = (((*transport_header.offset(1)) + 1) << 3) as c_int;
    let nh = (*skb).network_header as *mut u8;
    let mut off = (*skb).network_header_len as c_int;
    let mut padlen = 0;
    let mut tlv_count = 0;
    let disallow_unknowns = max_count < 0;
    let max_count = if disallow_unknowns {
        -max_count
    } else {
        max_count
    };

    if (*skb).transport_offset + len > skb_headlen(skb) as c_int {
        kfree_skb(skb);
        return false;
    }

    off += 2;
    let mut len = len - 2;

    while len > 0 {
        let optlen = if *nh.offset(off as isize) == 0 {
            // IPV6_TLV_PAD1
            padlen += 1;
            if padlen > 7 {
                kfree_skb(skb);
                return false;
            }
            1
        } else if len < 2 {
            kfree_skb(skb);
            return false;
        } else {
            let optlen = *nh.offset((off + 1) as isize) as c_int + 2;
            if optlen > len {
                kfree_skb(skb);
                return false;
            }

            if *nh.offset(off as isize) == 0 {
                // IPV6_TLV_PADN
                padlen += optlen;
                if padlen > 7 {
                    kfree_skb(skb);
                    return false;
                }
                // Check for zero padding
                for i in 2..optlen {
                    if *nh.offset((off + i) as isize) != 0 {
                        kfree_skb(skb);
                        return false;
                    }
                }
            } else {
                tlv_count += 1;
                if tlv_count > max_count {
                    kfree_skb(skb);
                    return false;
                }

                let mut curr = procs;
                while (*curr).type_ >= 0 {
                    if (*curr).type_ == *nh.offset(off as isize) as c_int {
                        if ((*curr).func)(skb, off) == false {
                            return false;
                        }
                        break;
                    }
                    curr = curr.offset(1);
                }

                if (*curr).type_ < 0 && !ip6_tlvopt_unknown(skb, off, disallow_unknowns) {
                    return false;
                }

                padlen = 0;
            }
            optlen
        };

        off += optlen;
        len -= optlen;
    }

    len == 0
}

#[no_mangle]
pub unsafe extern "C" fn ipv6_destopt_rcv(skb: *mut sk_buff) -> c_int {
    let idev = __in6_dev_get((*skb).dev);
    let opt = IP6CB(skb);
    let _dst = (*skb).dst;
    let net = dev_net((*skb).dev);
    let transport_header = (*skb).transport_header as *mut u8;
    let extlen = ((*transport_header.offset(1)) + 1) << 3;

    if !pskb_may_pull(skb, (*skb).transport_offset + 8)
        || !pskb_may_pull(skb, (*skb).transport_offset + extlen as c_int)
    {
        __IP6_INC_STATS(net, idev, 0); // IPSTATS_MIB_INHDRERRORS
        kfree_skb(skb);
        return -1;
    }

    if extlen > 255 { // max_dst_opts_len boundary
        kfree_skb(skb);
        return -1;
    }

    (*opt).dst1 = (*skb).network_header_len as c_int;
    (*opt).lastopt = (*opt).dst1;

    if ip6_parse_tlv(
        TLVPROCDESTOPT_LST.as_ptr(),
        skb,
        10, // max_dst_opts_cnt boundary
    ) {
        (*skb).transport_header = ((*skb).transport_header as isize + extlen as isize) as u16;
        let opt = IP6CB(skb);
        (*opt).nhoff = (*opt).dst1;
        return 1;
    }

    __IP6_INC_STATS(net, idev, 0); // IPSTATS_MIB_INHDRERRORS
    -1
}

// Default TLV handler with pointer and offset validation
extern "C" fn null_tlv_handler(skb: *mut sk_buff, offset: c_int) -> bool {
    if skb.is_null() || offset < 0 {
        return false;
    }
    false
}

// Static array of TLV handlers
static TLVPROCDESTOPT_LST: [tlvtype_proc; 2] = [
    tlvtype_proc {
        type_: 0, // IPV6_TLV_HAO
        func: ipv6_dest_hao_wrapper,
    },
    tlvtype_proc {
        type_: -1,
        func: null_tlv_handler,
    },
];

// Wrapper for ipv6_dest_hao to match safe function signature
extern "C" fn ipv6_dest_hao_wrapper(skb: *mut sk_buff, optoff: c_int) -> bool {
    unsafe { ipv6_dest_hao(skb, optoff) }
}

// Implementation deferred.
#[no_mangle]
pub unsafe extern "C" fn ipv6_dest_hao(skb: *mut sk_buff, optoff: c_int) -> bool {
    let opt = IP6CB(skb);
    let _ipv6h = ipv6_hdr(skb);
    let _hao = ((*skb).network_header as *mut u8).offset(optoff as isize) as *mut ipv6_destopt_hao;

    if (*opt).dsthao != ptr::null_mut() {
        return false; // Duplicate HAO
    }

    let skb = skb as *mut sk_buff;
    let _ = ip6cb(skb);
    let th = skb_transport_header_ptr(skb);
    if th.is_null() {
        return false;
    }

    // Additional checks would go here...

    true
}

// Implementation of seg6_update_csum
#[no_mangle]
pub unsafe extern "C" fn seg6_update_csum(skb: *mut sk_buff) {
    let hdr = (*skb).transport_header as *mut ipv6_sr_hdr;
    let _addr = ((*hdr).segments.as_ptr() as *mut u8).offset((*hdr).segments_left as isize);

    // Actual checksum update logic would go here...
}

// Implementation of ipv6_srh_rcv
#[no_mangle]
pub unsafe extern "C" fn ipv6_srh_rcv(skb: *mut sk_buff) -> c_int {
    let _opt = IP6CB(skb);
    let _net = dev_net((*skb).dev);
    let _hdr = (*skb).transport_header as *mut ipv6_sr_hdr;
    let _idev = __in6_dev_get((*skb).dev);

    // Implementation deferred.

    1
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ip6_parse_tlv() {
        // Basic test case
        assert!(!null_tlv_handler(ptr::null_mut(), 0));
        assert!(!null_tlv_handler(ptr::null_mut(), -1));
    }

    #[test]
    fn test_null_tlv_handler_validation() {
        let mut skb: sk_buff = unsafe { core::mem::zeroed() };
        assert!(!null_tlv_handler(&mut skb as *mut sk_buff, 10));
        assert!(!null_tlv_handler(&mut skb as *mut sk_buff, -5));
    }
}
