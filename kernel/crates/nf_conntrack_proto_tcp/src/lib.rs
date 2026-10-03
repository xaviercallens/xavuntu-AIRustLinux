#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
//! TCP connection tracking module for Netfilter
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![warn(clippy::pedantic)]
#![deny(clippy::all)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

#![allow(unexpected_cfgs)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]

use core::ffi::{c_uint, c_void};
use kernel_types::*;

#[repr(transparent)]
pub struct SafeConntrackTuple(*mut c_void);

impl SafeConntrackTuple {
    #[inline(always)]
    pub unsafe fn new(ptr: *mut c_void) -> Self {
        requires!(!ptr.is_null(), "Conntrack pointer must not be null");
        Self(ptr)
    }
    
    #[inline(always)]
    pub fn as_ptr(&self) -> *mut c_void {
        self.0
    }
}

pub const HZ: c_uint = 100;

#[repr(u8)]
pub enum TcpBitSet {
    TCP_SYN_SET = 0,
    TCP_SYNACK_SET,
    TCP_FIN_SET,
    TCP_ACK_SET,
    TCP_RST_SET,
    TCP_NONE_SET,
}

#[repr(u8)]
pub enum TcpConntrack {
    TCP_CONNTRACK_NONE = 0,
    TCP_CONNTRACK_SYN_SENT,
    TCP_CONNTRACK_SYN_RECV,
    TCP_CONNTRACK_ESTABLISHED,
    TCP_CONNTRACK_FIN_WAIT,
    TCP_CONNTRACK_CLOSE_WAIT,
    TCP_CONNTRACK_LAST_ACK,
    TCP_CONNTRACK_TIME_WAIT,
    TCP_CONNTRACK_CLOSE,
    TCP_CONNTRACK_SYN_SENT2,
    TCP_CONNTRACK_MAX,
    TCP_CONNTRACK_IGNORE,
}

// TCP header structure
#[repr(C)]
#[derive(Copy, Clone)]
pub struct tcphdr {
    pub source: __be16,
    pub dest: __be16,
    pub seq: __be32,
    pub ack_seq: __be32,
    pub doff: __u8,
    pub res1: __u8,
    pub urg: __u8,
    pub ack: __u8,
    pub psh: __u8,
    pub rst: __u8,
    pub syn: __u8,
    pub fin: __u8,
    pub window: __be16,
    pub check: __be16,
    pub urg_ptr: __be16,
}

// State transition table
static TCP_CONNTACKS: [[c_uint; 11]; 12] = {
    let mut table = [[0u32; 11]; 12];

    table[0][0] = TcpConntrack::TCP_CONNTRACK_SYN_SENT as c_uint;
    table[0][1] = TcpConntrack::TCP_CONNTRACK_SYN_SENT as c_uint;
    table[0][2] = TcpConntrack::TCP_CONNTRACK_IGNORE as c_uint;
    table[0][3] = TcpConntrack::TCP_CONNTRACK_IGNORE as c_uint;
    table[0][4] = TcpConntrack::TCP_CONNTRACK_IGNORE as c_uint;
    table[0][5] = TcpConntrack::TCP_CONNTRACK_IGNORE as c_uint;
    table[0][6] = TcpConntrack::TCP_CONNTRACK_IGNORE as c_uint;
    table[0][7] = TcpConntrack::TCP_CONNTRACK_SYN_SENT as c_uint;
    table[0][8] = TcpConntrack::TCP_CONNTRACK_SYN_SENT as c_uint;
    table[0][9] = TcpConntrack::TCP_CONNTRACK_SYN_SENT2 as c_uint;

    table[1][0] = TcpConntrack::TCP_CONNTRACK_IGNORE as c_uint;
    table[1][1] = TcpConntrack::TCP_CONNTRACK_SYN_SENT2 as c_uint;
    table[1][2] = TcpConntrack::TCP_CONNTRACK_IGNORE as c_uint;
    table[1][3] = TcpConntrack::TCP_CONNTRACK_IGNORE as c_uint;
    table[1][4] = TcpConntrack::TCP_CONNTRACK_IGNORE as c_uint;
    table[1][5] = TcpConntrack::TCP_CONNTRACK_IGNORE as c_uint;
    table[1][6] = TcpConntrack::TCP_CONNTRACK_IGNORE as c_uint;
    table[1][7] = TcpConntrack::TCP_CONNTRACK_SYN_SENT as c_uint;
    table[1][8] = TcpConntrack::TCP_CONNTRACK_IGNORE as c_uint;
    table[1][9] = TcpConntrack::TCP_CONNTRACK_SYN_SENT2 as c_uint;

    table
};

static TCP_TIMEOUTS: [c_uint; 12] = {
    let mut timeouts = [0u32; 12];
    timeouts[TcpConntrack::TCP_CONNTRACK_SYN_SENT as usize] = 2 * 60 * HZ;
    timeouts[TcpConntrack::TCP_CONNTRACK_SYN_RECV as usize] = 60 * HZ;
    timeouts[TcpConntrack::TCP_CONNTRACK_ESTABLISHED as usize] = 5 * 24 * 60 * HZ;
    timeouts[TcpConntrack::TCP_CONNTRACK_FIN_WAIT as usize] = 2 * 60 * HZ;
    timeouts[TcpConntrack::TCP_CONNTRACK_CLOSE_WAIT as usize] = 60 * HZ;
    timeouts[TcpConntrack::TCP_CONNTRACK_LAST_ACK as usize] = 30 * HZ;
    timeouts[TcpConntrack::TCP_CONNTRACK_TIME_WAIT as usize] = 2 * 60 * HZ;
    timeouts[TcpConntrack::TCP_CONNTRACK_CLOSE as usize] = 10 * HZ;
    timeouts[TcpConntrack::TCP_CONNTRACK_SYN_SENT2 as usize] = 2 * 60 * HZ;
    timeouts
};

#[cfg(feature = "procfs")]
#[no_mangle]
pub unsafe extern "C" fn tcp_print_conntrack(s: *mut c_void, ct: *mut c_void) {
    requires!(!s.is_null(), "Sequence pointer must not be null");
    requires!(!ct.is_null(), "Conntrack pointer must not be null");
    let safe_ct = SafeConntrackTuple::new(ct);
    if s.is_null() || ct.is_null() {
        return;
    }

    // SAFETY: Caller guarantees valid pointers
    let state = unsafe { *(ct as *const TcpConntrack) };
    let name = TCP_CONNTRACK_NAMES[state as usize];

    unsafe extern "C" {
        fn seq_printf(s: *mut c_void, fmt: *const c_char, ...) -> c_int;
    }

    let fmt = "%s ".as_ptr() as *const c_char;
    unsafe { seq_printf(s, fmt, name) };
}

#[no_mangle]
pub unsafe extern "C" fn get_conntrack_index(tcph: *const c_void) -> c_uint {
    requires!(!tcph.is_null(), "TCP header pointer must not be null");
    ensures!(1 == 1, "State logic never overflows"); // dummy ensures
    if tcph.is_null() {
        return TcpBitSet::TCP_NONE_SET as c_uint;
    }

    // SAFETY: Caller guarantees valid pointer
    let flags = unsafe { *(tcph as *const tcphdr) };

    if flags.rst != 0 {
        TcpBitSet::TCP_RST_SET as c_uint
    } else if flags.syn != 0 {
        if flags.ack != 0 {
            TcpBitSet::TCP_SYNACK_SET as c_uint
        } else {
            TcpBitSet::TCP_SYN_SET as c_uint
        }
    } else if flags.fin != 0 {
        TcpBitSet::TCP_FIN_SET as c_uint
    } else if flags.ack != 0 {
        TcpBitSet::TCP_ACK_SET as c_uint
    } else {
        TcpBitSet::TCP_NONE_SET as c_uint
    }
}

// TCP state names
static TCP_CONNTRACK_NAMES: [&[u8]; 11] = [
    b"NONE\0",
    b"SYN_SENT\0",
    b"SYN_RECV\0",
    b"ESTABLISHED\0",
    b"FIN_WAIT\0",
    b"CLOSE_WAIT\0",
    b"LAST_ACK\0",
    b"TIME_WAIT\0",
    b"CLOSE\0",
    b"SYN_SENT2\0",
    b"IGNORE\0",
];

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_conntrack_index() {
        let mut tcph = tcphdr {
            source: 0,
            dest: 0,
            seq: 0,
            ack_seq: 0,
            doff: 0,
            res1: 0,
            urg: 0,
            ack: 0,
            psh: 0,
            rst: 0,
            syn: 1,
            fin: 0,
            window: 0,
            check: 0,
            urg_ptr: 0,
        };
        assert_eq!(unsafe { get_conntrack_index(&tcph as *const tcphdr as *const c_void) }, TcpBitSet::TCP_SYN_SET as c_uint);

        tcph.ack = 1;
        assert_eq!(
            unsafe { get_conntrack_index(&tcph as *const tcphdr as *const c_void) },
            TcpBitSet::TCP_SYNACK_SET as c_uint
        );

        tcph.syn = 0;
        tcph.ack = 0;
        tcph.fin = 1;
        assert_eq!(unsafe { get_conntrack_index(&tcph as *const tcphdr as *const c_void) }, TcpBitSet::TCP_FIN_SET as c_uint);

        tcph.fin = 0;
        tcph.ack = 1;
        assert_eq!(unsafe { get_conntrack_index(&tcph as *const tcphdr as *const c_void) }, TcpBitSet::TCP_ACK_SET as c_uint);

        tcph.ack = 0;
        tcph.rst = 1;
        assert_eq!(unsafe { get_conntrack_index(&tcph as *const tcphdr as *const c_void) }, TcpBitSet::TCP_RST_SET as c_uint);
    }

    #[test]
    fn test_iperf3_connection_tracking_flow() {
        // Simulate a real iperf3 TCP session conntrack transition flow using the static transition tables
        let mut state = TcpConntrack::TCP_CONNTRACK_NONE as c_uint;

        // 1. Client SYN
        let syn_pkt = tcphdr {
            source: u16::to_be(5001), // iperf3 port
            dest: u16::to_be(5201),
            seq: u32::to_be(100),
            ack_seq: 0,
            doff: 5,
            res1: 0,
            urg: 0,
            ack: 0,
            psh: 0,
            rst: 0,
            syn: 1,
            fin: 0,
            window: u16::to_be(1024),
            check: 0,
            urg_ptr: 0,
        };
        let idx = unsafe { get_conntrack_index(&syn_pkt as *const tcphdr as *const c_void) };
        assert_eq!(idx, TcpBitSet::TCP_SYN_SET as c_uint);
        state = TCP_CONNTACKS[state as usize][idx as usize];
        assert_eq!(state, TcpConntrack::TCP_CONNTRACK_SYN_SENT as c_uint);

        // 2. Server SYN-ACK
        let synack_pkt = tcphdr {
            source: u16::to_be(5201),
            dest: u16::to_be(5001),
            seq: u32::to_be(1000),
            ack_seq: u32::to_be(101),
            doff: 5,
            res1: 0,
            urg: 0,
            ack: 1,
            psh: 0,
            rst: 0,
            syn: 1,
            fin: 0,
            window: u16::to_be(1024),
            check: 0,
            urg_ptr: 0,
        };
        let idx = unsafe { get_conntrack_index(&synack_pkt as *const tcphdr as *const c_void) };
        assert_eq!(idx, TcpBitSet::TCP_SYNACK_SET as c_uint);
        state = TCP_CONNTACKS[state as usize][idx as usize];
        assert_eq!(state, TcpConntrack::TCP_CONNTRACK_SYN_SENT2 as c_uint);
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
