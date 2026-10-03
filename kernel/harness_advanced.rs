use std::arch::x86_64::_rdtsc;
use std::fs::OpenOptions;
use std::io::Write;

const ITERATIONS: u64 = 100_000;

fn rdtsc() -> u64 {
    unsafe { _rdtsc() }
}

fn main() {
    let mut start: u64;
    let mut end: u64;

    // 4. IPC (Pipe) Benchmark
    let mut fds: [libc::c_int; 2] = [0; 2];
    unsafe { libc::pipe(fds.as_mut_ptr()) };
    let buf: [u8; 1] = [b'x'];
    let mut read_buf: [u8; 1] = [0];
    
    start = rdtsc();
    for _ in 0..ITERATIONS {
        unsafe {
            libc::write(fds[1], buf.as_ptr() as *const libc::c_void, 1);
            libc::read(fds[0], read_buf.as_mut_ptr() as *mut libc::c_void, 1);
        }
    }
    end = rdtsc();
    println!("Rust MVK Equivalent - IPC (Pipe R/W): {} cycles/op", (end - start) / ITERATIONS);
    unsafe {
        libc::close(fds[0]);
        libc::close(fds[1]);
    }

    // 5. Page Fault Benchmark
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
            // Force a page fault
            std::ptr::write_volatile(ptr as *mut u8, b'a');
            libc::munmap(ptr, 4096);
        }
    }
    end = rdtsc();
    println!("Rust MVK Equivalent - Page Fault Latency: {} cycles/op", (end - start) / (ITERATIONS / 100));

    // 6. I/O Benchmark (/dev/null write)
    let mut null_file = OpenOptions::new().write(true).open("/dev/null").unwrap();
    start = rdtsc();
    for _ in 0..ITERATIONS {
        null_file.write_all(&buf).unwrap();
    }
    end = rdtsc();
    println!("Rust MVK Equivalent - I/O (/dev/null): {} cycles/op", (end - start) / ITERATIONS);
}
