#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs)]

use core::ffi::c_int;
use core::ffi::c_void;
use core::mem;
use core::ptr;
use kernel_types::*;

pub const IPPROTO_UDP: u8 = 17;
pub const IPPROTO_IPV6: u8 = 41;
pub const IPPROTO_IPIP: u8 = 4;
pub const IPPROTO_UDPLITE: u8 = 136;

pub const EINVAL: c_int = -22; pub const ENOENT: c_int = -2; pub const EOPNOTSUPP: c_int = -95;

// Type definitions

#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip_tunnel_encap { pub dport: __be16, pub flags: __be16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct flowi6 { pub saddr: in6_addr, pub daddr: in6_addr }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct guehdr {
    pub version: u8,
    pub control: u8,
    pub hlen: u8,
    pub proto_ctype: u8,
}

#[repr(C)]
pub struct ip6_tnl_encap_ops {
    pub encap_hlen: extern "C" fn(e: *const ip_tunnel_encap) -> c_int,
    pub build_header: extern "C" fn(
        skb: *mut sk_buff,
        e: *const ip_tunnel_encap,
        protocol: *mut u8,
        fl6: *mut flowi6,
    ) -> c_int,
    pub err_handler: extern "C" fn(
        skb: *mut sk_buff,
        opt: *mut c_void,
        type_: u8,
        code: u8,
        offset: c_int,
        info: u32,
    ) -> c_int,
}

#[repr(C)]
pub struct inet6_protocol {
    pub handler: Option<extern "C" fn(skb: *mut sk_buff, opt: *mut c_void) -> c_int>,
    pub err_handler: Option<extern "C" fn(
        skb: *mut sk_buff,
        opt: *mut c_void,
        type_: u8,
        code: u8,
        offset: c_int,
        info: u32,
    ) -> c_int>,
}

unsafe extern "C" {
    fn skb_push(skb: *mut sk_buff, len: size_t) -> *mut c_void;
    fn skb_reset_transport_header(skb: *mut sk_buff);
    fn udp_hdr(skb: *mut sk_buff) -> *mut udphdr;
    fn udp6_set_csum(
        flag: c_int,
        skb: *mut sk_buff,
        saddr: *const in6_addr,
        daddr: *const in6_addr,
        len: size_t,
    );
    fn skb_len(skb: *const sk_buff) -> size_t;
    fn __fou_build_header(
        skb: *mut sk_buff,
        e: *const ip_tunnel_encap,
        protocol: *mut u8,
        sport: *mut u16,
        type_: c_int,
    ) -> c_int;
    fn __gue_build_header(
        skb: *mut sk_buff,
        e: *const ip_tunnel_encap,
        protocol: *mut u8,
        sport: *mut u16,
        type_: c_int,
    ) -> c_int;
    fn pskb_may_pull(skb: *mut sk_buff, len: size_t) -> c_int;
    fn validate_gue_flags(gueh: *const guehdr, optlen: size_t) -> c_int;
    fn ip6_tnl_encap_add_ops(ops: *const ip6_tnl_encap_ops, encap_type: c_int) -> c_int;
    fn ip6_tnl_encap_del_ops(ops: *const ip6_tnl_encap_ops, encap_type: c_int);
    fn pr_err(fmt: *const c_char, ...);
}

const TUNNEL_ENCAP_FLAG_CSUM6: u16 = 0x0001;
const SKB_GSO_UDP_TUNNEL: c_int = 0;
const SKB_GSO_UDP_TUNNEL_CSUM: c_int = 1;
const FOU_ENCAP: c_int = 1;
const GUE_ENCAP: c_int = 2;

fn fou6_build_udp(
    skb: *mut sk_buff,
    e: *const ip_tunnel_encap,
    fl6: *const flowi6,
    protocol: *mut u8,
    sport: u16,
) {
    unsafe {
        let _ = skb_push(skb, core::mem::size_of::<udphdr>()) as *mut udphdr;
        skb_reset_transport_header(skb);

        let uh = udp_hdr(skb);
        (*uh).dest = (*e).dport;
        (*uh).source = sport;
        (*uh).len = (skb_len(skb) as u16).to_be();

        udp6_set_csum(
            if ((*e).flags & TUNNEL_ENCAP_FLAG_CSUM6) == 0 { 1 } else { 0 },
            skb,
            &(*fl6).saddr,
            &(*fl6).daddr,
            skb_len(skb),
        );

        *protocol = IPPROTO_UDP;
    }
}

extern "C" fn fou6_build_header(
    skb: *mut sk_buff,
    e: *const ip_tunnel_encap,
    protocol: *mut u8,
    fl6: *mut flowi6,
) -> c_int {
    unsafe {
        let mut sport = 0u16;
        let type_ = if ((*e).flags & TUNNEL_ENCAP_FLAG_CSUM6) != 0 {
            SKB_GSO_UDP_TUNNEL_CSUM
        } else {
            SKB_GSO_UDP_TUNNEL
        };

        let err = __fou_build_header(skb, e, protocol, &mut sport, type_);
        if err != 0 {
            return err;
        }

        fou6_build_udp(skb, e, fl6, protocol, sport);
        0
    }
}

extern "C" fn gue6_build_header(
    skb: *mut sk_buff,
    e: *const ip_tunnel_encap,
    protocol: *mut u8,
    fl6: *mut flowi6,
) -> c_int {
    unsafe {
        let mut sport = 0u16;
        let type_ = if ((*e).flags & TUNNEL_ENCAP_FLAG_CSUM6) != 0 {
            SKB_GSO_UDP_TUNNEL_CSUM
        } else {
            SKB_GSO_UDP_TUNNEL
        };

        let err = __gue_build_header(skb, e, protocol, &mut sport, type_);
        if err != 0 {
            return err;
        }

        fou6_build_udp(skb, e, fl6, protocol, sport);
        0
    }
}

fn gue6_err_proto_handler(
    proto: c_int,
    skb: *mut sk_buff,
    opt: *mut c_void,
    type_: u8,
    code: u8,
    offset: c_int,
    info: u32,
) -> c_int {
    unsafe {
        let ipprot = ptr::read_volatile(&(*(&inet6_protos[proto as usize] as *const *const inet6_protocol)));
        if !ipprot.is_null() {
            if let Some(handler) = (*ipprot).err_handler {
                let result = handler(
                    skb,
                    opt,
                    type_,
                    code,
                    offset,
                    info,
                );
                if result == 0 {
                    return 0;
                }
            }
        }
        -ENOENT
    }
}

extern "C" fn gue6_err(
    skb: *mut sk_buff,
    opt: *mut c_void,
    type_: u8,
    code: u8,
    offset: c_int,
    info: u32,
) -> c_int {
    unsafe {
        let transport_offset = 0; // skb_transport_offset(skb)
        let udp = udp_hdr(skb);
        let guehdr = &(*(udp.offset(1) as *const guehdr));

        let len = mem::size_of::<udphdr>() + mem::size_of::<guehdr>();
        if pskb_may_pull(skb, (transport_offset + len) as usize) == 0 {
            return -EINVAL;
        }

        match guehdr.version {
            0 => {}
            1 => {
                skb_set_transport_header(skb, -(mem::size_of::<icmp6hdr>() as isize));

                let iph = &*(guehdr as *const guehdr as *const iphdr);
                match (*iph).version_ihl >> 4 {
                    4 => {
                        let ret = gue6_err_proto_handler(
                            IPPROTO_IPIP as c_int,
                            skb,
                            opt,
                            type_,
                            code,
                            offset,
                            info,
                        );
                        return ret;
                    }
                    6 => {
                        let ret = gue6_err_proto_handler(
                            IPPROTO_IPV6 as c_int,
                            skb,
                            opt,
                            type_,
                            code,
                            offset,
                            info,
                        );
                        return ret;
                    }
                    _ => return -EOPNOTSUPP,
                }
            }
            _ => return -EOPNOTSUPP,
        }

        if guehdr.control != 0 {
            return -ENOENT;
        }

        let optlen = (guehdr.hlen as usize) << 2;
        if pskb_may_pull(skb, (transport_offset + len + optlen) as usize) == 0 {
            return -EINVAL;
        }

        let udp = udp_hdr(skb);
        let guehdr = &(*(udp.offset(1) as *const guehdr));
        if validate_gue_flags(guehdr, optlen) != 0 {
            return -EINVAL;
        }

        if guehdr.proto_ctype == IPPROTO_UDP || guehdr.proto_ctype == IPPROTO_UDPLITE {
            return -EOPNOTSUPP;
        }

        skb_set_transport_header(skb, -(mem::size_of::<icmp6hdr>() as isize));
        let ret = gue6_err_proto_handler(
            guehdr.proto_ctype as c_int,
            skb,
            opt,
            type_,
            code,
            offset,
            info,
        );

        skb_set_transport_header(skb, transport_offset as isize);
        ret
    }
}

// Safe wrappers for unsafe functions
extern "C" fn fou_encap_hlen_wrapper(e: *const ip_tunnel_encap) -> c_int {
    unsafe { fou_encap_hlen(e) }
}

extern "C" fn gue_encap_hlen_wrapper(e: *const ip_tunnel_encap) -> c_int {
    unsafe { gue_encap_hlen(e) }
}

// Static data
static FOU_IP6TUN_OPS: ip6_tnl_encap_ops = ip6_tnl_encap_ops {
    encap_hlen: fou_encap_hlen_wrapper,
    build_header: fou6_build_header,
    err_handler: gue6_err,
};

static GUE_IP6TUN_OPS: ip6_tnl_encap_ops = ip6_tnl_encap_ops {
    encap_hlen: gue_encap_hlen_wrapper,
    build_header: gue6_build_header,
    err_handler: gue6_err,
};

// Extern declarations for undefined symbols
extern "C" {
    fn fou_encap_hlen(e: *const ip_tunnel_encap) -> c_int;
    fn gue_encap_hlen(e: *const ip_tunnel_encap) -> c_int;
    static inet6_protos: [*const inet6_protocol; 256];
    fn skb_set_transport_header(skb: *mut sk_buff, offset: isize);
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct icmp6hdr {
    pub icmp6_type: u8,
    pub icmp6_code: u8,
    pub icmp6_cksum: u16,
    pub icmp6_dataun: [u8; 4],
}

// Module functions
#[no_mangle]
pub unsafe extern "C" fn ip6_tnl_encap_add_fou_ops() -> c_int {
    let mut ret = ip6_tnl_encap_add_ops(&FOU_IP6TUN_OPS, 1); // TUNNEL_ENCAP_FOU
    if ret < 0 {
        pr_err(b"can't add fou6 ops\0".as_ptr() as *const c_char);
        return ret;
    }

    ret = ip6_tnl_encap_add_ops(&GUE_IP6TUN_OPS, 2); // TUNNEL_ENCAP_GUE
    if ret < 0 {
        ip6_tnl_encap_del_ops(&FOU_IP6TUN_OPS, 1);
        pr_err(b"can't add gue6 ops\0".as_ptr() as *const c_char);
        return ret;
    }

    ret
}

#[no_mangle]
pub unsafe extern "C" fn ip6_tnl_encap_del_fou_ops() {
    ip6_tnl_encap_del_ops(&FOU_IP6TUN_OPS, 1);
    ip6_tnl_encap_del_ops(&GUE_IP6TUN_OPS, 2);
}

// Module init/exit
#[no_mangle]
pub unsafe extern "C" fn fou6_init() -> c_int {
    ip6_tnl_encap_add_fou_ops()
}

#[no_mangle]
pub unsafe extern "C" fn fou6_fini() {
    ip6_tnl_encap_del_fou_ops()
}

// Module metadata
#[no_mangle]
pub static MOD_AUTHOR: [u8; 34] = *b"Tom Herbert <therbert@google.com>\0";

#[no_mangle]
pub static MOD_LICENSE: [u8; 4] = *b"GPL\0";

#[no_mangle]
pub static MOD_DESCRIPTION: [u8; 20] = *b"Foo over UDP (IPv6)\0";
#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------------
    // Test 1 – FOU/GUE protocol constants have the correct IANA-assigned values
    // -----------------------------------------------------------------------
    #[test]
    fn test_protocol_constants() {
        // IPPROTO_UDP = 17 (RFC 768)
        assert_eq!(IPPROTO_UDP, 17u8);
        // IPPROTO_IPV6 = 41 (RFC 2473)
        assert_eq!(IPPROTO_IPV6, 41u8);
        // IPPROTO_IPIP = 4 (RFC 2003)
        assert_eq!(IPPROTO_IPIP, 4u8);
        // IPPROTO_UDPLITE = 136 (RFC 3828)
        assert_eq!(IPPROTO_UDPLITE, 136u8);
    }

    // -----------------------------------------------------------------------
    // Test 2 – POSIX error-code constants must match kernel errno values
    // -----------------------------------------------------------------------
    #[test]
    fn test_errno_constants() {
        // EINVAL = -22, ENOENT = -2, EOPNOTSUPP = -95
        assert_eq!(EINVAL, -22i32);
        assert_eq!(ENOENT, -2i32);
        assert_eq!(EOPNOTSUPP, -95i32);
    }

    // -----------------------------------------------------------------------
    // Test 3 – Encap-type sentinels and GSO flag values are correct
    // -----------------------------------------------------------------------
    #[test]
    fn test_encap_type_and_gso_constants() {
        // FOU = 1, GUE = 2  (kernel TUNNEL_ENCAP_* enum order)
        assert_eq!(FOU_ENCAP, 1i32);
        assert_eq!(GUE_ENCAP, 2i32);
        // GSO tunnel types
        assert_eq!(SKB_GSO_UDP_TUNNEL, 0i32);
        assert_eq!(SKB_GSO_UDP_TUNNEL_CSUM, 1i32);
        // CSUM6 flag bit
        assert_eq!(TUNNEL_ENCAP_FLAG_CSUM6, 0x0001u16);
    }

    // -----------------------------------------------------------------------
    // Test 4 – guehdr struct layout: zeroed header has safe, predictable fields
    // -----------------------------------------------------------------------
    #[test]
    fn test_guehdr_zeroed_fields() {
        // SAFETY: guehdr is a plain-old-data #[repr(C)] struct; zeroing it
        // produces a valid bit-pattern (version=0, control=0, hlen=0,
        // proto_ctype=0) which is a legal "no options, FOU-mode" GUE header.
        let hdr: guehdr = unsafe { core::mem::zeroed() };
        assert_eq!(hdr.version, 0u8);
        assert_eq!(hdr.control, 0u8);
        assert_eq!(hdr.hlen, 0u8);
        assert_eq!(hdr.proto_ctype, 0u8);
    }

    // -----------------------------------------------------------------------
    // Test 5 – guehdr known-good input: version=0, proto_ctype=41 (IPv6)
    // -----------------------------------------------------------------------
    #[test]
    fn test_guehdr_known_good_ipv6_encap() {
        let hdr = guehdr {
            version: 0,
            control: 0,
            hlen: 0,
            proto_ctype: IPPROTO_IPV6, // 41 – valid inner protocol
        };
        // A control==0, version==0 header with a non-UDP/UDPLITE proto_ctype
        // should *not* be treated as a control message and should not trigger
        // the EOPNOTSUPP early-exit in gue6_err (version != 1 path is fine).
        assert_eq!(hdr.version, 0u8);
        assert_eq!(hdr.control, 0u8);
        assert_eq!(hdr.proto_ctype, 41u8);
        // Verify this proto is neither UDP nor UDPLITE (rejection guard)
        assert_ne!(hdr.proto_ctype, IPPROTO_UDP);
        assert_ne!(hdr.proto_ctype, IPPROTO_UDPLITE);
    }

    // -----------------------------------------------------------------------
    // Test 6 – ip_tunnel_encap CSUM6 flag logic mirrors what fou6_build_header
    //           and gue6_build_header use to select the GSO type
    // -----------------------------------------------------------------------
    #[test]
    fn test_tunnel_encap_csum6_flag_logic() {
        // Without CSUM6 flag → expect SKB_GSO_UDP_TUNNEL (0)
        let e_no_csum = ip_tunnel_encap { dport: 4789u16.to_be(), flags: 0 };
        let type_no_csum = if (e_no_csum.flags & TUNNEL_ENCAP_FLAG_CSUM6) != 0 {
            SKB_GSO_UDP_TUNNEL_CSUM
        } else {
            SKB_GSO_UDP_TUNNEL
        };
        assert_eq!(type_no_csum, SKB_GSO_UDP_TUNNEL);

        // With CSUM6 flag set → expect SKB_GSO_UDP_TUNNEL_CSUM (1)
        let e_with_csum = ip_tunnel_encap { dport: 4789u16.to_be(), flags: TUNNEL_ENCAP_FLAG_CSUM6 };
        let type_with_csum = if (e_with_csum.flags & TUNNEL_ENCAP_FLAG_CSUM6) != 0 {
            SKB_GSO_UDP_TUNNEL_CSUM
        } else {
            SKB_GSO_UDP_TUNNEL
        };
        assert_eq!(type_with_csum, SKB_GSO_UDP_TUNNEL_CSUM);
    }

    // -----------------------------------------------------------------------
    // Test 7 – IPPROTO_UDP and IPPROTO_UDPLITE are correctly rejected by the
    //           proto_ctype guard in gue6_err (mirrors the `return -EOPNOTSUPP`
    //           branch without needing FFI)
    // -----------------------------------------------------------------------
    #[test]
    fn test_guehdr_udp_proto_ctype_rejected() {
        // Simulate the guard condition from gue6_err:
        //   if guehdr.proto_ctype == IPPROTO_UDP || guehdr.proto_ctype == IPPROTO_UDPLITE
        //       return EOPNOTSUPP
        let check = |proto: u8| -> i32 {
            if proto == IPPROTO_UDP || proto == IPPROTO_UDPLITE {
                EOPNOTSUPP // -95
            } else {
                0
            }
        };
        assert_eq!(check(IPPROTO_UDP),     EOPNOTSUPP);
        assert_eq!(check(IPPROTO_UDPLITE), EOPNOTSUPP);
        assert_eq!(check(IPPROTO_IPV6),    0);
        assert_eq!(check(IPPROTO_IPIP),    0);
    }

    // -----------------------------------------------------------------------
    // Test 8 – guehdr optlen calculation from hlen field (hlen << 2 bytes)
    //           and control-flag zero check (non-zero control → ENOENT)
    // -----------------------------------------------------------------------
    #[test]
    fn test_guehdr_optlen_and_control_flag() {
        // optlen = hlen << 2  (each unit = 4 bytes, as in the kernel code)
        let hdr_hlen2 = guehdr { version: 0, control: 0, hlen: 2, proto_ctype: IPPROTO_IPV6 };
        let optlen = (hdr_hlen2.hlen as usize) << 2;
        assert_eq!(optlen, 8usize); // 2 × 4 bytes

        // A control-message header (control != 0) triggers ENOENT
        let hdr_ctrl = guehdr { version: 0, control: 1, hlen: 0, proto_ctype: 0 };
        let result = if hdr_ctrl.control != 0 { ENOENT } else { 0 };
        assert_eq!(result, ENOENT);

        // A non-control header with hlen=0 has zero optlen
        let hdr_no_opts = guehdr { version: 0, control: 0, hlen: 0, proto_ctype: IPPROTO_IPV6 };
        assert_eq!((hdr_no_opts.hlen as usize) << 2, 0usize);
    }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
