#![no_main]
use libfuzzer_sys::fuzz_target;
use kernel_types::*;

fuzz_target!(|data: &[u8]| {
    if data.len() < 16 {
        return;
    }

    // Try to parse the input as routing table data (dest, mask, gateway, metric)
    let dest = u32::from_ne_bytes(data[0..4].try_into().unwrap());
    let mask = u32::from_ne_bytes(data[4..8].try_into().unwrap());
    let gw = u32::from_ne_bytes(data[8..12].try_into().unwrap());
    let target_ip = u32::from_ne_bytes(data[12..16].try_into().unwrap());

    // Fuzz a simulated routing lookup
    let mut fib: fib_table = unsafe { core::mem::zeroed() };
    fib.tb_id = 254;

    // Very simple lookup mock based on standard IP bitwise operations
    // We just want to ensure these operations don't panic on weird input
    let is_match = (target_ip & mask) == (dest & mask);
    
    // Test basic metric constraints
    if is_match {
        let _hop_count = if mask == 0xFFFFFFFF { 1 } else { 2 };
        if gw != 0 {
            // Validate next-hop is not a broadcast if possible
            let _is_valid_gw = (gw & 0xFF000000) != 0xFF000000;
        }
    }
});
