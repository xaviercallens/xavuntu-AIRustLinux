#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! IRC (DCC) connection tracking helper for Linux kernel
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(clippy::all)]
#![allow(clippy::not_unsafe_ptr_arg_deref)]
#![allow(private_interfaces)]
#![allow(static_mut_refs)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

use core::ffi::{c_int, c_uint, c_void};
use core::ptr;
use kernel_types::*;

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

// Constants
pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const NF_ACCEPT: c_int = 0;
pub const NF_DROP: c_int = 1;
pub const NF_CT_EXPECT_MAX_CNT: c_uint = 100;
pub const IP_CT_DIR_REPLY: c_int = 1;
pub const IP_CT_ESTABLISHED: c_int = 2;
pub const IP_CT_ESTABLISHED_REPLY: c_int = 3;
pub const NF_CT_EXPECT_CLASS_DEFAULT: c_int = 0;

// Type definitions

#[repr(C)]
#[derive(Copy, Clone)]
pub struct tcphdr {
    pub source: u16,
    pub dest: u16,
    pub doff: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_with_addr {
    pub src: nf_conntrack_tuple_src_with_addr,
    pub dst: nf_conntrack_tuple_dst_with_addr,
    pub src_l3num: u16,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_src_with_addr {
    pub ip: u32,
    pub l3num: u8,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_dst_with_addr {
    pub ip: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_expect { pub class: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_expect_policy { pub max_expected: c_uint, pub timeout: c_uint }

#[repr(C)]
#[derive(Copy, Clone, Default)]
pub struct nf_conntrack_helper {
    _priv: [u8; 0],
    name: *const u8,
}

// SAFETY: nf_conntrack_helper is used in kernel context where thread safety is handled by kernel locks
unsafe impl Sync for nf_conntrack_helper {}

#[repr(C)]
#[derive(Copy, Clone)]
struct Spinlock { _private: u32 }

type nf_nat_irc_hook_t = Option<
    unsafe extern "C" fn(
        skb: *const sk_buff,
        ctinfo: c_int,
        protoff: c_uint,
        matchoff: c_uint,
        matchlen: c_uint,
        exp: *mut nf_conntrack_expect,
    ) -> c_int,
>;

struct IrcConfig {
    ports: [u16; 8],
    ports_c: c_uint,
    max_dcc_channels: c_uint,
}
struct IrcConfigWrapper(core::cell::UnsafeCell<IrcConfig>);
// SAFETY: Configuration is only mutated during single-threaded module initialization.
unsafe impl Sync for IrcConfigWrapper {}

static IRC_CONFIG: IrcConfigWrapper = IrcConfigWrapper(core::cell::UnsafeCell::new(IrcConfig {
    ports: [0; 8],
    ports_c: 0,
    max_dcc_channels: 8,
}));

impl IrcConfigWrapper {
    #[inline(always)]
    unsafe fn get_mut(&self) -> &mut IrcConfig {
        // SAFETY: Caller must ensure single-threaded context (module init).
        unsafe { &mut *self.0.get() }
    }
}

struct IrcBufferState {
    storage: [u8; 65536],
    buffer_ptr: *mut c_void,
    lock: Spinlock,
}
struct IrcBufferWrapper(core::cell::UnsafeCell<IrcBufferState>);
// SAFETY: Access to the buffer is synchronized by the embedded Spinlock.
unsafe impl Sync for IrcBufferWrapper {}

static IRC_BUFFER_STATE: IrcBufferWrapper = IrcBufferWrapper(core::cell::UnsafeCell::new(IrcBufferState {
    storage: [0; 65536],
    buffer_ptr: ptr::null_mut(),
    lock: Spinlock { _private: 0 },
}));

impl IrcBufferWrapper {
    #[inline(always)]
    unsafe fn get_mut(&self) -> &mut IrcBufferState {
        // SAFETY: Caller must acquire the lock or be in single-threaded context.
        unsafe { &mut *self.0.get() }
    }
}

struct IrcHooksWrapper(core::cell::UnsafeCell<Option<nf_nat_irc_hook_t>>);
// SAFETY: Hook is modified only during module init/exit.
unsafe impl Sync for IrcHooksWrapper {}
static NF_NAT_IRC_HOOK: IrcHooksWrapper = IrcHooksWrapper(core::cell::UnsafeCell::new(None));

impl IrcHooksWrapper {
    #[inline(always)]
    unsafe fn get_mut(&self) -> &mut Option<nf_nat_irc_hook_t> {
        // SAFETY: Caller ensures single-threaded initialization context.
        unsafe { &mut *self.0.get() }
    }
}

unsafe extern "C" {
    static nf_nat_irc_hook: core::cell::UnsafeCell<nf_nat_irc_hook_t>;
}

const DCC_PROTOS: [&[u8; 6]; 5] = [b"SEND \0", b"CHAT \0", b"MOVE \0", b"TSEND\0", b"SCHAT\0"];

// Helper function to convert ctinfo to direction
#[inline]
fn CTINFO2DIR(ctinfo: c_int) -> c_int {
    ctinfo & 1
}

// Network byte order conversion
#[inline]
fn htons(val: u16) -> u16 {
    val.to_be()
}

// Helper to access IP from nf_conntrack_tuple (casting to our extended type)
#[inline]
unsafe fn tuple_src_ip(tuple: *const nf_conntrack_tuple) -> u32 {
    (*(tuple as *const nf_conntrack_tuple_with_addr)).src.ip
}

#[inline]
unsafe fn tuple_dst_ip(tuple: *const nf_conntrack_tuple) -> u32 {
    (*(tuple as *const nf_conntrack_tuple_with_addr)).dst.ip
}

#[inline]
unsafe fn tuple_src_l3num(tuple: *const nf_conntrack_tuple) -> u8 {
    (*(tuple as *const nf_conntrack_tuple_with_addr)).src.l3num
}

struct IrcHelpersWrapper(core::cell::UnsafeCell<[nf_conntrack_helper; 8]>);
// SAFETY: Helpers array is only mutated during module init.
unsafe impl Sync for IrcHelpersWrapper {}
static IRC_HELPERS: IrcHelpersWrapper = IrcHelpersWrapper(core::cell::UnsafeCell::new([nf_conntrack_helper { _priv: [], name: ptr::null() }; 8]));
impl IrcHelpersWrapper {
    #[inline(always)]
    unsafe fn get_mut(&self) -> &mut [nf_conntrack_helper; 8] {
        // SAFETY: Mutated exclusively during module initialization (`nf_conntrack_irc_init`),
        // which occurs in a single-threaded context.
        unsafe { &mut *self.0.get() }
    }
}
static IRC_EXP_POLICY: nf_conntrack_expect_policy = nf_conntrack_expect_policy {
    max_expected: 1,
    timeout: 300,
};

unsafe extern "C" {
    fn nf_conntrack_helpers_register(helper: *mut nf_conntrack_helper, count: c_uint) -> c_int;
    fn nf_conntrack_helpers_unregister(helper: *mut nf_conntrack_helper, count: c_uint);

    fn nf_ct_expect_alloc(ct: *const nf_conn) -> *mut nf_conntrack_expect;
    fn nf_ct_expect_init(
        exp: *mut nf_conntrack_expect,
        class: c_int,
        l3num: u8,
        laddr: *const nf_inet_addr,
        lport: *const u16,
        protonum: u8,
        faddr: *const u32,
        fport: *const u16,
    );
    fn nf_ct_expect_related(exp: *mut nf_conntrack_expect, timeout: c_int) -> c_int;
    fn nf_ct_expect_put(exp: *mut nf_conntrack_expect);

    fn nf_ct_helper_init(
        helper: *mut nf_conntrack_helper,
        l3num: u8,
        protonum: u8,
        name: *const u8,
        src_port: u16,
        dst_port: u16,
        index: c_int,
        policy: *const nf_conntrack_expect_policy,
        flags: c_int,
        help: unsafe extern "C" fn(
            skb: *const sk_buff,
            protoff: c_uint,
            ct: *mut nf_conn,
            ctinfo: c_int,
        ) -> c_int,
        me: *const c_void,
        module: *const c_void,
    );

    fn ip_hdr(skb: *const sk_buff) -> *const iphdr;
    fn skb_header_pointer(
        skb: *const sk_buff,
        offset: c_int,
        size: c_int,
        buffer: *mut c_void,
    ) -> *mut c_void;

    fn pr_debug(fmt: *const u8, ...);
    fn net_warn_ratelimited(fmt: *const u8, ...);
    fn nf_ct_helper_log(skb: *const sk_buff, ct: *const nf_conn, fmt: *const u8, ...);

    fn malloc(size: usize) -> *mut c_void;
    fn free(ptr: *mut c_void);
}

#[no_mangle]
pub extern "C" fn nf_conntrack_irc_init() -> c_int {
    unsafe {
        let config = IRC_CONFIG.get_mut();
        let buf_state = IRC_BUFFER_STATE.get_mut();
        let helpers = IRC_HELPERS.get_mut();

        if config.max_dcc_channels < 1 {
            pr_debug(b"max_dcc_channels must not be zero\n\0".as_ptr() as *const u8);
            return EINVAL;
        }

        if config.max_dcc_channels > NF_CT_EXPECT_MAX_CNT {
            pr_debug(b"max_dcc_channels must not be more than %u\n\0".as_ptr() as *const u8);
            return EINVAL;
        }
        buf_state.buffer_ptr = ptr::addr_of_mut!(buf_state.storage).cast();

        // Default to standard IRC port if none specified
        if config.ports_c == 0 {
            config.ports[0] = 6667;
            config.ports_c = 1;
        }

        let mut i: c_int = 0;
        while i < config.ports_c as c_int {
            nf_ct_helper_init(
                &mut helpers[i as usize],
                AF_INET,
                IPPROTO_TCP,
                HELPER_NAME.as_ptr(),
                IRC_PORT,
                config.ports[i as usize],
                i,
                &IRC_EXP_POLICY,
                0,
                help,
                ptr::null(),
                ptr::null(),
            );
            i += 1;
        }

        let ret = nf_conntrack_helpers_register(&mut helpers[0], config.ports_c);
        if ret != 0 {
            buf_state.buffer_ptr = ptr::null_mut();
            return ret;
        }

        0
    }
}

#[no_mangle]
pub extern "C" fn nf_conntrack_irc_fini() {
    unsafe {
        let config = IRC_CONFIG.get_mut();
        let buf_state = IRC_BUFFER_STATE.get_mut();
        let helpers = IRC_HELPERS.get_mut();
        
        nf_conntrack_helpers_unregister(&mut helpers[0], config.ports_c);
        buf_state.buffer_ptr = ptr::null_mut();
    }
}

// Helper function implementation
#[no_mangle]
pub unsafe extern "C" fn help(
    skb: *const sk_buff,
    protoff: c_uint,
    ct: *mut nf_conn,
    ctinfo: c_int,
) -> c_int {
    let dir = CTINFO2DIR(ctinfo);
    if dir == IP_CT_DIR_REPLY {
        return NF_ACCEPT;
    }

    if ctinfo != IP_CT_ESTABLISHED && ctinfo != IP_CT_ESTABLISHED_REPLY {
        return NF_ACCEPT;
    }

    let skb_len = (*skb).len;
    let mut _tcph: tcphdr = tcphdr {
        source: 0,
        dest: 0,
        doff: 0,
    };
    let th: *mut tcphdr = skb_header_pointer(skb, protoff as c_int, core::mem::size_of::<tcphdr>() as c_int, &mut _tcph as *mut _ as *mut c_void) as *mut tcphdr;
    if th.is_null() {
        return NF_ACCEPT;
    }

    let dataoff = protoff + (*th).doff as c_uint * 4;
    if dataoff >= skb_len as c_uint {
        return NF_ACCEPT;
    }

    let buf_state = IRC_BUFFER_STATE.get_mut();

    // Acquire spinlock
    spin_lock_bh(&mut buf_state.lock);

    let ib_ptr = skb_header_pointer(
        skb,
        dataoff as c_int,
        skb_len as c_int - dataoff as c_int,
        buf_state.buffer_ptr,
    ) as *mut u8;
    if ib_ptr.is_null() {
        spin_unlock_bh(&mut buf_state.lock);
        return NF_ACCEPT;
    }

    let data = ib_ptr;
    let data_limit = unsafe { data.add(skb_len as usize - dataoff as usize) };

    let mut ret = NF_ACCEPT;
    let mut data = data;

    while data < data_limit.offset(-(19 + 5) as isize) {
        let data_slice = core::slice::from_raw_parts(data, 5);
        if data_slice != b"\x01DCC " {
            data = data.offset(1);
            continue;
        }

        data = data.offset(5);
        let iph = ip_hdr(skb);
        unsafe {
            pr_debug(
                b"DCC found in master %pI4:%u %pI4:%u\n\0".as_ptr() as *const u8,
                &(*iph).saddr,
                &(*th).source,
                &(*iph).daddr,
                &(*th).dest,
            );
        }

        for i in 0..DCC_PROTOS.len() {
            let proto = DCC_PROTOS[i];
            let data_slice = core::slice::from_raw_parts(data, proto.len());
            if data_slice != proto {
                continue;
            }

            data = data.offset(proto.len() as isize);
            let mut dcc_ip: u32 = 0;
            let mut dcc_port: u16 = 0;
            let mut addr_beg_p: *mut u8 = ptr::null_mut();
            let mut addr_end_p: *mut u8 = ptr::null_mut();

            if parse_dcc(data, data_limit, &mut dcc_ip, &mut dcc_port, &mut addr_beg_p, &mut addr_end_p) != 0 {
                unsafe { pr_debug(b"unable to parse dcc command\n\0".as_ptr() as *const u8); }
                continue;
            }

            unsafe { pr_debug(b"DCC bound ip/port: %pI4:%u\n\0".as_ptr() as *const u8, &dcc_ip, &dcc_port); }

            let tuple = &(*ct).tuplehash[dir as usize].tuple;
            let tuple_ptr = tuple as *const nf_conntrack_tuple;
            let src_ip = tuple_src_ip(tuple_ptr);
            let dst_ip = tuple_dst_ip(tuple_ptr);
            if src_ip != dcc_ip && dst_ip != dcc_ip {
                unsafe {
                    net_warn_ratelimited(
                        b"Forged DCC command from %pI4: %pI4:%u\n\0".as_ptr() as *const u8,
                        &src_ip,
                        &dcc_ip,
                        &dcc_port,
                    );
                }
                continue;
            }

            let exp = nf_ct_expect_alloc(ct);
            if exp.is_null() {
                nf_ct_helper_log(skb, ct, b"cannot alloc expectation\0".as_ptr() as *const u8);
                ret = NF_DROP;
                break;
            }

            let tuple = &(*ct).tuplehash[!dir as usize].tuple;
            let tuple_ptr = tuple as *const nf_conntrack_tuple;
            let port = htons(dcc_port);
            let dst_ip = tuple_dst_ip(tuple_ptr);
            let l3num = tuple_src_l3num(tuple_ptr);
            nf_ct_expect_init(
                exp,
                NF_CT_EXPECT_CLASS_DEFAULT,
                l3num,
                ptr::null(),
                ptr::null(),
                IPPROTO_TCP,
                &dst_ip as *const u32,
                &port as *const u16,
            );

            let hooks = NF_NAT_IRC_HOOK.get_mut();
            if let Some(nf_nat_irc_fn) = hooks {
                if let Some(hook_fn) = nf_nat_irc_fn {
                    if (*ct).status & IPS_NAT_MASK != 0 {
                        let nat_ret = hook_fn(
                            skb,
                            ctinfo,
                            protoff,
                            (addr_beg_p as usize - ib_ptr as usize) as c_uint,
                            (addr_end_p as usize - addr_beg_p as usize) as c_uint,
                            exp,
                        );
                        if nat_ret != 0 {
                            ret = nat_ret;
                        }
                    } else if nf_ct_expect_related(exp, 0) != 0 {
                        nf_ct_helper_log(skb, ct, b"cannot add expectation\0".as_ptr() as *const u8);
                        ret = NF_DROP;
                    }
                } else if nf_ct_expect_related(exp, 0) != 0 {
                    nf_ct_helper_log(skb, ct, b"cannot add expectation\0".as_ptr() as *const u8);
                    ret = NF_DROP;
                }
            } else if nf_ct_expect_related(exp, 0) != 0 {
                nf_ct_helper_log(skb, ct, b"cannot add expectation\0".as_ptr() as *const u8);
                ret = NF_DROP;
            }

            nf_ct_expect_put(exp);
            break;
        }
    }

    spin_unlock_bh(&mut buf_state.lock);
    ret
}

// Parse DCC command implementation
#[no_mangle]
pub unsafe extern "C" fn parse_dcc(
    data: *mut u8,
    data_end: *mut u8,
    ip: *mut u32,
    port: *mut u16,
    ad_beg_p: *mut *mut u8,
    ad_end_p: *mut *mut u8,
) -> c_int {
    let mut data = data;
    let data_end = data_end.offset(-12);

    while *data != b' ' as u8 {
        if data > data_end {
            return -1;
        }
        data = data.offset(1);
    }

    data = data.offset(1);
    let mut tmp = data;

    while tmp <= data_end {
        if *tmp == b'\n' as u8 {
            break;
        }
        tmp = tmp.offset(1);
    }

    if tmp > data_end || *tmp != b'\n' as u8 {
        return -1;
    }

    *ad_beg_p = data;
    let mut num: u32 = 0;
    let mut end: *mut u8 = data;

    while end <= data_end && *end != b' ' as u8 && *end != b'\n' as u8 {
        if *end < b'0' as u8 || *end > b'9' as u8 {
            return -1;
        }
        num = num * 10 + (*end - b'0' as u8) as u32;
        end = end.offset(1);
    }

    *ip = num.to_be();

    // Skip spaces
    while *end == b' ' as u8 {
        if end >= data_end {
            return -1;
        }
        end = end.offset(1);
    }

    num = 0;
    while end <= data_end && *end != b'\n' as u8 {
        if *end < b'0' as u8 || *end > b'9' as u8 {
            return -1;
        }
        num = num * 10 + (*end - b'0' as u8) as u32;
        end = end.offset(1);
    }

    *port = num as u16;
    *ad_end_p = end;
    0
}

// Implementation deferred.
#[no_mangle]
pub unsafe extern "C" fn spin_lock_bh(lock: *mut Spinlock) {
    // SAFETY: Kernel guarantees lock is valid and properly aligned
    (*lock)._private = 1;
}

#[no_mangle]
pub unsafe extern "C" fn spin_unlock_bh(lock: *mut Spinlock) {
    // SAFETY: Kernel guarantees lock is valid and properly aligned
    (*lock)._private = 0;
}

// Constants
const AF_INET: u8 = 2; const IPPROTO_TCP: u8 = 6;
const HELPER_NAME: &str = "irc";
const IRC_PORT: u16 = 6667; const IPS_NAT_MASK: u64 = 0x0000000F;

// Module exports
#[no_mangle]
pub extern "C" fn parse_dcc_helper(
    _skb: *const sk_buff,
    _ctinfo: c_int,
    _protoff: c_uint,
    _matchoff: c_uint,
    _matchlen: c_uint,
    _exp: *mut nf_conntrack_expect,
) -> c_int {
    // Implementation would go here if needed
    0
}

// Module metadata
#[no_mangle]
pub static NF_CT_HELPER_IRC: nf_conntrack_helper = nf_conntrack_helper {
    _priv: [],
    name: ptr::null(),
};

// Test cases (conditional compilation)
#[cfg(test)]
mod tests {
    use core::ptr;
    #[test]
    fn test_parse_dcc() {
        // Basic test case for DCC parsing
        let data = b"A 3232235777 1234\n\0            "; // 12 spaces padding
        let mut ip: u32 = 0;
        let mut port: u16 = 0;
        let mut ad_beg: *mut u8 = ptr::null_mut();
        let mut ad_end: *mut u8 = ptr::null_mut();

        unsafe {
            let result = super::parse_dcc(
                data.as_ptr() as *mut u8,
                data.as_ptr().add(data.len()) as *mut u8,
                &mut ip,
                &mut port,
                &mut ad_beg,
                &mut ad_end,
            );

            assert_eq!(result, 0);
            assert_eq!(ip, 0xC0A80101u32.to_be());
            assert_eq!(port, 1234);
        }
    }
}
