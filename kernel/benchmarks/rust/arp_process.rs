use std::env;
use std::time::Instant;

#[repr(C)]
struct ArpPacket {
    hw_type: u16,
    proto_type: u16,
    hw_len: u8,
    proto_len: u8,
    operation: u16,
    sender_hw: [u8; 6],
    sender_ip: [u8; 4],
    target_hw: [u8; 6],
    target_ip: [u8; 4],
}

fn process_arp(pkt: *const ArpPacket) -> i32 {
    unsafe {
        if (*pkt).hw_type != 1 || (*pkt).proto_type != 0x0800 {
            return -1;
        }

        // Simulate ARP cache lookup
        for i in 0..100 {
            if (*pkt).sender_ip[0] == i {
                break;
            }
        }
    }

    0
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let iterations: usize = args[1].parse().unwrap();

    let pkt = ArpPacket {
        hw_type: 1,
        proto_type: 0x0800,
        hw_len: 6,
        proto_len: 4,
        operation: 1,
        sender_hw: [0; 6],
        sender_ip: [192, 168, 1, 1],
        target_hw: [0; 6],
        target_ip: [0; 4],
    };

    let start = Instant::now();

    for _ in 0..iterations {
        let _ = process_arp(&pkt as *const ArpPacket);
    }

    let elapsed = start.elapsed();
    println!("{:.9}", elapsed.as_secs_f64());
}
