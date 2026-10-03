use std::arch::x86_64::_rdtsc;
use std::thread;

const ITERATIONS: u64 = 1_000_000;

fn rdtsc() -> u64 {
    unsafe { _rdtsc() }
}

fn main() {
    let mut start: u64;
    let mut end: u64;

    // 1. Syscall Benchmark (getpid equivalent via libc)
    start = rdtsc();
    for _ in 0..ITERATIONS {
        unsafe { libc::getpid() };
    }
    end = rdtsc();
    println!("Rust MVK Equivalent - Syscall (getpid): {} cycles/op", (end - start) / ITERATIONS);

    // 2. Memory Allocation Benchmark (mmap equivalent via libc)
    start = rdtsc();
    for _ in 0..(ITERATIONS / 100) {
        unsafe {
            let ptr = libc::mmap(
                std::ptr::null_mut(),
                4096,
                libc::PROT_READ | libc::PROT_WRITE,
                libc::MAP_PRIVATE | libc::MAP_ANONYMOUS,
                -1,
                0,
            );
            libc::munmap(ptr, 4096);
        }
    }
    end = rdtsc();
    println!("Rust MVK Equivalent - Mem Alloc (mmap): {} cycles/op", (end - start) / (ITERATIONS / 100));

    // 3. Thread Spawning Benchmark (std::thread)
    start = rdtsc();
    for _ in 0..(ITERATIONS / 1000) {
        let handle = thread::spawn(|| {});
        handle.join().unwrap();
    }
    end = rdtsc();
    println!("Rust MVK Equivalent - Thread Spawn/Join: {} cycles/op", (end - start) / (ITERATIONS / 1000));
}
