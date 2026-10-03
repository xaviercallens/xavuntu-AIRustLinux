#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! Amanda NAT helper for TCP NAT alteration in Linux kernel
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(private_interfaces)]
#![allow(static_mut_refs)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs)]


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

pub const IP_CT_DIR_ORIGINAL: c_int = 0;
pub const NF_DROP: c_uint = 0xFFFF_FFFF;
pub const NF_ACCEPT: c_uint = 0x0000_0001;
pub const EBUSY: c_int = 16;

#[repr(C)]
struct nf_conntrack_proto { tcp: nf_conntrack_proto_tcp }

#[repr(C)]
struct nf_conntrack_proto_tcp { port: u16 }

#[repr(C)]
struct nf_conntrack_tuple_dst { u: nf_conntrack_tuple_u }

#[repr(C)]
struct nf_conntrack_tuple_u { tcp: nf_conntrack_tuple_tcp }

#[repr(C)]
struct nf_conntrack_tuple_tcp { port: u16 }

#[repr(C)]
struct nf_conntrack_tuple { dst: nf_conntrack_tuple_dst }

#[repr(C)]
struct nf_conntrack_expect {
    saved_proto: nf_conntrack_proto,
    tuple: nf_conntrack_tuple,
    dir: c_int,
    expectfn: Option<unsafe extern "C" fn(*mut nf_conntrack_expect)>,
}

#[repr(C)]
struct nf_conntrack_nat_helper { name: *const u8 }

// Function declarations for kernel functions
extern "C" {
    fn nf_ct_expect_related(exp: *mut nf_conntrack_expect, flags: c_int) -> c_int;
    fn nf_ct_unexpect_related(exp: *mut nf_conntrack_expect);
    fn nf_nat_mangle_udp_packet(
        skb: *mut sk_buff,
        master: *mut c_void,
        ctinfo: c_uint,
        protoff: c_uint,
        matchoff: c_uint,
        matchlen: c_uint,
        buffer: *const u8,
        buflen: c_uint,
    ) -> c_int;
    fn nf_ct_helper_log(skb: *mut sk_buff, master: *mut c_void, msg: *const c_char);
    fn nf_nat_helper_unregister(helper: *mut nf_conntrack_nat_helper);
    fn nf_nat_helper_register(helper: *mut nf_conntrack_nat_helper);
    fn synchronize_rcu();
}

// Helper macro for initializing nf_conntrack_nat_helper
const fn nf_ct_nat_helper_init(name: *const u8) -> nf_conntrack_nat_helper {
    nf_conntrack_nat_helper { name }
}

// Global static variables
static AMANDA_NAME: &[u8; 7] = b"amanda\0";
static ALL_PORTS_IN_USE: &[u8; 17] = b"all ports in use\0";
static CANNOT_MANGLE_PACKET: &[u8; 21] = b"cannot mangle packet\0";

static NAT_HELPER_AMANDA: SyncWrapper<nf_conntrack_nat_helper> =
    SyncWrapper::new(nf_ct_nat_helper_init(AMANDA_NAME.as_ptr()));

#[unsafe(no_mangle)]
static nf_nat_amanda_hook: SyncWrapper<Option<
    unsafe extern "C" fn(
        skb: *mut sk_buff,
        ctinfo: c_uint,
        protoff: c_uint,
        matchoff: c_uint,
        matchlen: c_uint,
        exp: *mut nf_conntrack_expect,
    ) -> c_uint,
>> = SyncWrapper::new(None);

#[unsafe(no_mangle)]
pub unsafe extern "C" fn help(
    skb: *mut sk_buff,
    ctinfo: c_uint,
    protoff: c_uint,
    matchoff: c_uint,
    matchlen: c_uint,
    exp: *mut nf_conntrack_expect,
) -> c_uint {
    if exp.is_null() {
        return NF_DROP;
    }

    unsafe {
        (*exp).saved_proto.tcp.port = (*exp).tuple.dst.u.tcp.port;
        (*exp).dir = IP_CT_DIR_ORIGINAL;
        (*exp).expectfn = None;
    }

    let mut port: u16 = unsafe { ntohs((*exp).saved_proto.tcp.port) };

    while port != 0 {
        unsafe {
            (*exp).tuple.dst.u.tcp.port = htons(port);
        }
        let res = unsafe { nf_ct_expect_related(exp, 0) };

        if res == 0 {
            break;
        } else if res != -EBUSY {
            port = 0;
            break;
        }

        port = port.wrapping_sub(1);
    }

    if port == 0 {
        unsafe {
            nf_ct_helper_log(
                skb,
                core::ptr::null_mut(),
                ALL_PORTS_IN_USE.as_ptr() as *const c_char,
            );
        }
        return NF_DROP;
    }

    let mut buffer: [u8; 6] = [0; 6];
    let mut temp = port;
    let mut i: usize = 5;
    buffer[i] = 0;

    if temp == 0 {
        i = 4;
        buffer[i] = b'0';
    } else {
        while temp > 0 && i > 0 {
            i -= 1;
            buffer[i] = b'0' + (temp % 10) as u8;
            temp /= 10;
        }
    }

    let buflen: c_uint = (5 - i) as c_uint;

    let rc = unsafe {
        nf_nat_mangle_udp_packet(
            skb,
            core::ptr::null_mut(),
            ctinfo,
            protoff,
            matchoff,
            matchlen,
            buffer[i..5].as_ptr(),
            buflen,
        )
    };

    if rc == 0 {
        unsafe {
            nf_ct_helper_log(
                skb,
                core::ptr::null_mut(),
                CANNOT_MANGLE_PACKET.as_ptr() as *const c_char,
            );
            nf_ct_unexpect_related(exp);
        }
        return NF_DROP;
    }

    NF_ACCEPT
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn nf_nat_amanda_fini() {
    nf_nat_helper_unregister(NAT_HELPER_AMANDA.get_mut());
    *nf_nat_amanda_hook.get_mut() = None;
    synchronize_rcu();
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn nf_nat_amanda_init() {
    // SAFETY: This is a module init function, called once at load time
    assert!((*nf_nat_amanda_hook.get_mut()).is_none(), "Hook already initialized");

    nf_nat_helper_register(NAT_HELPER_AMANDA.get_mut());
    *nf_nat_amanda_hook.get_mut() = Some(help);
}

// Helper functions for byte order conversion
#[inline]
unsafe fn htons(x: u16) -> u16 { x.to_be() }

#[inline]
unsafe fn ntohs(x: u16) -> u16 { u16::from_be(x) }
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
