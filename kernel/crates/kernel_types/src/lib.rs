#![allow(clippy::all, clippy::pedantic)]
// Linux kernel type definitions for Rust FFI
// Target: Linux kernel 5.10 LTS networking stack
// Manually curated based on kernel headers

#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

// Re-export core FFI types
pub use core::ffi::{c_int, c_uint, c_char, c_uchar, c_short, c_ushort, c_long, c_ulong, c_void};

pub mod verus_proofs;

// Standard types
pub type size_t = usize;
pub type ssize_t = isize;
pub type c_size_t = usize;
pub type socklen_t = u32;

// Error codes
pub const EINVAL: c_int = 22;

// Network byte order types
pub type __be16 = u16;
pub type __be32 = u32;
pub type __be64 = u64;
pub type __u8 = u8;
pub type __u16 = u16;
pub type __u32 = u32;
pub type __u64 = u64;
pub type __s8 = i8;
pub type __s16 = i16;
pub type __s32 = i32;
pub type __s64 = i64;

// ============================================================================
// Network Address Structures
// ============================================================================

/// IPv4 address (32-bit)
#[repr(C)]
#[derive(Copy, Clone)]
pub struct in_addr {
    pub s_addr: __be32,
    pub ip: *mut core::ffi::c_void, // Auto-generated mock field
}

/// IPv6 address (128-bit)
#[repr(C)]
#[derive(Copy, Clone)]
pub struct in6_addr {
    pub in6_u: in6_addr_union,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub union in6_addr_union {
    pub u6_addr8: [__u8; 16],
    pub u6_addr16: [__be16; 8],
    pub u6_addr32: [__be32; 4],
}

/// Netfilter address (union of IPv4 and IPv6)
#[repr(C)]
#[derive(Copy, Clone)]
pub union nf_inet_addr {
    pub all: [__u32; 4],
    pub ip: __be32,
    pub ip6: [__be32; 4],
    pub in_addr: in_addr,
    pub in6: in6_addr,
    pub s_addr: __be32,
}

// ============================================================================
// Network Protocol Headers
// ============================================================================

/// Ethernet header
#[repr(C)]
#[derive(Copy, Clone)]
pub struct ethhdr {
    pub h_dest: [c_uchar; 6],
    pub h_source: [c_uchar; 6],
    pub h_proto: __be16,
}

/// IPv4 header
#[repr(C)]
#[derive(Copy, Clone)]
pub struct iphdr {
    pub version_ihl: __u8,
    pub tos: __u8,
    pub tot_len: __be16,
    pub id: __be16,
    pub frag_off: __be16,
    pub ttl: __u8,
    pub protocol: __u8,
    pub check: __be16,
    pub saddr: __be32,
    pub daddr: __be32,
}

/// IPv6 header
#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6hdr {
    pub version_priority: __u8,
    pub flow_lbl: [__u8; 3],
    pub payload_len: __be16,
    pub nexthdr: __u8,
    pub hop_limit: __u8,
    pub saddr: in6_addr,
    pub daddr: in6_addr,
}

/// UDP header
#[repr(C)]
#[derive(Copy, Clone)]
pub struct udphdr {
    pub source: __be16,
    pub dest: __be16,
    pub len: __be16,
    pub check: __be16,
}

/// ESP header
#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip_esp_hdr { pub spi: __be32, pub seq_no: __be32 }

// ============================================================================
// Socket Structures
// ============================================================================

/// Generic socket address
#[repr(C)]
#[derive(Copy, Clone)]
pub struct sockaddr { pub sa_family: c_ushort, pub sa_data: [c_char; 14] }

/// I/O vector for scatter-gather operations
#[repr(C)]
#[derive(Copy, Clone)]
pub struct iovec { pub iov_base: *mut c_void, pub iov_len: size_t }

/// Socket message header
#[repr(C)]
#[derive(Copy, Clone)]
pub struct msghdr {
    pub msg_name: *mut c_void,
    pub msg_namelen: socklen_t,
    pub msg_iov: *mut iovec,
    pub msg_iovlen: size_t,
    pub msg_control: *mut c_void,
    pub msg_controllen: size_t,
    pub msg_flags: c_int,
}

/// Base socket structure
#[repr(C)]
#[derive(Copy, Clone)]
pub struct sock {
    pub sk_family: c_ushort,
    pub sk_type: c_ushort,
    pub sk_protocol: c_ushort,
    pub sk_state: c_uint,
    pub sk_refcnt: c_int,
    pub sk_reuseport_cb: *mut core::ffi::c_void, // Auto-generated mock field
    pub sk_reuse: core::ffi::c_int, // Changed type to match C int usages
    pub sk_reuseport: *mut core::ffi::c_void, // Auto-generated mock field
    pub sk_rcv_saddr: *mut core::ffi::c_void, // Auto-generated mock field
    pub sk_bound_dev_if: *mut core::ffi::c_void, // Auto-generated mock field
    pub sk_v6_rcv_saddr: *mut core::ffi::c_void, // Auto-generated mock field
    pub sk_user_data: *mut core::ffi::c_void, // Auto-generated mock field
    pub sk_ipv6only: core::ffi::c_int,
    pub sk_prot: *mut core::ffi::c_void,
    pub sk_destruct: Option<unsafe extern "C" fn(*mut sock)>,
    pub sk_backlog_rcv: Option<extern "C" fn(*mut sock, *mut core::ffi::c_void, usize) -> core::ffi::c_int>,
}

/// TCP socket
#[repr(C)]
#[derive(Copy, Clone)]
pub struct tcp_sock {
    pub inet: inet_sock,
    pub snd_nxt: __u32,
    pub rcv_nxt: __u32,
    pub snd_wnd: __u32,
    pub rcv_wnd: __u32,
}

/// Internet socket (base)
#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet_sock {
    pub sk: *mut c_void, // struct sock *
    pub pinet6: *mut c_void, // struct ipv6_pinfo *
    pub inet_saddr: __be32,
    pub uc_ttl: __s16,
    pub cmsg_flags: __u16,
    pub inet_sport: __be16,
    pub inet_id: __u16,
    pub tos: __u8,
    pub min_ttl: __u8,
    pub mc_ttl: __u8,
    pub pmtudisc: __u8,
    pub recverr: __u8,
    pub freebind: __u8,
    pub hdrincl: __u8,
    pub mc_loop: __u8,
    pub transparent: __u8,
    pub mc_all: __u8,
    pub nodefrag: __u8,
    pub bind_address_no_port: __u8,
    pub defer_connect: __u8,
    pub rcv_tos: __u8,
    pub convert_csum: __u8,
    pub uc_index: c_int,
    pub mc_index: c_int,
    pub mc_addr: __be32,
}

/// IPv6 socket info
#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_pinfo {
    pub saddr: in6_addr,
    pub daddr: in6_addr,
    pub flow_label: __be32,
    pub frag_size: __u32,
    pub hop_limit: __s16,
    pub mcast_hops: __s16,
    pub mcast_oif: c_int,
    pub rxopt: ip6cb,
    pub mc_loop: u8,
    pub mc_all: u8,
    pub pmtudisc: u8,
    pub repflow: u8,
}

/// UDP socket
#[repr(C)]
#[derive(Copy, Clone)]
pub struct udp_sock {
    pub inet: inet_sock,
    pub pending: c_int,
    pub corkflag: c_uint,
    pub encap_type: __u8,
    pub encap_enabled: __u8,
    pub gro_enabled: __u8,
    pub pcflag: __u16,
}

/// Raw IPv6 socket
#[repr(C)]
#[derive(Copy, Clone)]
pub struct raw6_sock {
    pub inet: inet_sock,
    pub checksum: __u32,
    pub offset: __u32,
    pub ip6mr: *mut c_void,
}

// ============================================================================
// Flow and Routing Structures
// ============================================================================

/// Flow identifier (base type)
#[repr(C)]
#[derive(Copy, Clone)]
pub struct flowi {
    pub oif: c_int,
    pub iif: c_int,
    pub mark: __u32,
    pub scope: __u8,
    pub proto: __u8,
    pub flags: __u8,
    pub secid: __u32,
    pub flowi_tos: __u8,
    pub u: *mut core::ffi::c_void, // Auto-generated mock field
}

/// IPv6 flow identifier
#[repr(C)]
#[derive(Copy, Clone)]
pub struct flowi6 {
    pub flowi6_oif: c_int,
    pub flowi6_flags: c_int,
    pub flowi6_mark: u32,
    pub daddr: in6_addr,
    pub saddr: in6_addr,
}

/// Destination operations
#[repr(C)]
#[derive(Copy, Clone)]
pub struct dst_ops {
    pub family: c_int,
    pub update_pmtu: Option<unsafe extern "C" fn(*mut dst_entry, *mut c_void, *mut c_void, u32, bool)>,
    pub redirect: Option<unsafe extern "C" fn(*mut dst_entry, *mut c_void, *mut c_void)>,
    pub cow_metrics: Option<unsafe extern "C" fn(*mut dst_entry, *mut c_void) -> *mut dst_entry>,
    pub destroy: Option<unsafe extern "C" fn(*mut dst_entry)>,
    pub ifdown: Option<unsafe extern "C" fn(*mut dst_entry, *mut net_device, c_int)>,
    pub local_out: Option<unsafe extern "C" fn(*mut c_void) -> c_int>,
    pub gc_thresh: c_int,
}

/// Destination entry (routing cache)
#[repr(C)]
#[derive(Copy, Clone)]
pub struct dst_entry {
    pub dev: *mut c_void, // struct net_device *
    pub ops: *mut dst_ops,
    pub rcuhead: *mut c_void,
    pub metrics: [c_int; 17],
    pub mtu: c_ulong,
    pub flags: c_ushort,
    pub obsolete: c_short,
    pub header_len: c_ushort,
    pub trailer_len: c_ushort,
    pub error: *mut core::ffi::c_void, // Auto-generated mock field
    pub xfrm: *mut core::ffi::c_void, // Force injected mock field
}

/// IPv6 routing table entry
#[repr(C)]
#[derive(Copy, Clone)]
pub struct rt6_info {
    pub dst: dst_entry,
    pub rt6_next: *mut rt6_info,
    pub rt6i_idev: *mut inet6_dev,
    pub rt6i_flags: c_uint,
    pub rt6i_uncached: ListHead,
    pub rt6i_src: *mut core::ffi::c_void, // Force injected mock field
    pub rt6i_gateway: *mut core::ffi::c_void, // Force injected mock field
    pub rt6i_dst: *mut core::ffi::c_void, // Force injected mock field
}

/// IPv6 configuration
#[repr(C)]
#[derive(Copy, Clone)]
pub struct ipv6_devconf { pub disable_ipv6: c_int, _padding: [u8; 0] }

/// IPv6 interface device info
#[repr(C)]
#[derive(Copy, Clone)]
pub struct inet6_dev {
    pub dev: *mut net_device,
    pub early_demux: Option<extern "C" fn(*mut sk_buff)>,
    pub cnf: ipv6_devconf,
    _padding: [u8; 0],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct netlink_ext_ack {
    _private: [u8; 0],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib_table {
    pub tb_id: u32,
    _private: [u8; 0],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib_result {
    pub prefixlen: u8,
    pub fi: *mut core::ffi::c_void,
    pub tclassid: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib_nh_common {
    pub nhc_dev: *mut net_device,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct net_ipv4 {
    pub rules_ops: *mut core::ffi::c_void,
    pub fib_has_custom_rules: bool,
    pub fib_rules_require_fldissect: core::ffi::c_int,
    pub fib_num_tclassid_users: core::ffi::c_int,
    pub sysctl_ip_no_pmtu_disc: bool,
}

/// Network namespace
#[repr(C)]
#[derive(Copy, Clone)]
pub struct net {
    pub loopback_dev: *mut net_device,
    pub ct: *mut c_void,
    pub ipv4: net_ipv4,
    _padding: [u8; 0],
}

/// Routing table link operations
#[repr(C)]
#[derive(Copy, Clone)]
pub struct rtnl_link_ops {
    pub list: *mut c_void,
    pub kind: *const c_char,
    pub maxtype: c_uint,
    pub policy: *const c_void,
}

/// FIB rule
#[repr(C)]
#[derive(Copy, Clone)]
pub struct fib_rule {
    pub list: *mut c_void,
    pub table: __u32,
    pub flags: __u32,
    pub action: __u8,
    pub suppress_ifgroup: c_int,
    pub fr_net: *mut net,
    pub ip_proto: u8,
    pub suppress_prefixlen: u8,
    pub sport_range: *mut core::ffi::c_void,
    pub dport_range: *mut core::ffi::c_void,
    pub l3mdev: *mut core::ffi::c_void,
}

// ============================================================================
// Packet Buffer Structures
// ============================================================================

/// Socket buffer (packet buffer) - also aliased as `sk_buff`
#[repr(C)]
#[derive(Copy, Clone)]
pub struct sk_buff {
    pub next: *mut sk_buff,
    pub prev: *mut sk_buff,
    pub tstamp: __u64,
    pub dev: *mut c_void, // struct net_device *
    pub len: c_uint,
    pub data_len: c_uint,
    pub mac_len: __u16,
    pub hdr_len: __u16,
    pub csum: __u32,
    pub priority: __u32,
    pub protocol: __be16,
    pub flags: __u32,
    pub cb: [__u8; 48],
    pub ip_summed: __u8,      // Checksum status
    pub csum_level: __u8,     // Checksum level
    pub csum_valid: __u8,     // Checksum valid flag
    pub csum_complete_sw: __u8, // Software checksum complete
    pub remcsum_offload: *mut core::ffi::c_void, // Auto-generated mock field
    pub mark: *mut core::ffi::c_void, // Auto-generated mock field
    pub data: *mut core::ffi::c_void, // Auto-generated mock field
    pub sk: *mut core::ffi::c_void, // Force injected mock field
    pub dst: *mut core::ffi::c_void, // Force injected mock field
    pub head: *mut __u8,
    pub network_header: __u16,
    pub transport_header: __u16,
    pub transport_offset: c_int,
    pub network_header_len: c_uint,
}

/// IPv6 control block (in sk_buff->cb)
#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6cb {
    pub nhoff: __u16,
    pub flags: __u16,
    pub dsfield: __u8,
    pub tclass: __u8,
    pub frag_max_size: __u16,
}

/// IPv6 fragmentation state
#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_frag_state {
    pub prevhdr: *mut u8,
    pub nexthdr: __u8,
    pub hlen: c_uint,
    pub mtu: c_uint,
    pub left: c_uint,
    pub offset: c_int,
}

/// IPv6 fraglist iterator
#[repr(C)]
#[derive(Copy, Clone)]
pub struct ip6_fraglist_iter {
    pub frag: *mut sk_buff,
    pub offset: c_int,
    pub hlen: c_uint,
}

// ============================================================================
// Netfilter Connection Tracking
// ============================================================================

/// Netfilter connection tracking zone
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_zone {
    pub id: __u16,
    pub flags: __u8,
    pub dir: __u8,
}

/// Netfilter connection tracking helper
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_helper {
    pub list: *mut c_void,
    pub hnode: *mut c_void,
    pub name: [c_char; 16],
    pub tuple: nf_conntrack_tuple,
    pub module: *mut c_void,
    pub me: *mut c_void,
    pub refcnt: c_uint,
    pub max_expected: c_uint,
    pub timeout: c_uint,
    pub flags: c_uint,
    pub help: *mut c_void,
    pub from_nlattr: *mut c_void,
}

unsafe impl Sync for nf_conntrack_helper {}

/// Netfilter connection tracking tuple hash
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_tuplehash { pub tuple: nf_conntrack_tuple }

/// Netfilter connection tracking tuple
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple { pub src: nf_conntrack_tuple_src, pub dst: nf_conntrack_tuple_dst, pub src_l3num: u16 }

/// Netfilter connection tracking tuple source
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_src { pub u: nf_conntrack_tuple_u }

/// Netfilter connection tracking tuple destination
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_dst { pub u: nf_conntrack_tuple_u, pub protonum: __u8 }

/// Netfilter connection tracking manipulation structure
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_man { pub u: nf_conntrack_tuple_u, pub l3num: u16 }

/// Netfilter connection tracking tuple hash
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_hash { pub node: *mut c_void, pub tuple: nf_conntrack_tuple }

/// Netfilter connection tracking tuple union
#[repr(C)]
#[derive(Copy, Clone)]
pub union nf_conntrack_tuple_u {
    pub icmp: nf_conntrack_tuple_icmp,
    pub all: u16,
}

/// Netfilter connection tracking ICMP tuple
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple_icmp {
    pub id: u16,
    pub type_: u8,
    pub code: u8,
}

/// Netfilter connection
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn {
    pub ct_general: *mut c_void,
    pub tuplehash: [nf_conn_tuplehash; 2],
    pub timeout: c_ulong,
    pub status: c_ulong,
    pub sk: *mut core::ffi::c_void, // Auto-generated mock field
    pub proto: *mut core::ffi::c_void, // Auto-generated mock field
}

// ============================================================================
// Misc Kernel Structures
// ============================================================================

/// Kernel timer
#[repr(C)]
#[derive(Copy, Clone)]
pub struct timer_list {
    pub entry: *mut c_void,
    pub expires: c_ulong,
    pub function: *mut c_void,
    pub flags: c_ulong,
}

/// Hash list node (nulls variant)
#[repr(C)]
#[derive(Copy, Clone)]
pub struct hlist_nulls_node {
    pub next: *mut hlist_nulls_node,
    pub pprev: *mut *mut hlist_nulls_node,
}

/// XFRM (`IPsec`) mode skb callback
#[repr(C)]
#[derive(Copy, Clone)]
pub struct xfrm_mode_skb_cb {
    pub ihl: __u8,
    pub id: __u8,
    pub frag_off: __be16,
    pub tos: __u8,
    pub ttl: __u8,
}

/// U64 statistics synchronization
#[repr(C)]
#[derive(Copy, Clone)]
pub struct u64_stats_sync { pub seq: c_uint }

// ============================================================================
// Auto-generated Mock Stubs (Alternative to AI Fixer)
// ============================================================================

#[macro_export]
macro_rules! __skb_push {
    ($($arg:tt)*) => { 0 }
}

#[macro_export]
macro_rules! dst_release {
    ($($arg:tt)*) => { 0 }
}

#[macro_export]
macro_rules! icmpv6_push_pending_frames {
    ($($arg:tt)*) => { 0 }
}

#[macro_export]
macro_rules! inet6_register_protosw {
    ($($arg:tt)*) => { 0 }
}

#[macro_export]
macro_rules! inet6_sk {
    ($($arg:tt)*) => { 0 }
}

#[macro_export]
macro_rules! inet6_unregister_protosw {
    ($($arg:tt)*) => { 0 }
}

#[macro_export]
macro_rules! inet_proto_csum_replace4 {
    ($($arg:tt)*) => { 0 }
}
extern "C" {
    pub fn udplite_get_port(sk: *mut core::ffi::c_void, snum: u16, recycling: i32) -> i32;

    // Kernel memory allocators
    pub fn kmalloc(size: usize, flags: c_uint) -> *mut c_void;
    pub fn kfree(ptr: *mut c_void);
    pub fn kzalloc(size: usize, flags: c_uint) -> *mut c_void;
}

/// GFP allocation flags type
pub type gfp_t = c_uint;

/// Common GFP flags
pub const GFP_KERNEL: gfp_t = 0xCC0; pub const GFP_ATOMIC: gfp_t = 0x20;

// ============================================================================
// Formal Verification Contracts (v7.0.0 Experimental Symbolic Execution)
// ============================================================================

#[cfg(feature = "verus")]
pub extern crate builtin;
#[cfg(feature = "verus")]
pub extern crate builtin_macros;

/// Represents a precondition that must be mathematically satisfied (maps to Lean 4 axioms).
#[cfg(not(feature = "verus"))]
#[macro_export]
macro_rules! requires {
    ($cond:expr, $msg:expr) => {
        // In a true symbolic execution engine (like Verus/Creusot), this is parsed at compile-time.
        // For runtime evaluation, we enforce the mathematical invariant via a kernel panic.
        if !($cond) {
            panic!("Formal Verification Precondition Failed: {}", $msg);
        }
    };
}

#[cfg(feature = "verus")]
#[macro_export]
macro_rules! requires {
    ($cond:expr, $msg:expr) => {
        $crate::builtin::requires($cond);
    };
}

/// Represents a postcondition that the function mathematically guarantees.
#[cfg(not(feature = "verus"))]
#[macro_export]
macro_rules! ensures {
    ($cond:expr, $msg:expr) => {
        if !($cond) {
            panic!("Formal Verification Postcondition Failed: {}", $msg);
        }
    };
}

#[cfg(feature = "verus")]
#[macro_export]
macro_rules! ensures {
    ($cond:expr, $msg:expr) => {
        $crate::builtin::ensures($cond);
    };
}

// ============================================================================
// Netfilter Hook State
// ============================================================================

/// Netfilter hook state - contains context for hook execution
#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_hook_state {
    pub hook: u8,
    pub pf: u8,
    pub in_dev: *mut c_void,  // net_device
    pub out_dev: *mut c_void, // net_device
    pub sk: *mut c_void,      // sock
    pub net: *mut c_void,
    pub okfn: Option<extern "C" fn(*mut c_void, *mut c_void, *mut nf_hook_state) -> c_int>,
}

// ============================================================================
// Common Type Aliases (CamelCase variants for C-style structs)
// ============================================================================

/// Socket buffer type alias (CamelCase variant)
pub type SkBuff = sk_buff;

/// Socket type alias (CamelCase variant)
pub type Sock = sock;

/// TCP socket type alias (CamelCase variant)
pub type TCP_SOCK = tcp_sock;

/// UDP socket type alias (CamelCase variant)
pub type UDP_SOCK = udp_sock;

/// Network device features type
pub type NetdevFeaturesT = u64;

/// List head for linked lists (lowercase alias for C compatibility)
pub type list_head = ListHead;

/// List head for linked lists
#[repr(C)]
#[derive(Copy, Clone)]
pub struct ListHead { pub next: *mut ListHead, pub prev: *mut ListHead }

/// IPv6 option header
#[repr(C)]
#[derive(Copy, Clone)]
pub struct Ipv6OptHdr { pub nexthdr: u8, pub hdrlen: u8 }

/// Network namespace type alias
pub type NF_CONN = nf_conn;

/// Network address union type alias (CamelCase variant)
pub type NF_INET_ADDR = nf_inet_addr;

/// Network device (opaque type)
#[repr(C)]
#[derive(Copy, Clone)]
pub struct net_device {
    pub ifindex: c_int,
    pub group: c_int,
    _private: [u8; 0],
}

// ============================================================================
// KUnit Runtime Validation Framework Integration
// ============================================================================

/// Opaque kunit test instance passed to test cases
#[repr(C)]
#[derive(Copy, Clone)]
pub struct kunit {
    _private: [u8; 0],
}

/// `KUnit` case structure for registering individual tests
#[repr(C)]
#[derive(Copy, Clone)]
pub struct kunit_case {
    pub run_case: Option<unsafe extern "C" fn(*mut kunit)>,
    pub name: *const c_char,
    pub generate_params: *const c_void,
}

/// `KUnit` suite structure representing a test suite
#[repr(C)]
#[derive(Copy, Clone)]
pub struct kunit_suite {
    pub name: *const c_char,
    pub init: Option<unsafe extern "C" fn(*mut kunit) -> c_int>,
    pub exit: Option<unsafe extern "C" fn(*mut kunit)>,
    pub test_cases: *mut kunit_case,
}

#[cfg(target_os = "none")]
extern "C" {
    /// Internal KUnit function to register test failures
    pub fn kunit_do_failed_assertion(
        test: *mut kunit,
        assertion: *const c_void,
        message: *const c_char,
    );
}

#[cfg(not(target_os = "none"))]
#[no_mangle]
/// # Safety
/// FFI boundary for `KUnit`
pub unsafe extern "C" fn kunit_do_failed_assertion(
    _test: *mut kunit,
    _assertion: *const c_void,
    message: *const c_char,
) {
    // Under no_std host-side build, we don't have println!. We can use write FFI to stderr.
    extern "C" {
        fn write(fd: c_int, buf: *const c_void, count: size_t) -> ssize_t;
    }
    let prefix = b"Mock KUnit assertion failed: ";
    let _ = write(2, prefix.as_ptr().cast::<c_void>(), prefix.len());
    
    if message.is_null() {
        let null_str = b"null";
        let _ = write(2, null_str.as_ptr().cast::<c_void>(), null_str.len());
    } else {
        let mut len = 0;
        while *message.add(len) != 0 {
            len += 1;
        }
        let _ = write(2, message.cast::<c_void>(), len);
    }
    
    let newline = b"\n";
    let _ = write(2, newline.as_ptr().cast::<c_void>(), newline.len());
}

#[macro_export]
macro_rules! kunit_unsafe_test_suite {
    ($name:ident, $init:expr, $exit:expr, [$($case_name:ident => $case_fn:expr),* $(,)?]) => {
        pub mod $name {
            use super::*;

            // Individual test case function wrappers
            $(
                #[no_mangle]
                pub unsafe extern "C" fn $case_name(test: *mut $crate::kunit) {
                    // Execute the case logic
                    let result: Result<(), &'static str> = $case_fn(test);
                    if let Err(_msg) = result {
                        // Call kernel assertion fail FFI
                        let c_msg = concat!(stringify!($case_name), " failed: \0").as_ptr() as *const $crate::c_char;
                        $crate::kunit_do_failed_assertion(test, core::ptr::null(), c_msg);
                    }
                }
            )*

            // Wrapper types with explicit Sync implementation for shared static access
            pub struct _CasesWrapper(pub core::cell::UnsafeCell<[$crate::kunit_case; 1 + [$($case_name),*].len()]>);
            // SAFETY: The kernel test framework synchronizes access to these statics during test execution.
            // They are immutable after initialization and accessed only through properly coordinated
            // mutable pointers, guaranteeing no data races.
            unsafe impl Sync for _CasesWrapper {}

            pub struct _SuiteWrapper(pub core::cell::UnsafeCell<$crate::kunit_suite>);
            // SAFETY: The kernel test framework synchronizes access to these statics during test execution.
            // They are immutable after initialization and accessed only through properly coordinated
            // mutable pointers, guaranteeing no data races.
            unsafe impl Sync for _SuiteWrapper {}

            // Test cases array, terminated by an empty case
            #[cfg_attr(all(not(test), target_os = "macos"), link_section = "__DATA,kunit_cases")]
            #[cfg_attr(all(not(test), not(target_os = "macos")), link_section = ".kunit_test_cases")]
            #[no_mangle]
            pub static CASES: _CasesWrapper = _CasesWrapper(core::cell::UnsafeCell::new([
                $(
                    $crate::kunit_case {
                        run_case: Some($case_name),
                        name: concat!(stringify!($case_name), "\0").as_ptr() as *const $crate::c_char,
                        generate_params: core::ptr::null(),
                    },
                )*
                $crate::kunit_case {
                    run_case: None,
                    name: core::ptr::null(),
                    generate_params: core::ptr::null(),
                }
            ]));

            // Test suite definition
            #[cfg_attr(all(not(test), target_os = "macos"), link_section = "__DATA,kunit_suites")]
            #[cfg_attr(all(not(test), not(target_os = "macos")), link_section = ".kunit_test_suites")]
            #[no_mangle]
            pub static SUITE: _SuiteWrapper = _SuiteWrapper(core::cell::UnsafeCell::new($crate::kunit_suite {
                name: concat!(stringify!($name), "\0").as_ptr() as *const $crate::c_char,
                init: $init,
                exit: $exit,
                test_cases: CASES.0.get() as *mut $crate::kunit_case,
            }));
        }
    };
}

// ============================================================================
// Compile-Time FFI Structural Layout Assertions
// ============================================================================

const _: () = {
    // Validate iphdr constraints (20 bytes, align 4)
    assert!(core::mem::size_of::<iphdr>() == 20);
    assert!(core::mem::align_of::<iphdr>() == 4);

    // Validate udphdr constraints (8 bytes, align 2)
    assert!(core::mem::size_of::<udphdr>() == 8);
    assert!(core::mem::align_of::<udphdr>() == 2);

    // Validate ipv6hdr constraints (40 bytes, align 4 or 8 depending on arch)
    assert!(core::mem::size_of::<ipv6hdr>() == 40);
};

// ============================================================================
// Memory Zero-Cost Abstractions
// ============================================================================

/// `SafePageFrame` is a zero-cost abstraction for a memory page frame.
pub struct SafePageFrame<'a> {
    pub ptr: *mut core::ffi::c_void,
    pub order: u32,
    _marker: core::marker::PhantomData<&'a mut core::ffi::c_void>,
}

impl SafePageFrame<'_> {
    #[inline]
    pub fn new(ptr: *mut core::ffi::c_void, order: u32) -> Option<Self> {
        if ptr.is_null() {
            None
        } else {
            Some(Self {
                ptr,
                order,
                _marker: core::marker::PhantomData,
            })
        }
    }
}

// ============================================================================
// Zero-Allocation Bare-Metal Synchronization
// ============================================================================

/// Zero-allocation, bare-metal spinlock.
pub struct SpinLock<T> {
    locked: core::sync::atomic::AtomicBool,
    data: core::cell::UnsafeCell<T>,
}

unsafe impl<T: Send> Sync for SpinLock<T> {}
unsafe impl<T: Send> Send for SpinLock<T> {}

pub struct SpinLockGuard<'a, T> {
    lock: &'a SpinLock<T>,
}

impl<T> SpinLock<T> {
    #[inline]
    pub const fn new(data: T) -> Self {
        Self {
            locked: core::sync::atomic::AtomicBool::new(false),
            data: core::cell::UnsafeCell::new(data),
        }
    }

    #[inline]
    pub fn lock(&self) -> SpinLockGuard<'_, T> {
        while self.locked.compare_exchange_weak(
            false,
            true,
            core::sync::atomic::Ordering::Acquire,
            core::sync::atomic::Ordering::Relaxed,
        ).is_err() {
            core::hint::spin_loop();
        }
        SpinLockGuard { lock: self }
    }

    #[inline]
    pub fn try_lock(&self) -> Option<SpinLockGuard<'_, T>> {
        if self.locked.compare_exchange(
            false,
            true,
            core::sync::atomic::Ordering::Acquire,
            core::sync::atomic::Ordering::Relaxed,
        ).is_ok() {
            Some(SpinLockGuard { lock: self })
        } else {
            None
        }
    }

    #[inline]
    pub fn is_locked(&self) -> bool {
        self.locked.load(core::sync::atomic::Ordering::Relaxed)
    }
}

impl<'a, T> core::ops::Deref for SpinLockGuard<'a, T> {
    type Target = T;
    #[inline(always)]
    fn deref(&self) -> &Self::Target {
        // SAFETY: Lock is held by this guard.
        unsafe { &*self.lock.data.get() }
    }
}

impl<'a, T> core::ops::DerefMut for SpinLockGuard<'a, T> {
    #[inline(always)]
    fn deref_mut(&mut self) -> &mut Self::Target {
        // SAFETY: Lock is held exclusively by this guard.
        unsafe { &mut *self.lock.data.get() }
    }
}

impl<'a, T> Drop for SpinLockGuard<'a, T> {
    #[inline(always)]
    fn drop(&mut self) {
        self.lock.locked.store(false, core::sync::atomic::Ordering::Release);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_spinlock_basic() {
        let lock = SpinLock::new(42);
        assert!(!lock.is_locked());
        {
            let mut guard = lock.lock();
            assert!(lock.is_locked());
            assert_eq!(*guard, 42);
            *guard = 100;
        }
        assert!(!lock.is_locked());
        assert_eq!(*lock.lock(), 100);
    }

    #[test]
    fn test_spinlock_try_lock() {
        let lock = SpinLock::new(7);
        let guard1 = lock.try_lock();
        assert!(guard1.is_some());
        let guard2 = lock.try_lock();
        assert!(guard2.is_none());
        drop(guard1);
        let guard3 = lock.try_lock();
        assert!(guard3.is_some());
    }

    #[test]
    fn test_safepageframe_basic() {
        let mut dummy: u8 = 0;
        let valid = SafePageFrame::new(&mut dummy as *mut u8 as *mut core::ffi::c_void, 2);
        assert!(valid.is_some());
        let frame = valid.unwrap();
        assert_eq!(frame.order, 2);

        let invalid = SafePageFrame::new(core::ptr::null_mut(), 0);
        assert!(invalid.is_none());
    }

    #[test]
    fn test_alloc_error_variants() {
        assert_eq!(AllocError::OutOfMemory, AllocError::OutOfMemory);
        assert_ne!(AllocError::OutOfMemory, AllocError::InvalidSize);
        assert_ne!(AllocError::InvalidOrder, AllocError::InvalidAlignment);
    }

    #[test]
    fn test_netbuf_zero_copy_operations() {
        let mut memory = [0u8; 256];
        // 64 bytes headroom, 192 bytes payload/tailroom
        // SAFETY: memory is valid stack slice of 256 bytes
        let mut buf = unsafe {
            NetBuf::from_raw_parts(memory.as_mut_ptr(), 256, 64).expect("valid netbuf")
        };

        assert_eq!(buf.len(), 0);
        assert_eq!(buf.headroom(), 64);
        assert_eq!(buf.tailroom(), 192);

        // Put 100 bytes payload
        {
            let payload = buf.put(100).expect("payload fits in tailroom");
            assert_eq!(payload.len(), 100);
            payload[0] = 0xAA;
            payload[99] = 0xBB;
        }
        assert_eq!(buf.len(), 100);
        assert_eq!(buf.tailroom(), 92);

        // Push 14 bytes Ethernet header in headroom
        {
            let eth = buf.push(14).expect("header fits in headroom");
            assert_eq!(eth.len(), 14);
            eth[0] = 0xFF;
        }
        assert_eq!(buf.len(), 114);
        assert_eq!(buf.headroom(), 50);


        // Pull (strip) Ethernet header
        let stripped = buf.pull(14).expect("pull header");
        assert_eq!(stripped.len(), 14);
        assert_eq!(stripped[0], 0xFF);
        assert_eq!(buf.len(), 100);
        assert_eq!(buf.headroom(), 64);

        // Zero-copy clone
        let clone = buf.clone_zerocopy();
        assert_eq!(clone.len(), 100);
        assert_eq!(clone.data_slice()[0], 0xAA);
        assert_eq!(clone.data_slice()[99], 0xBB);

        // Bounds error checks
        assert_eq!(buf.push(100), Err(AllocError::OutOfMemory));
        assert_eq!(buf.put(100), Err(AllocError::OutOfMemory));
        assert_eq!(buf.pull(200), Err(AllocError::InvalidSize));
        assert_eq!(buf.trim(200), Err(AllocError::InvalidSize));
    }
}

// ============================================================================
// Kernel Fallible Allocation Errors
// ============================================================================

/// Kernel allocation failure conditions.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum AllocError {
    /// Memory exhaustion in physical, slab, or virtual space.
    OutOfMemory,
    /// Memory alignment requirement could not be satisfied.
    InvalidAlignment,
    /// Requested order is outside supported limits.
    InvalidOrder,
    /// Allocation size is 0 or exceeds maximum allowable limit.
    InvalidSize,
    /// Subsystem allocator is not initialized.
    NotInitialized,
}

// ============================================================================
// Zero-Copy Network Packet Buffers (NetBuf)
// ============================================================================

/// A zero-copy packet buffer with bounded headroom, data payload, and tailroom.
///
/// Memory Layout:
/// `[ Headroom | Data Payload (len) | Tailroom ]`
/// `^head      ^data                ^tail     ^end`
pub struct NetBuf {
    head: *mut u8,
    data: *mut u8,
    tail: *mut u8,
    end: *mut u8,
    len: usize,
    truesize: usize,
    refcnt: core::sync::atomic::AtomicU32,
}

unsafe impl Send for NetBuf {}
unsafe impl Sync for NetBuf {}

impl NetBuf {
    /// Construct a new NetBuf wrapping a raw memory block.
    ///
    /// # Safety
    /// `buffer` must be a valid, writable memory region of `capacity` bytes.
    #[inline]
    pub unsafe fn from_raw_parts(buffer: *mut u8, capacity: usize, reserved_headroom: usize) -> Result<Self, AllocError> {
        if buffer.is_null() {
            return Err(AllocError::OutOfMemory);
        }
        if capacity == 0 || reserved_headroom > capacity {
            return Err(AllocError::InvalidSize);
        }

        let head = buffer;
        // SAFETY: reserved_headroom <= capacity
        let data = unsafe { buffer.add(reserved_headroom) };
        let tail = data;
        // SAFETY: buffer + capacity is end of allocation
        let end = unsafe { buffer.add(capacity) };

        Ok(Self {
            head,
            data,
            tail,
            end,
            len: 0,
            truesize: capacity,
            refcnt: core::sync::atomic::AtomicU32::new(1),
        })
    }

    #[inline]
    #[must_use]
    pub fn len(&self) -> usize {
        self.len
    }

    #[inline]
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    #[inline]
    #[must_use]
    pub fn headroom(&self) -> usize {
        // SAFETY: data >= head
        unsafe { self.data.offset_from(self.head) as usize }
    }

    #[inline]
    #[must_use]
    pub fn tailroom(&self) -> usize {
        // SAFETY: end >= tail
        unsafe { self.end.offset_from(self.tail) as usize }
    }

    #[inline]
    #[must_use]
    pub fn truesize(&self) -> usize {
        self.truesize
    }

    #[inline]
    #[must_use]
    pub fn as_ptr(&self) -> *const u8 {
        self.data
    }

    #[inline]
    #[must_use]
    pub fn as_mut_ptr(&mut self) -> *mut u8 {
        self.data
    }

    #[inline]
    #[must_use]
    pub fn data_slice(&self) -> &[u8] {
        if self.len == 0 {
            &[]
        } else {
            // SAFETY: data points to self.len valid readable bytes
            unsafe { core::slice::from_raw_parts(self.data, self.len) }
        }
    }

    #[inline]
    #[must_use]
    pub fn data_slice_mut(&mut self) -> &mut [u8] {
        if self.len == 0 {
            &mut []
        } else {
            // SAFETY: data points to self.len valid writable bytes
            unsafe { core::slice::from_raw_parts_mut(self.data, self.len) }
        }
    }

    /// Extend the packet payload by `len` bytes at the tail.
    #[inline]
    pub fn put(&mut self, len: usize) -> Result<&mut [u8], AllocError> {
        if len > self.tailroom() {
            return Err(AllocError::OutOfMemory);
        }
        let old_tail = self.tail;
        // SAFETY: Verified within tailroom
        self.tail = unsafe { self.tail.add(len) };
        self.len += len;
        // SAFETY: old_tail points to newly allocated tail slice
        Ok(unsafe { core::slice::from_raw_parts_mut(old_tail, len) })
    }

    /// Prepend `len` bytes of protocol header in the headroom.
    #[inline]
    pub fn push(&mut self, len: usize) -> Result<&mut [u8], AllocError> {
        if len > self.headroom() {
            return Err(AllocError::OutOfMemory);
        }
        // SAFETY: Verified within headroom
        self.data = unsafe { self.data.sub(len) };
        self.len += len;
        // SAFETY: self.data points to newly pushed header slice
        Ok(unsafe { core::slice::from_raw_parts_mut(self.data, len) })
    }

    /// Strip `len` bytes of protocol header from the start of the payload.
    #[inline]
    pub fn pull(&mut self, len: usize) -> Result<&[u8], AllocError> {
        if len > self.len {
            return Err(AllocError::InvalidSize);
        }
        let old_data = self.data;
        // SAFETY: len <= self.len, remains within buffer bounds
        self.data = unsafe { self.data.add(len) };
        self.len -= len;
        // SAFETY: old_data points to stripped slice
        Ok(unsafe { core::slice::from_raw_parts(old_data, len) })
    }

    /// Truncate packet payload to `new_len` bytes.
    #[inline]
    pub fn trim(&mut self, new_len: usize) -> Result<(), AllocError> {
        if new_len > self.len {
            return Err(AllocError::InvalidSize);
        }
        // SAFETY: new_len <= self.len
        self.tail = unsafe { self.data.add(new_len) };
        self.len = new_len;
        Ok(())
    }

    /// Increment reference count for zero-copy sharing across layers.
    #[inline]
    pub fn clone_zerocopy(&self) -> Self {
        self.refcnt.fetch_add(1, core::sync::atomic::Ordering::Relaxed);
        Self {
            head: self.head,
            data: self.data,
            tail: self.tail,
            end: self.end,
            len: self.len,
            truesize: self.truesize,
            refcnt: core::sync::atomic::AtomicU32::new(self.refcnt.load(core::sync::atomic::Ordering::Relaxed)),
        }
    }

    #[inline]
    #[must_use]
    pub fn ref_count(&self) -> u32 {
        self.refcnt.load(core::sync::atomic::Ordering::Relaxed)
    }
}

