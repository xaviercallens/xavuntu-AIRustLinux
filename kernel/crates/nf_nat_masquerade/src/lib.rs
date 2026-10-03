#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
use kernel_types::*;

const IPPROTO_TCP: u8 = 6;
const IPPROTO_UDP: u8 = 17;
const NF_NAT_RANGE_MAP_IPS: u32 = 1;
const AF_INET: u16 = 2;
const AF_INET6: u16 = 10;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct NF_NAT_MASQUERADE {
    pub masq: NF_NAT_RANGE,
    pub timeout: u32,
    pub flags: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct NF_NAT_RANGE {
    pub flags: u32,
    pub min_addr: NF_INET_ADDR,
    pub max_addr: NF_INET_ADDR,
    pub min_proto: NF_NAT_MULTI_RANGE_COMPAT,
    pub max_proto: NF_NAT_MULTI_RANGE_COMPAT,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct NF_NAT_MULTI_RANGE_COMPAT { pub range: [u32; 2] }

// Helper struct for protocol info
#[repr(C)]
#[derive(Copy, Clone)]
struct nf_conntrack_l4proto {
    pub l4proto: u8,
    pub protocol: u8,
}

// Helper functions
unsafe fn get_ct_protocol(ct: &NF_CONN) -> u8 {
    if ct.proto.is_null() {
        return 0;
    }
    let proto = ct.proto as *const nf_conntrack_l4proto;
    if let Some(p) = proto.as_ref() {
        p.protocol
    } else {
        0
    }
}

unsafe fn get_ct_src_addr_ip(ct: &NF_CONN) -> __be32 {
    ct.tuplehash[0].tuple.src.u.all as u32
}

unsafe fn get_ct_src_addr_ip6(ct: &NF_CONN) -> [__be32; 4] {
    let ip = ct.tuplehash[0].tuple.src.u.icmp;
    [ip.id as u32, 0, 0, 0]
}

unsafe fn get_ct_l3num(ct: &NF_CONN) -> u16 {
    ct.tuplehash[0].tuple.src_l3num
}

// Implementation deferred.
#[no_mangle]
pub unsafe extern "C" fn NF_NAT_SETUP_INFO(
    _ct: *mut NF_CONN,
    _range: *mut NF_NAT_RANGE,
    _min: *mut NF_NAT_RANGE,
    _max: *mut NF_NAT_RANGE,
) -> c_int {
    let ret: c_int = 0;
    ret
}

#[no_mangle]
pub unsafe extern "C" fn NF_CT_TIMEOUT_SET(
    _ct: *mut NF_CONN,
    _timeout: *mut u32,
    _flags: u32,
) -> c_int {
    let ret: c_int = 0;
    ret
}

#[no_mangle]
pub unsafe extern "C" fn NF_NAT_MASQUERADE_IPV4(
    ct: *mut NF_CONN,
    min: *mut NF_NAT_RANGE,
    max: *mut NF_NAT_RANGE,
) -> c_int {
        let ct_ref = match ct.as_ref() { Some(ct) => ct, None => return -EINVAL };
        let _min = match min.as_ref() { Some(min) => min, None => return -EINVAL };
        let _max = match max.as_ref() { Some(max) => max, None => return -EINVAL };

        let protocol = get_ct_protocol(ct_ref);
        if protocol != IPPROTO_TCP && protocol != IPPROTO_UDP {
            return -EINVAL;
        }

        let src_ip = get_ct_src_addr_ip(ct_ref);

        let mut masq = NF_NAT_MASQUERADE {
            masq: NF_NAT_RANGE {
                flags: NF_NAT_RANGE_MAP_IPS,
                min_addr: NF_INET_ADDR {
                    ip: src_ip,
                },
                max_addr: NF_INET_ADDR {
                    ip: src_ip,
                },
                min_proto: NF_NAT_MULTI_RANGE_COMPAT {
                    range: [0, 0],
                },
                max_proto: NF_NAT_MULTI_RANGE_COMPAT {
                    range: [0, 0],
                },
            },
            timeout: 0,
            flags: 0,
        };

        if protocol == IPPROTO_TCP {
            let tcp = ct as *const NF_CONN as *const TCP_SOCK;
            if let Some(tcp) = tcp.as_ref() {
                masq.masq.min_proto.range[0] = tcp.inet.inet_sport as u32;
                masq.masq.max_proto.range[0] = tcp.inet.inet_sport as u32;
            }
        } else if protocol == IPPROTO_UDP {
            let udp = ct as *const NF_CONN as *const UDP_SOCK;
            if let Some(udp) = udp.as_ref() {
                masq.masq.min_proto.range[0] = udp.inet.inet_sport as u32;
                masq.masq.max_proto.range[0] = udp.inet.inet_sport as u32;
            }
        }

        if NF_NAT_SETUP_INFO(ct, &mut masq.masq, min, max) != 0 {
            return -EINVAL;
        }

        if NF_CT_TIMEOUT_SET(ct, &mut masq.timeout, masq.flags) != 0 {
            return -EINVAL;
        }

    0
}

#[no_mangle]
pub unsafe extern "C" fn NF_NAT_MASQUERADE_IPV6(
    ct: *mut NF_CONN,
    min: *mut NF_NAT_RANGE,
    max: *mut NF_NAT_RANGE,
) -> c_int {
        let ct_ref = match ct.as_ref() { Some(ct) => ct, None => return -EINVAL };
        let _min = match min.as_ref() { Some(min) => min, None => return -EINVAL };
        let _max = match max.as_ref() { Some(max) => max, None => return -EINVAL };

        let protocol = get_ct_protocol(ct_ref);
        if protocol != IPPROTO_TCP && protocol != IPPROTO_UDP {
            return -EINVAL;
        }

        let src_ip6 = get_ct_src_addr_ip6(ct_ref);

        let mut masq = NF_NAT_MASQUERADE {
            masq: NF_NAT_RANGE {
                flags: NF_NAT_RANGE_MAP_IPS,
                min_addr: NF_INET_ADDR {
                    ip6: src_ip6,
                },
                max_addr: NF_INET_ADDR {
                    ip6: src_ip6,
                },
                min_proto: NF_NAT_MULTI_RANGE_COMPAT {
                    range: [0, 0],
                },
                max_proto: NF_NAT_MULTI_RANGE_COMPAT {
                    range: [0, 0],
                },
            },
            timeout: 0,
            flags: 0,
        };

        if protocol == IPPROTO_TCP {
            let tcp = ct as *const NF_CONN as *const TCP_SOCK;
            if let Some(tcp) = tcp.as_ref() {
                masq.masq.min_proto.range[0] = tcp.inet.inet_sport as u32;
                masq.masq.max_proto.range[0] = tcp.inet.inet_sport as u32;
            }
        } else if protocol == IPPROTO_UDP {
            let udp = ct as *const NF_CONN as *const UDP_SOCK;
            if let Some(udp) = udp.as_ref() {
                masq.masq.min_proto.range[0] = udp.inet.inet_sport as u32;
                masq.masq.max_proto.range[0] = udp.inet.inet_sport as u32;
            }
        }

        if NF_NAT_SETUP_INFO(ct, &mut masq.masq, min, max) != 0 {
            return -EINVAL;
        }

        if NF_CT_TIMEOUT_SET(ct, &mut masq.timeout, masq.flags) != 0 {
            return -EINVAL;
        }

    0
}

#[no_mangle]
pub unsafe extern "C" fn NF_NAT_MASQUERADE_INET(
    ct: *mut NF_CONN,
    min: *mut NF_NAT_RANGE,
    max: *mut NF_NAT_RANGE,
) -> c_int {
        let ct_ref = match ct.as_ref() { Some(ct) => ct, None => return -EINVAL };

        let l3num = get_ct_l3num(ct_ref);
        if l3num == AF_INET {
            NF_NAT_MASQUERADE_IPV4(ct, min, max)
        } else if l3num == AF_INET6 {
            NF_NAT_MASQUERADE_IPV6(ct, min, max)
    } else {
        -EINVAL
    }
}

#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
