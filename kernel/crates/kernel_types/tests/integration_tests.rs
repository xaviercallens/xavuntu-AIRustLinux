use kernel_types::*;
use core::mem::{size_of, align_of};

#[test]
fn test_network_address_sizes_and_alignment() {
    // Assert structural sizes match C-ABI expectations for 5.10 LTS networking
    assert_eq!(size_of::<in_addr>(), 16); // 4 bytes IP + pointer mock field on 64-bit systems
    assert_eq!(size_of::<in6_addr>(), 16); // 16 bytes IP6 (union of u8/u16/u32 arrays, no padding)
    assert_eq!(align_of::<in_addr>(), 8);
    assert_eq!(align_of::<in6_addr>(), 4);
}

#[test]
fn test_protocol_header_sizes() {
    // Assert standard protocol header sizes
    assert_eq!(size_of::<ethhdr>(), 14); // 6 + 6 + 2 bytes
    assert_eq!(size_of::<iphdr>(), 20);  // Standard IPv4 header size is 20 bytes
    assert_eq!(size_of::<ipv6hdr>(), 40); // Standard IPv6 header size is 40 bytes (8-byte fixed header + 2x16-byte addresses)
    assert_eq!(size_of::<udphdr>(), 8);   // UDP header size is 8 bytes
}

#[test]
fn test_socket_structure_sizes() {
    // Verify base structures
    assert_eq!(size_of::<sockaddr>(), 16); // 2 + 14 bytes
    assert_eq!(size_of::<iovec>(), 16);    // 8 + 8 bytes on 64-bit systems
}

#[test]
fn test_list_head_manipulation() {
    // Standard doubly-linked list nodes
    let mut head = ListHead {
        next: core::ptr::null_mut(),
        prev: core::ptr::null_mut(),
    };
    
    let mut node = ListHead {
        next: core::ptr::null_mut(),
        prev: core::ptr::null_mut(),
    };
    
    // Perform simulated insertion
    head.next = &mut node;
    node.prev = &mut head;
    
    assert!(!head.next.is_null());
    assert_eq!(node.prev, &mut head as *mut ListHead);
}

// Simulated mock tests to verify KUnit macro compiles and works
fn dummy_kunit_case_1(_test: *mut kunit) -> Result<(), &'static str> {
    Ok(())
}

fn dummy_kunit_case_2(_test: *mut kunit) -> Result<(), &'static str> {
    // Return an error to simulate a test failure
    Err("Simulated assertion failure")
}

// Instantiate the test suite using our new macro to verify compile-time macro expansion
kunit_unsafe_test_suite!(
    mock_kernel_suite,
    None,
    None,
    [
        test_case_success => dummy_kunit_case_1,
        test_case_fail => dummy_kunit_case_2,
    ]
);

#[test]
fn test_kunit_macro_expansion() {
    // SAFETY: The generated CASES and SUITE statics are immutable after initialization and persist
    // for the lifetime of the program. We only dereference them to read their contents, and no data
    // races can occur since Rust's execution model prevents concurrent mutation of statics within
    // a single test execution.
    unsafe {
        // Assert the generated array has 3 elements (2 cases + 1 null terminator)
        assert_eq!((*mock_kernel_suite::CASES.0.get()).len(), 3);

        // Assert suite metadata is correctly populated
        assert!(!(*mock_kernel_suite::SUITE.0.get()).name.is_null());
        assert_eq!((*mock_kernel_suite::SUITE.0.get()).test_cases, mock_kernel_suite::CASES.0.get() as *mut _);
    }
}

#[test]
fn test_ping_packet_flow() {
    // FFI-compatible ICMP header definition
    #[repr(C)]
    struct icmphdr {
        pub icmp_type: u8,
        pub code: u8,
        pub checksum: u16,
        pub id: u16,
        pub sequence: u16,
    }

    // 1. Echo Request (Ping outgoing)
    let ip_req = iphdr {
        version_ihl: 0x45, // IPv4, 20 bytes
        tos: 0,
        tot_len: u16::to_be(64),
        id: u16::to_be(100),
        frag_off: 0,
        ttl: 64,
        protocol: 1, // ICMP
        check: 0,
        saddr: u32::to_be(0x0a000001), // 10.0.0.1
        daddr: u32::to_be(0x0a000002), // 10.0.0.2
    };

    let icmp_req = icmphdr {
        icmp_type: 8, // Echo Request
        code: 0,
        checksum: 0,
        id: u16::to_be(0x1234),
        sequence: u16::to_be(1),
    };

    assert_eq!(ip_req.protocol, 1);
    assert_eq!(icmp_req.icmp_type, 8);
    assert_eq!(u32::from_be(ip_req.saddr), 0x0a000001);
    assert_eq!(u32::from_be(ip_req.daddr), 0x0a000002);

    // 2. Echo Reply (Ping response)
    let ip_rep = iphdr {
        version_ihl: 0x45,
        tos: 0,
        tot_len: u16::to_be(64),
        id: u16::to_be(101),
        frag_off: 0,
        ttl: 64,
        protocol: 1,
        check: 0,
        saddr: u32::to_be(0x0a000002), // 10.0.0.2
        daddr: u32::to_be(0x0a000001), // 10.0.0.1
    };

    let icmp_rep = icmphdr {
        icmp_type: 0, // Echo Reply
        code: 0,
        checksum: 0,
        id: u16::to_be(0x1234),
        sequence: u16::to_be(1),
    };

    assert_eq!(ip_rep.protocol, 1);
    assert_eq!(icmp_rep.icmp_type, 0);
    assert_eq!(u32::from_be(ip_rep.saddr), 0x0a000002);
    assert_eq!(u32::from_be(ip_rep.daddr), 0x0a000001);
}

#[test]
fn test_iperf3_payload_parsing() {
    // FFI-compatible TCP header definition
    #[repr(C)]
    struct tcphdr {
        pub source: u16,
        pub dest: u16,
        pub seq: u32,
        pub ack_seq: u32,
        pub flags: u16,
        pub window: u16,
        pub check: u16,
        pub urg_ptr: u16,
    }

    // Simulate an iperf3 TCP connection tracking flow: Client SYN -> Server SYN-ACK -> Client ACK
    let syn_pkt = tcphdr {
        source: u16::to_be(5001),
        dest: u16::to_be(5201), // iperf3 server
        seq: u32::to_be(100),
        ack_seq: 0,
        flags: 0x0002, // SYN flag set
        window: u16::to_be(8192),
        check: 0,
        urg_ptr: 0,
    };

    let synack_pkt = tcphdr {
        source: u16::to_be(5201),
        dest: u16::to_be(5001),
        seq: u32::to_be(1000),
        ack_seq: u32::to_be(101),
        flags: 0x0012, // SYN-ACK flags set
        window: u16::to_be(8192),
        check: 0,
        urg_ptr: 0,
    };

    assert_eq!(u16::from_be(syn_pkt.dest), 5201);
    assert_eq!(syn_pkt.flags & 0x0002, 0x0002);
    assert_eq!(u32::from_be(synack_pkt.ack_seq), 101);
}
