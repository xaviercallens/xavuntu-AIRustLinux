#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! nf_conntrack Standalone Module
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::ffi::{c_char, c_int, c_uint, c_void};
use core::panic::PanicInfo;

pub type size_t = usize;
pub type c_size_t = usize;
pub type socklen_t = u32;

pub const NFPROTO_IPV4: u16 = 2; pub const NFPROTO_IPV6: u16 = 10;

pub const IPPROTO_ICMP: u8 = 1;
pub const IPPROTO_TCP: u8 = 6;
pub const IPPROTO_UDP: u8 = 17;
pub const IPPROTO_DCCP: u8 = 33;
pub const IPPROTO_GRE: u8 = 47;
pub const IPPROTO_ICMPV6: u8 = 58;
pub const IPPROTO_SCTP: u8 = 132;
pub const IPPROTO_UDPLITE: u8 = 136;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct seq_file { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub union nf_inet_addr {
    pub all: [u32; 4],
    pub ip: u32,
    pub ip6: [u32; 4],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_src_icmp { pub id: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_src_port { pub port: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_src_gre { pub key: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub union nf_conntrack_tuple_src_u {
    pub icmp: nf_conntrack_tuple_src_icmp,
    pub tcp: nf_conntrack_tuple_src_port,
    pub udp: nf_conntrack_tuple_src_port,
    pub dccp: nf_conntrack_tuple_src_port,
    pub sctp: nf_conntrack_tuple_src_port,
    pub gre: nf_conntrack_tuple_src_gre,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_src {
    pub u3: nf_inet_addr,
    pub u: nf_conntrack_tuple_src_u,
    pub l3num: u16,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_dst_icmp { pub type_: u8, pub code: u8 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_dst_port { pub port: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_dst_gre { pub key: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub union nf_conntrack_tuple_dst_u {
    pub icmp: nf_conntrack_tuple_dst_icmp,
    pub tcp: nf_conntrack_tuple_dst_port,
    pub udp: nf_conntrack_tuple_dst_port,
    pub dccp: nf_conntrack_tuple_dst_port,
    pub sctp: nf_conntrack_tuple_dst_port,
    pub gre: nf_conntrack_tuple_dst_gre,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_dst {
    pub u3: nf_inet_addr,
    pub u: nf_conntrack_tuple_dst_u,
    pub protonum: u8,
    pub dir: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple { pub src: nf_conntrack_tuple_src, pub dst: nf_conntrack_tuple_dst }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_l4proto { pub l4proto: u8, _private: [u8; 0] }

unsafe extern "C" {
    pub fn seq_printf(s: *mut seq_file, fmt: *const c_char, ...) -> c_int;
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn print_tuple(
    s: *mut seq_file,
    tuple: *const nf_conntrack_tuple,
    l4proto: *const nf_conntrack_l4proto,
) {
    // SAFETY: Function is called with valid pointers as per contract
    let tuple_ref = &*tuple;
    let l4proto_ref = &*l4proto;
    let l3num = tuple_ref.src.l3num;

    match l3num {
        NFPROTO_IPV4 => {
            let src_ip = tuple_ref.src.u3.ip;
            let dst_ip = tuple_ref.dst.u3.ip;
            seq_printf(
                s,
                b"src=%pI4 dst=%pI4 \0" as *const _ as *const c_char,
                &src_ip as *const _ as *const c_void,
                &dst_ip as *const _ as *const c_void,
            );
        }
        NFPROTO_IPV6 => {
            let src_ip6 = tuple_ref.src.u3.ip6;
            let dst_ip6 = tuple_ref.dst.u3.ip6;
            seq_printf(
                s,
                b"src=%pI6 dst=%pI6 \0" as *const _ as *const c_char,
                &src_ip6 as *const _ as *const c_void,
                &dst_ip6 as *const _ as *const c_void,
            );
        }
        _ => {}
    }

    let l4proto_num = l4proto_ref.l4proto;

    match l4proto_num {
        IPPROTO_ICMP => {
            let icmp_type = tuple_ref.dst.u.icmp.type_;
            let icmp_code = tuple_ref.dst.u.icmp.code;
            let icmp_id = u16::from_be(tuple_ref.src.u.icmp.id);
            seq_printf(
                s,
                b"type=%u code=%u id=%u \0" as *const _ as *const c_char,
                icmp_type as c_uint,
                icmp_code as c_uint,
                icmp_id as c_uint,
            );
        }
        IPPROTO_TCP => {
            let sport = u16::from_be(tuple_ref.src.u.tcp.port);
            let dport = u16::from_be(tuple_ref.dst.u.tcp.port);
            seq_printf(
                s,
                b"sport=%hu dport=%hu \0" as *const _ as *const c_char,
                sport as c_uint,
                dport as c_uint,
            );
        }
        IPPROTO_UDPLITE | IPPROTO_UDP => {
            let sport = u16::from_be(tuple_ref.src.u.udp.port);
            let dport = u16::from_be(tuple_ref.dst.u.udp.port);
            seq_printf(
                s,
                b"sport=%hu dport=%hu \0" as *const _ as *const c_char,
                sport as c_uint,
                dport as c_uint,
            );
        }
        IPPROTO_DCCP => {
            let sport = u16::from_be(tuple_ref.src.u.dccp.port);
            let dport = u16::from_be(tuple_ref.dst.u.dccp.port);
            seq_printf(
                s,
                b"sport=%hu dport=%hu \0" as *const _ as *const c_char,
                sport as c_uint,
                dport as c_uint,
            );
        }
        IPPROTO_SCTP => {
            let sport = u16::from_be(tuple_ref.src.u.sctp.port);
            let dport = u16::from_be(tuple_ref.dst.u.sctp.port);
            seq_printf(
                s,
                b"sport=%hu dport=%hu \0" as *const _ as *const c_char,
                sport as c_uint,
                dport as c_uint,
            );
        }
        IPPROTO_ICMPV6 => {
            let icmp_type = tuple_ref.dst.u.icmp.type_;
            let icmp_code = tuple_ref.dst.u.icmp.code;
            let icmp_id = u16::from_be(tuple_ref.src.u.icmp.id);
            seq_printf(
                s,
                b"type=%u code=%u id=%u \0" as *const _ as *const c_char,
                icmp_type as c_uint,
                icmp_code as c_uint,
                icmp_id as c_uint,
            );
        }
        IPPROTO_GRE => {
            let srckey = u16::from_be(tuple_ref.src.u.gre.key);
            let dstkey = u16::from_be(tuple_ref.dst.u.gre.key);
            seq_printf(
                s,
                b"srckey=0x%x dstkey=0x%x \0" as *const _ as *const c_char,
                srckey as c_uint,
                dstkey as c_uint,
            );
        }
        _ => {}
    }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}
