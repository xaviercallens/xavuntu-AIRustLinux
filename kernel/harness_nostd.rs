#![no_std]
#![no_main]

use core::arch::asm;
use core::panic::PanicInfo;

const ITERATIONS: u64 = 100_000;

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}

fn rdtsc() -> u64 {
    let mut lo: u32;
    let mut hi: u32;
    unsafe {
        asm!("rdtsc", out("eax") lo, out("edx") hi, options(nomem, nostack));
    }
    ((hi as u64) << 32) | (lo as u64)
}

unsafe fn sys_getpid() {
    asm!(
        "syscall",
        in("rax") 39, // getpid
        out("rcx") _,
        out("r11") _,
        options(nostack, preserves_flags)
    );
}

// Minimal print function
unsafe fn print_num(label: &str, num: u64) {
    let mut buf = [0u8; 128];
    let mut i = 0;
    
    for b in label.as_bytes() {
        buf[i] = *b;
        i += 1;
    }
    
    let mut n = num;
    let mut n_len = 0;
    if n == 0 {
        buf[i] = b'0';
        i += 1;
    } else {
        let mut temp = n;
        while temp > 0 {
            n_len += 1;
            temp /= 10;
        }
        let mut j = i + n_len - 1;
        while n > 0 {
            buf[j] = b'0' + (n % 10) as u8;
            n /= 10;
            j -= 1;
        }
        i += n_len;
    }
    
    buf[i] = b'\n';
    i += 1;
    
    asm!(
        "syscall",
        in("rax") 1, // write
        in("rdi") 1, // stdout
        in("rsi") buf.as_ptr(),
        in("rdx") i,
        out("rcx") _,
        out("r11") _,
        options(nostack, preserves_flags)
    );
}

#[no_mangle]
pub extern "C" fn _start() -> ! {
    let mut start: u64;
    let mut end: u64;

    // Syscall Benchmark (no_std raw syscall)
    start = rdtsc();
    for _ in 0..ITERATIONS {
        unsafe { sys_getpid() };
    }
    end = rdtsc();
    
    unsafe {
        print_num("Rust Pure no_std - Syscall (getpid) cycles: ", (end - start) / ITERATIONS);
    }
    
    // Exit
    unsafe {
        asm!(
            "syscall",
            in("rax") 60, // exit
            in("rdi") 0,
            options(noreturn)
        );
    }
}
