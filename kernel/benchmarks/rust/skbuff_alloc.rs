use std::alloc::{alloc, dealloc, Layout};
use std::env;
use std::time::Instant;

#[repr(C)]
struct SkBuff {
    data: *mut u8,
    len: u32,
    truesize: u32,
}

fn alloc_skb(size: usize) -> *mut SkBuff {
    unsafe {
        let layout = Layout::new::<SkBuff>();
        let skb = alloc(layout) as *mut SkBuff;
        if !skb.is_null() {
            let data_layout = Layout::from_size_align_unchecked(size, 8);
            let data = alloc(data_layout);
            (*skb).data = data;
            (*skb).len = 0;
            (*skb).truesize = size as u32;
        }
        skb
    }
}

fn free_skb(skb: *mut SkBuff) {
    unsafe {
        if !skb.is_null() {
            let data = (*skb).data;
            let size = (*skb).truesize as usize;
            let data_layout = Layout::from_size_align_unchecked(size, 8);
            dealloc(data, data_layout);

            let layout = Layout::new::<SkBuff>();
            dealloc(skb as *mut u8, layout);
        }
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let iterations: usize = args[1].parse().unwrap();

    let start = Instant::now();

    for _ in 0..iterations {
        let skb = alloc_skb(1500);
        free_skb(skb);
    }

    let elapsed = start.elapsed();
    println!("{:.9}", elapsed.as_secs_f64());
}
