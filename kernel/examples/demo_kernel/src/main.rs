#![no_std]
#![no_main]

use core::panic::PanicInfo;
use core::arch::{global_asm, asm};

global_asm!(r#"
.section .multiboot, "a"
.align 4
.long 0x1BADB002
.long 0x00
.long -(0x1BADB002)

.section .bss
.align 16
stack_bottom:
.skip 16384
stack_top:

.section .text
.global _start
_start:
    mov esp, offset stack_top

    # Enable SSE (required by Rust's optimized memory operations)
    mov eax, cr0
    and ax, 0xFFFB      # Clear EM bit (bit 2)
    or ax, 0x2          # Set MP bit (bit 1)
    mov cr0, eax
    mov eax, cr4
    or ax, 0x600        # Set OSFXSR (bit 9) and OSXMMEXCPT (bit 10)
    mov cr4, eax

    call kmain
    cli
1:  hlt
    jmp 1b
"#);

#[no_mangle]
pub unsafe extern "C" fn memset(dest: *mut u8, c: i32, n: usize) -> *mut u8 {
    let mut i = 0;
    while i < n {
        *dest.add(i) = c as u8;
        i += 1;
    }
    dest
}

#[no_mangle]
pub extern "C" fn rust_eh_personality() {}

// VGA text buffer constants
const VGA_BUFFER: *mut u8 = 0xb8000 as *mut u8;
const VGA_WIDTH: usize = 80;
const VGA_HEIGHT: usize = 25;

// Color codes for VGA text mode
#[allow(dead_code)]
#[repr(u8)]
enum Color {
    Black = 0,
    Blue = 1,
    Green = 2,
    Cyan = 3,
    Red = 4,
    Magenta = 5,
    Brown = 6,
    LightGray = 7,
    DarkGray = 8,
    LightBlue = 9,
    LightGreen = 10,
    LightCyan = 11,
    LightRed = 12,
    Pink = 13,
    Yellow = 14,
    White = 15,
}

#[derive(Copy, Clone)]
#[repr(C)]
struct ColorCode {
    value: u8,
}

impl ColorCode {
    fn new(foreground: Color, background: Color) -> ColorCode {
        ColorCode {
            value: (background as u8) << 4 | (foreground as u8),
        }
    }
}

// Kernel entry point
#[no_mangle]
pub extern "C" fn kmain() -> ! {
    clear_screen();

    print_banner();
    print_kernel_info();
    print_modules();
    print_features();
    print_prompt();

    // Halt the CPU
    loop {
        unsafe { asm!("hlt") };
    }
}

fn clear_screen() {
    let color = ColorCode::new(Color::LightGray, Color::Black);
    for i in 0..(VGA_WIDTH * VGA_HEIGHT) {
        unsafe {
            *VGA_BUFFER.offset(i as isize * 2) = b' ';
            *VGA_BUFFER.offset(i as isize * 2 + 1) = color.value;
        }
    }
}

fn print_banner() {
    let banner = [
        "================================================================================",
        "                       RUST LINUX MINI KERNEL - DEMO                           ",
        "================================================================================",
        "",
        "  ____            _     _     _                    __  __ _       _            ",
        " |  _ \\ _   _ ___| |_  | |   (_)_ __  _   ___  __ |  \\/  (_)_ __ (_)          ",
        " | |_) | | | / __| __| | |   | | '_ \\| | | \\ \\/ / | |\\/| | | '_ \\| |      ",
        " |  _ <| |_| \\__ \\ |_  | |___| | | | | |_| |>  <  | |  | | | | | | |          ",
        " |_| \\_\\\\__,_|___/\\__| |_____|_|_| |_|\\__,_/_/\\_\\ |_|  |_|_|_| |_|_|      ",
        "                                                                                ",
        "            _  __                    _                                          ",
        "           | |/ /___ _ __ _ __   ___| |                                        ",
        "           | ' // _ \\ '__| '_ \\ / _ \\ |                                      ",
        "           | . \\  __/ |  | | | |  __/ |                                        ",
        "           |_|\\_\\___|_|  |_| |_|\\___|_|                                      ",
        "",
        "================================================================================",
    ];

    let color = ColorCode::new(Color::LightCyan, Color::Black);
    for (row, line) in banner.iter().enumerate() {
        print_at(row, 0, line, color);
    }
}

fn print_kernel_info() {
    let row = 17;
    let color = ColorCode::new(Color::LightGreen, Color::Black);
    let label_color = ColorCode::new(Color::Yellow, Color::Black);

    print_at(row, 2, "Kernel Information:", label_color);
    print_at(row + 1, 4, "Version:     0.1.0-demo", color);
    print_at(row + 2, 4, "Build Date:  2026-05-18", color);
    print_at(row + 3, 4, "Architecture: x86_64", color);
    print_at(row + 4, 4, "Mode:        64-bit Protected Mode", color);
}

fn print_modules() {
    let row = 23;
    let color = ColorCode::new(Color::LightGreen, Color::Black);
    let label_color = ColorCode::new(Color::Yellow, Color::Black);

    print_at(row, 42, "Loaded Modules:", label_color);
    print_at(row + 1, 44, "[OK] kernel_types    - Core kernel types", color);
}

fn print_features() {
    let row_start = 23;
    let features = [
        "Features Demonstrated:",
        "  [*] VGA Text Mode Output",
        "  [*] Memory-Safe Rust Code",
        "  [*] No Standard Library (no_std)",
        "  [*] Direct Hardware Access",
        "  [*] Minimal Kernel Footprint",
    ];

    let color = ColorCode::new(Color::LightCyan, Color::Black);
    let label_color = ColorCode::new(Color::Yellow, Color::Black);

    for (i, feature) in features.iter().enumerate() {
        if i == 0 {
            print_at(row_start + i, 2, feature, label_color);
        } else {
            print_at(row_start + i, 2, feature, color);
        }
    }
}

fn print_prompt() {
    let row = VGA_HEIGHT - 1;
    let color = ColorCode::new(Color::White, Color::Blue);

    let prompt = " [Press Ctrl+C to exit QEMU] | Rust Mini Kernel Demo v0.1.0 | Press any key... ";
    print_at(row, 0, prompt, color);
}

fn outb(port: u16, val: u8) {
    unsafe {
        asm!("out dx, al", in("dx") port, in("al") val, options(nomem, nostack, preserves_flags));
    }
}

fn print_at(row: usize, col: usize, text: &str, color: ColorCode) {
    let offset = (row * VGA_WIDTH + col) * 2;
    for (i, byte) in text.bytes().enumerate() {
        outb(0x3F8, byte);
        if col + i >= VGA_WIDTH {
            break;
        }
        unsafe {
            *VGA_BUFFER.offset(offset as isize + i as isize * 2) = byte;
            *VGA_BUFFER.offset(offset as isize + i as isize * 2 + 1) = color.value;
        }
    }
    outb(0x3F8, b'\n');
}

// Panic handler
#[panic_handler]
fn panic(info: &PanicInfo) -> ! {
    let color = ColorCode::new(Color::White, Color::Red);
    print_at(12, 25, "!!! KERNEL PANIC !!!", color);

    if let Some(location) = info.location() {
        let mut msg = [0u8; 60];
        let panic_msg = format_panic_location(location, &mut msg);
        print_at(13, 10, panic_msg, ColorCode::new(Color::LightRed, Color::Black));
    }

    loop {
        unsafe { asm!("hlt") };
    }
}

fn format_panic_location<'a>(location: &core::panic::Location, buf: &'a mut [u8]) -> &'a str {
    let file = location.file();
    let line = location.line();

    let mut i = 0;
    for b in b"Panic at: ".iter() {
        if i >= buf.len() { break; }
        buf[i] = *b;
        i += 1;
    }

    for b in file.bytes() {
        if i >= buf.len() { break; }
        buf[i] = b;
        i += 1;
    }

    if i < buf.len() {
        buf[i] = b':';
        i += 1;
    }

    // Simple line number conversion
    let mut line_val = line;
    let mut divisor = 10000;
    let mut started = false;

    while divisor > 0 {
        let digit = line_val / divisor;
        if digit > 0 || started || divisor == 1 {
            if i < buf.len() {
                buf[i] = b'0' + (digit as u8);
                i += 1;
                started = true;
            }
        }
        line_val %= divisor;
        divisor /= 10;
    }

    core::str::from_utf8(&buf[..i]).unwrap_or("Panic!")
}

// Assembly magic for inline asm
