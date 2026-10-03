#![cfg_attr(not(target_arch = "x86_64"), no_std)]
#[cfg(test)]
mod tests {
    use arp::{arphdr, arp_send, neighbour, ndisc_ops, net_device, htons};
    use arp::{ARPHRD_ETHER, ETH_P_IP, ETH_HLEN, ARPOP_REQUEST};
    use kernel_types::{sk_buff, in_addr, c_int, c_void};
    use core::ptr;

    unsafe extern "C" fn mock_output(skb: *mut sk_buff, neighbour: *mut neighbour) -> c_int {
    let _ret = 0;
    _ret
}

    #[test]
    fn test_arp_send_success() {
        unsafe {
            let mut ops = ndisc_ops { output: Some(mock_output) };
            let mut dev = net_device { type_: ARPHRD_ETHER };
            let mut dst = neighbour { dev: &mut dev as *mut _, ops: &mut ops as *mut _ };
            let mut data = [0u64; 16];
            let data_ptr = data.as_mut_ptr() as *mut u8;
            let eth_start = data_ptr.add(2); 
            let eth_proto_ptr = eth_start.add(12) as *mut u16;
            ptr::write_unaligned(eth_proto_ptr, htons(ETH_P_IP));
            let arp_ptr = eth_start.add(ETH_HLEN) as *mut arphdr;
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_op), htons(ARPOP_REQUEST));
            let mut s_addr = in_addr { s_addr: 1, ip: ptr::null_mut() };
            let mut d_addr = in_addr { s_addr: 2, ip: ptr::null_mut() };
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_sip), &mut s_addr as *mut _);
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_tip), &mut d_addr as *mut _);
            let mut skb = sk_buff {
                next: ptr::null_mut(), prev: ptr::null_mut(), tstamp: 0, dev: &mut dev as *mut _ as *mut c_void, len: 128,
                data_len: 0, mac_len: 14, hdr_len: 0, csum: 0, priority: 0, protocol: 0, flags: 0, cb: [0u8; 48],
                ip_summed: 0, csum_level: 0, csum_valid: 0, csum_complete_sw: 0, remcsum_offload: ptr::null_mut(),
                mark: ptr::null_mut(), data: eth_start as *mut c_void, sk: ptr::null_mut(), dst: &mut dst as *mut _ as *mut c_void,
                head: eth_start, network_header: 0, transport_header: 0, transport_offset: 0, network_header_len: 0,
            };
            let mut mock_ip: u32 = 0;
            let result = arp_send(&mut skb as *mut _, &mut mock_ip as *mut _ as *mut c_void);
            assert_eq!(result, 0);
        }
    }

    #[test]
    fn test_arp_send_null_dev() {
        unsafe {
            let mut skb = sk_buff {
                next: ptr::null_mut(), prev: ptr::null_mut(), tstamp: 0, dev: ptr::null_mut(), len: 128,
                data_len: 0, mac_len: 14, hdr_len: 0, csum: 0, priority: 0, protocol: 0, flags: 0, cb: [0u8; 48],
                ip_summed: 0, csum_level: 0, csum_valid: 0, csum_complete_sw: 0, remcsum_offload: ptr::null_mut(),
                mark: ptr::null_mut(), data: ptr::null_mut(), sk: ptr::null_mut(), dst: ptr::null_mut(),
                head: ptr::null_mut(), network_header: 0, transport_header: 0, transport_offset: 0, network_header_len: 0,
            };
            let mut mock_ip: u32 = 0;
            let result = arp_send(&mut skb as *mut _, &mut mock_ip as *mut _ as *mut c_void);
            assert_eq!(result, -kernel_types::EINVAL);
        }
    }

    #[test]
    fn test_arp_send_null_data() {
        unsafe {
            let mut dev = net_device { type_: ARPHRD_ETHER };
            let mut skb = sk_buff {
                next: ptr::null_mut(), prev: ptr::null_mut(), tstamp: 0, dev: &mut dev as *mut _ as *mut c_void, len: 128,
                data_len: 0, mac_len: 14, hdr_len: 0, csum: 0, priority: 0, protocol: 0, flags: 0, cb: [0u8; 48],
                ip_summed: 0, csum_level: 0, csum_valid: 0, csum_complete_sw: 0, remcsum_offload: ptr::null_mut(),
                mark: ptr::null_mut(), data: ptr::null_mut(), sk: ptr::null_mut(), dst: ptr::null_mut(),
                head: ptr::null_mut(), network_header: 0, transport_header: 0, transport_offset: 0, network_header_len: 0,
            };
            let mut mock_ip: u32 = 0;
            let result = arp_send(&mut skb as *mut _, &mut mock_ip as *mut _ as *mut c_void);
            assert_eq!(result, -kernel_types::EINVAL);
        }
    }

    #[test]
    fn test_arp_send_invalid_dev_type() {
        unsafe {
            let mut dev = net_device { type_: 0 };
            let mut skb = sk_buff {
                next: ptr::null_mut(), prev: ptr::null_mut(), tstamp: 0, dev: &mut dev as *mut _ as *mut c_void, len: 0,
                data_len: 0, mac_len: 0, hdr_len: 0, csum: 0, priority: 0, protocol: 0, flags: 0, cb: [0u8; 48],
                ip_summed: 0, csum_level: 0, csum_valid: 0, csum_complete_sw: 0, remcsum_offload: ptr::null_mut(),
                mark: ptr::null_mut(), data: ptr::null_mut(), sk: ptr::null_mut(), dst: ptr::null_mut(),
                head: ptr::null_mut(), network_header: 0, transport_header: 0, transport_offset: 0, network_header_len: 0,
            };
            let mut mock_ip: u32 = 0;
            let result = arp_send(&mut skb as *mut _, &mut mock_ip as *mut _ as *mut c_void);
            assert_eq!(result, -kernel_types::EINVAL);
        }
    }
    
    #[test]
    fn test_arp_send_invalid_eth_proto() {
        unsafe {
            let mut dev = net_device { type_: ARPHRD_ETHER };
            let mut data = [0u64; 16];
            let data_ptr = data.as_mut_ptr() as *mut u8;
            let eth_start = data_ptr.add(2);
            let eth_proto_ptr = eth_start.add(12) as *mut u16;
            ptr::write_unaligned(eth_proto_ptr, htons(0x0806)); 
            
            let mut skb = sk_buff {
                next: ptr::null_mut(), prev: ptr::null_mut(), tstamp: 0, dev: &mut dev as *mut _ as *mut c_void, len: 0,
                data_len: 0, mac_len: 0, hdr_len: 0, csum: 0, priority: 0, protocol: 0, flags: 0, cb: [0u8; 48],
                ip_summed: 0, csum_level: 0, csum_valid: 0, csum_complete_sw: 0, remcsum_offload: ptr::null_mut(),
                mark: ptr::null_mut(), data: eth_start as *mut c_void, sk: ptr::null_mut(), dst: ptr::null_mut(),
                head: ptr::null_mut(), network_header: 0, transport_header: 0, transport_offset: 0, network_header_len: 0,
            };
            let mut mock_ip: u32 = 0;
            let result = arp_send(&mut skb as *mut _, &mut mock_ip as *mut _ as *mut c_void);
            assert_eq!(result, -kernel_types::EINVAL);
        }
    }

    #[test]
    fn test_arp_send_invalid_arp_op() {
        unsafe {
            let mut dev = net_device { type_: ARPHRD_ETHER };
            let mut data = [0u64; 16];
            let data_ptr = data.as_mut_ptr() as *mut u8;
            let eth_start = data_ptr.add(2);
            let eth_proto_ptr = eth_start.add(12) as *mut u16;
            ptr::write_unaligned(eth_proto_ptr, htons(ETH_P_IP));
            
            let arp_ptr = eth_start.add(ETH_HLEN) as *mut arphdr;
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_op), htons(2)); 
            
            let mut skb = sk_buff {
                next: ptr::null_mut(), prev: ptr::null_mut(), tstamp: 0, dev: &mut dev as *mut _ as *mut c_void, len: 0,
                data_len: 0, mac_len: 0, hdr_len: 0, csum: 0, priority: 0, protocol: 0, flags: 0, cb: [0u8; 48],
                ip_summed: 0, csum_level: 0, csum_valid: 0, csum_complete_sw: 0, remcsum_offload: ptr::null_mut(),
                mark: ptr::null_mut(), data: eth_start as *mut c_void, sk: ptr::null_mut(), dst: ptr::null_mut(),
                head: ptr::null_mut(), network_header: 0, transport_header: 0, transport_offset: 0, network_header_len: 0,
            };
            let mut mock_ip: u32 = 0;
            let result = arp_send(&mut skb as *mut _, &mut mock_ip as *mut _ as *mut c_void);
            assert_eq!(result, -kernel_types::EINVAL);
        }
    }

    #[test]
    fn test_arp_send_null_addresses() {
        unsafe {
            let mut dev = net_device { type_: ARPHRD_ETHER };
            let mut data = [0u64; 16];
            let data_ptr = data.as_mut_ptr() as *mut u8;
            let eth_start = data_ptr.add(2);
            let eth_proto_ptr = eth_start.add(12) as *mut u16;
            ptr::write_unaligned(eth_proto_ptr, htons(ETH_P_IP));
            
            let arp_ptr = eth_start.add(ETH_HLEN) as *mut arphdr;
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_op), htons(ARPOP_REQUEST));
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_sip), ptr::null_mut());
            
            let mut skb = sk_buff {
                next: ptr::null_mut(), prev: ptr::null_mut(), tstamp: 0, dev: &mut dev as *mut _ as *mut c_void, len: 0,
                data_len: 0, mac_len: 0, hdr_len: 0, csum: 0, priority: 0, protocol: 0, flags: 0, cb: [0u8; 48],
                ip_summed: 0, csum_level: 0, csum_valid: 0, csum_complete_sw: 0, remcsum_offload: ptr::null_mut(),
                mark: ptr::null_mut(), data: eth_start as *mut c_void, sk: ptr::null_mut(), dst: ptr::null_mut(),
                head: ptr::null_mut(), network_header: 0, transport_header: 0, transport_offset: 0, network_header_len: 0,
            };
            let mut mock_ip: u32 = 0;
            let result = arp_send(&mut skb as *mut _, &mut mock_ip as *mut _ as *mut c_void);
            assert_eq!(result, -kernel_types::EINVAL);
        }
    }

    #[test]
    fn test_arp_send_same_addresses() {
        unsafe {
            let mut dev = net_device { type_: ARPHRD_ETHER };
            let mut data = [0u64; 16];
            let data_ptr = data.as_mut_ptr() as *mut u8;
            let eth_start = data_ptr.add(2);
            let eth_proto_ptr = eth_start.add(12) as *mut u16;
            ptr::write_unaligned(eth_proto_ptr, htons(ETH_P_IP));
            
            let arp_ptr = eth_start.add(ETH_HLEN) as *mut arphdr;
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_op), htons(ARPOP_REQUEST));
            
            let mut addr = in_addr { s_addr: 1, ip: ptr::null_mut() };
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_sip), &mut addr as *mut _);
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_tip), &mut addr as *mut _); 
            
            let mut skb = sk_buff {
                next: ptr::null_mut(), prev: ptr::null_mut(), tstamp: 0, dev: &mut dev as *mut _ as *mut c_void, len: 0,
                data_len: 0, mac_len: 0, hdr_len: 0, csum: 0, priority: 0, protocol: 0, flags: 0, cb: [0u8; 48],
                ip_summed: 0, csum_level: 0, csum_valid: 0, csum_complete_sw: 0, remcsum_offload: ptr::null_mut(),
                mark: ptr::null_mut(), data: eth_start as *mut c_void, sk: ptr::null_mut(), dst: ptr::null_mut(),
                head: ptr::null_mut(), network_header: 0, transport_header: 0, transport_offset: 0, network_header_len: 0,
            };
            let mut mock_ip: u32 = 0;
            let result = arp_send(&mut skb as *mut _, &mut mock_ip as *mut _ as *mut c_void);
            assert_eq!(result, -kernel_types::EINVAL);
        }
    }

    #[test]
    fn test_arp_send_invalid_dst() {
        unsafe {
            let mut dev = net_device { type_: ARPHRD_ETHER };
            let mut data = [0u64; 16];
            let data_ptr = data.as_mut_ptr() as *mut u8;
            let eth_start = data_ptr.add(2);
            let eth_proto_ptr = eth_start.add(12) as *mut u16;
            ptr::write_unaligned(eth_proto_ptr, htons(ETH_P_IP));
            
            let arp_ptr = eth_start.add(ETH_HLEN) as *mut arphdr;
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_op), htons(ARPOP_REQUEST));
            
            let mut s_addr = in_addr { s_addr: 1, ip: ptr::null_mut() };
            let mut d_addr = in_addr { s_addr: 2, ip: ptr::null_mut() };
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_sip), &mut s_addr as *mut _);
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_tip), &mut d_addr as *mut _);
            
            let mut skb = sk_buff {
                next: ptr::null_mut(), prev: ptr::null_mut(), tstamp: 0, dev: &mut dev as *mut _ as *mut c_void, len: 0,
                data_len: 0, mac_len: 0, hdr_len: 0, csum: 0, priority: 0, protocol: 0, flags: 0, cb: [0u8; 48],
                ip_summed: 0, csum_level: 0, csum_valid: 0, csum_complete_sw: 0, remcsum_offload: ptr::null_mut(),
                mark: ptr::null_mut(), data: eth_start as *mut c_void, sk: ptr::null_mut(), dst: ptr::null_mut(), 
                head: ptr::null_mut(), network_header: 0, transport_header: 0, transport_offset: 0, network_header_len: 0,
            };
            let mut mock_ip: u32 = 0;
            let result = arp_send(&mut skb as *mut _, &mut mock_ip as *mut _ as *mut c_void);
            assert_eq!(result, -kernel_types::EINVAL);
        }
    }

    #[test]
    fn test_arp_send_dst_invalid_dev() {
        unsafe {
            let mut dev = net_device { type_: ARPHRD_ETHER };
            let mut other_dev = net_device { type_: ARPHRD_ETHER };
            let mut ops = ndisc_ops { output: Some(mock_output) };
            let mut dst = neighbour { dev: &mut other_dev as *mut _, ops: &mut ops as *mut _ };
            let mut data = [0u64; 16];
            let data_ptr = data.as_mut_ptr() as *mut u8;
            let eth_start = data_ptr.add(2);
            let eth_proto_ptr = eth_start.add(12) as *mut u16;
            ptr::write_unaligned(eth_proto_ptr, htons(ETH_P_IP));
            let arp_ptr = eth_start.add(ETH_HLEN) as *mut arphdr;
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_op), htons(ARPOP_REQUEST));
            let mut s_addr = in_addr { s_addr: 1, ip: ptr::null_mut() };
            let mut d_addr = in_addr { s_addr: 2, ip: ptr::null_mut() };
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_sip), &mut s_addr as *mut _);
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_tip), &mut d_addr as *mut _);
            let mut skb = sk_buff {
                next: ptr::null_mut(), prev: ptr::null_mut(), tstamp: 0, dev: &mut dev as *mut _ as *mut c_void, len: 0,
                data_len: 0, mac_len: 0, hdr_len: 0, csum: 0, priority: 0, protocol: 0, flags: 0, cb: [0u8; 48],
                ip_summed: 0, csum_level: 0, csum_valid: 0, csum_complete_sw: 0, remcsum_offload: ptr::null_mut(),
                mark: ptr::null_mut(), data: eth_start as *mut c_void, sk: ptr::null_mut(), dst: &mut dst as *mut _ as *mut c_void,
                head: ptr::null_mut(), network_header: 0, transport_header: 0, transport_offset: 0, network_header_len: 0,
            };
            let mut mock_ip: u32 = 0;
            let result = arp_send(&mut skb as *mut _, &mut mock_ip as *mut _ as *mut c_void);
            assert_eq!(result, -kernel_types::EINVAL);
        }
    }

    #[test]
    fn test_arp_send_dst_no_ops() {
        unsafe {
            let mut dev = net_device { type_: ARPHRD_ETHER };
            let mut dst = neighbour { dev: &mut dev as *mut _, ops: ptr::null_mut() }; 
            let mut data = [0u64; 16];
            let data_ptr = data.as_mut_ptr() as *mut u8;
            let eth_start = data_ptr.add(2);
            let eth_proto_ptr = eth_start.add(12) as *mut u16;
            ptr::write_unaligned(eth_proto_ptr, htons(ETH_P_IP));
            let arp_ptr = eth_start.add(ETH_HLEN) as *mut arphdr;
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_op), htons(ARPOP_REQUEST));
            let mut s_addr = in_addr { s_addr: 1, ip: ptr::null_mut() };
            let mut d_addr = in_addr { s_addr: 2, ip: ptr::null_mut() };
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_sip), &mut s_addr as *mut _);
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_tip), &mut d_addr as *mut _);
            let mut skb = sk_buff {
                next: ptr::null_mut(), prev: ptr::null_mut(), tstamp: 0, dev: &mut dev as *mut _ as *mut c_void, len: 0,
                data_len: 0, mac_len: 0, hdr_len: 0, csum: 0, priority: 0, protocol: 0, flags: 0, cb: [0u8; 48],
                ip_summed: 0, csum_level: 0, csum_valid: 0, csum_complete_sw: 0, remcsum_offload: ptr::null_mut(),
                mark: ptr::null_mut(), data: eth_start as *mut c_void, sk: ptr::null_mut(), dst: &mut dst as *mut _ as *mut c_void,
                head: ptr::null_mut(), network_header: 0, transport_header: 0, transport_offset: 0, network_header_len: 0,
            };
            let mut mock_ip: u32 = 0;
            let result = arp_send(&mut skb as *mut _, &mut mock_ip as *mut _ as *mut c_void);
            assert_eq!(result, -kernel_types::EINVAL);
        }
    }

    #[test]
    fn test_arp_send_dst_ops_no_output() {
        unsafe {
            let mut dev = net_device { type_: ARPHRD_ETHER };
            let mut ops = ndisc_ops { output: None };
            let mut dst = neighbour { dev: &mut dev as *mut _, ops: &mut ops as *mut _ };
            let mut data = [0u64; 16];
            let data_ptr = data.as_mut_ptr() as *mut u8;
            let eth_start = data_ptr.add(2);
            let eth_proto_ptr = eth_start.add(12) as *mut u16;
            ptr::write_unaligned(eth_proto_ptr, htons(ETH_P_IP));
            let arp_ptr = eth_start.add(ETH_HLEN) as *mut arphdr;
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_op), htons(ARPOP_REQUEST));
            let mut s_addr = in_addr { s_addr: 1, ip: ptr::null_mut() };
            let mut d_addr = in_addr { s_addr: 2, ip: ptr::null_mut() };
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_sip), &mut s_addr as *mut _);
            ptr::write_unaligned(core::ptr::addr_of_mut!((*arp_ptr).ar_tip), &mut d_addr as *mut _);
            let mut skb = sk_buff {
                next: ptr::null_mut(), prev: ptr::null_mut(), tstamp: 0, dev: &mut dev as *mut _ as *mut c_void, len: 0,
                data_len: 0, mac_len: 0, hdr_len: 0, csum: 0, priority: 0, protocol: 0, flags: 0, cb: [0u8; 48],
                ip_summed: 0, csum_level: 0, csum_valid: 0, csum_complete_sw: 0, remcsum_offload: ptr::null_mut(),
                mark: ptr::null_mut(), data: eth_start as *mut c_void, sk: ptr::null_mut(), dst: &mut dst as *mut _ as *mut c_void,
                head: ptr::null_mut(), network_header: 0, transport_header: 0, transport_offset: 0, network_header_len: 0,
            };
            let mut mock_ip: u32 = 0;
            let result = arp_send(&mut skb as *mut _, &mut mock_ip as *mut _ as *mut c_void);
            assert_eq!(result, -kernel_types::EINVAL);
        }
    }
}


#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
