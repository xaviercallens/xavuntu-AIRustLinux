#![no_main]
use libfuzzer_sys::fuzz_target;
use kernel_types::*;
use core::mem::size_of;

fuzz_target!(|data: &[u8]| {
    // Fuzzing the network packet decoders
    if data.len() < 20 {
        return;
    }

    // Tier 1: Try to parse as an IPv4 header
    let iph_ptr = data.as_ptr() as *const iphdr;
    unsafe {
        // Safe check if pointer alignment permits dereferencing or use read_unaligned
        let iph = core::ptr::read_unaligned(iph_ptr);
        
        // Extract fields using our newly packed version_ihl bitfield logic
        let ihl = iph.version_ihl & 0x0f;
        let version = iph.version_ihl >> 4;
        
        // Assertions or logic pathways to ensure parser doesn't panic
        if version == 4 && ihl >= 5 {
            let _hdroff = (ihl as usize) * 4;
        }
    }

    // Tier 2: Try to parse as an IPv6 header if size permits
    if data.len() >= 40 {
        let ip6h_ptr = data.as_ptr() as *const ipv6hdr;
        unsafe {
            let ip6h = core::ptr::read_unaligned(ip6h_ptr);
            
            // Extract IPv6 version and priority from packed field
            let version = (ip6h.version_priority & 0xf0) >> 4;
            if version == 6 {
                let _payload_len = u16::from_be(ip6h.payload_len);
            }
        }
    }

    // Tier 3: Mock sk_buff parsing with the raw data
    let mut buffer = data.to_vec();
    let mut skb = sk_buff {
        next: core::ptr::null_mut(),
        prev: core::ptr::null_mut(),
        tstamp: 0,
        dev: core::ptr::null_mut(),
        len: buffer.len() as c_uint,
        data_len: 0,
        mac_len: 14,
        hdr_len: 20,
        csum: 0,
        priority: 0,
        protocol: 0x0008, // IPv4
        flags: 0,
        cb: [0; 48],
        ip_summed: 0,
        csum_level: 0,
        csum_valid: 0,
        csum_complete_sw: 0,
        remcsum_offload: core::ptr::null_mut(),
        mark: core::ptr::null_mut(),
        data: buffer.as_mut_ptr() as *mut core::ffi::c_void,
        sk: core::ptr::null_mut(),
        dst: core::ptr::null_mut(),
        head: buffer.as_mut_ptr(),
        network_header: 14,
        transport_header: 34,
        transport_offset: 34,
        network_header_len: 20,
    };

    // Simulate simple network parser checks on skb
    unsafe {
        let network_header_ptr = (skb.head as *const u8).add(skb.network_header as usize);
        if skb.len > skb.network_header as u32 + size_of::<iphdr>() as u32 {
            let iph = core::ptr::read_unaligned(network_header_ptr as *const iphdr);
            let version = iph.version_ihl >> 4;
            let ihl = iph.version_ihl & 0x0f;
            if version == 4 && ihl >= 5 {
                let ip_hdr_len = (ihl as u32) * 4;
                if skb.len >= skb.network_header as u32 + ip_hdr_len {
                    skb.network_header_len = ip_hdr_len;
                    let _ = skb.network_header_len;
                }
            }
        }
    }
});
