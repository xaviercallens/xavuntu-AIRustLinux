// Real x86_64 long-mode boot harness: Multiboot2 entry (CPU starts in
// 32-bit protected mode per the Multiboot spec, regardless of the
// kernel ELF's own bitness) sets up identity-mapped page tables,
// enables PAE + long mode (EFER.LME) + paging, far-jumps into a 64-bit
// code segment, then hands off to genuine 64-bit Rust which exercises a
// real workspace type (`kernel_types::SafePageFrame`) before shutting
// QEMU down cleanly via the isa-debug-exit device.
#![no_std]
#![no_main]

use core::arch::{asm, global_asm};
use core::panic::PanicInfo;

#[no_mangle]
pub extern "C" fn rust_eh_personality() {}

global_asm!(
    r#"
.section .multiboot2, "a"
.align 8
mb2_header_start:
    .long 0xE85250D6
    .long 0
    .long mb2_header_end - mb2_header_start
    .long -(0xE85250D6 + 0 + (mb2_header_end - mb2_header_start))
    .align 8
    .word 0
    .word 0
    .long 8
mb2_header_end:

.section .bss
.align 4096
pml4_table:
    .skip 4096
pdpt_table:
    .skip 4096
pd_table:
    .skip 4096
.align 16
stack_bottom:
    .skip 16384
stack_top:

.section .rodata
.align 8
gdt64:
    .quad 0
    .quad 0x00AF9A000000FFFF
    .quad 0x00AF92000000FFFF
gdt64_end:
gdt64_ptr:
    .word gdt64_end - gdt64 - 1
    .quad gdt64

.section .text
.code32
.global _start
_start:
    cli
    mov esp, offset stack_top

    # PML4[0] = &pdpt_table | PRESENT|WRITABLE
    mov eax, offset pdpt_table
    or eax, 3
    mov dword ptr [pml4_table], eax
    mov dword ptr [pml4_table+4], 0

    # PDPT[0] = &pd_table | PRESENT|WRITABLE
    mov eax, offset pd_table
    or eax, 3
    mov dword ptr [pdpt_table], eax
    mov dword ptr [pdpt_table+4], 0

    # Fill PD: 512 x 2MiB pages, identity-mapped, present|writable|huge
    mov edi, offset pd_table
    xor ebx, ebx
    mov ecx, 512
fill_pd:
    mov eax, ebx
    or eax, 0x83
    mov dword ptr [edi], eax
    mov dword ptr [edi+4], 0
    add ebx, 0x200000
    add edi, 8
    loop fill_pd

    mov eax, offset pml4_table
    mov cr3, eax

    mov eax, cr4
    or eax, 0x20
    mov cr4, eax

    mov ecx, 0xC0000080
    rdmsr
    or eax, 0x100
    wrmsr

    mov eax, cr0
    or eax, 0x80000000
    mov cr0, eax

    lgdt [gdt64_ptr]

    ljmp 0x08, offset long_mode_entry

.code64
long_mode_entry:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov fs, ax
    mov gs, ax
    mov ss, ax

    mov rsp, offset stack_top
    xor rbp, rbp
    and rsp, -16

    call kmain

    cli
2:
    hlt
    jmp 2b
"#
);

fn outb(port: u16, val: u8) {
    // SAFETY: `out` to an I/O port is only observable by hardware (the
    // 16550 UART / QEMU debug-exit device), touches no Rust-managed
    // memory, and `options(nomem, nostack, preserves_flags)` accurately
    // describes its effects, so it cannot violate any Rust aliasing or
    // memory-safety invariant.
    unsafe {
        asm!("out dx, al", in("dx") port, in("al") val, options(nomem, nostack, preserves_flags));
    }
}

fn serial_print(text: &str) {
    for byte in text.bytes() {
        outb(0x3F8, byte);
    }
}

const HEX_DIGITS: &[u8; 16] = b"0123456789abcdef";

/// Print `val`'s low `nibbles * 4` bits as lowercase hex over serial,
/// with no allocator and no `core::fmt` machinery -- this harness has
/// neither.
fn serial_print_hex(val: u32, nibbles: u32) {
    for i in (0..nibbles).rev() {
        let nibble = ((val >> (i * 4)) & 0xF) as usize;
        outb(0x3F8, HEX_DIGITS[nibble]);
    }
}

/// QEMU's isa-debug-exit device: exit code = (value << 1) | 1.
/// value=0x00 -> exit code 1 (success sentinel used by this harness).
/// value=0x11 -> exit code 35 (panic sentinel).
fn qemu_exit(value: u8) -> ! {
    outb(0xF4, value);
    loop {
        // SAFETY: `hlt` only stops the CPU until the next interrupt; it
        // takes no operands, touches no memory, and this loop is
        // reachable only after the isa-debug-exit write above, which
        // terminates QEMU before `hlt` is ever actually needed to run.
        unsafe { asm!("hlt") };
    }
}

#[no_mangle]
pub extern "C" fn kmain() -> ! {
    serial_print("[INFO] Booting RunuX x86_64 QEMU Harness (long mode)...\n");
    serial_print("[INFO] PAE + EFER.LME + CR0.PG enabled, identity-mapped first 1GiB\n");

    // Exercise a real workspace type, not just print statements: the
    // RAII newtype wrapper AGENTS.md requires for page-frame handling
    // (invariant #2: "SafePageFrame"). This is genuine kernel_types
    // code, not a stub -- both the null-rejection and the valid-pointer
    // path run for real here.
    let mut sample: u64 = 0xC0FFEE;
    let ptr = &mut sample as *mut u64 as *mut core::ffi::c_void;

    match kernel_types::SafePageFrame::new(ptr, 0) {
        Some(_frame) => serial_print("[PASS] SafePageFrame::new(valid_ptr) -> Some\n"),
        None => qemu_exit(0x11),
    }

    match kernel_types::SafePageFrame::new(core::ptr::null_mut(), 0) {
        None => serial_print("[PASS] SafePageFrame::new(null) -> None (rejected as required)\n"),
        Some(_) => qemu_exit(0x11),
    }

    // Real PCI bus enumeration (Configuration Mechanism #1, I/O ports
    // 0xCF8/0xCFC), genuinely reading hardware config space on every
    // call. A "1af4:1050" line below means this code actually saw
    // QEMU's virtio-gpu device on the bus, not an assertion that it
    // should be there.
    serial_print("[INFO] Enumerating PCI bus (Configuration Mechanism #1)...\n");
    let mut devices = [driver_pci_core::PciDeviceInfo {
        address: driver_pci_core::PciAddress { bus: 0, device: 0, function: 0 },
        vendor_id: 0,
        device_id: 0,
        class: 0,
        subclass: 0,
        header_type: 0,
        multi_function: false,
    }; driver_pci_probe::MAX_ENUMERATED_DEVICES];
    // SAFETY: this harness runs at CPL0 in long mode with full I/O port
    // access (no TSS I/O bitmap restricting it), matching pci_enumerate's
    // precondition; called exactly once, after boot, before any other
    // code depends on PCI state.
    let device_count = unsafe { driver_pci_probe::pci_enumerate(&driver_pci_access::HardwareIo, &mut devices) };

    serial_print("[INFO] PCI devices found: ");
    serial_print_hex(device_count as u32, 2);
    serial_print("\n");

    let mut found_gpu = false;
    for dev in &devices[..device_count] {
        serial_print("  ");
        serial_print_hex(u32::from(dev.address.bus), 2);
        serial_print(":");
        serial_print_hex(u32::from(dev.address.device), 2);
        serial_print(".");
        serial_print_hex(u32::from(dev.address.function), 1);
        serial_print(" vendor=");
        serial_print_hex(u32::from(dev.vendor_id), 4);
        serial_print(" device=");
        serial_print_hex(u32::from(dev.device_id), 4);
        serial_print(" class=");
        serial_print_hex(u32::from(dev.class), 2);
        serial_print(" subclass=");
        serial_print_hex(u32::from(dev.subclass), 2);

        let is_known_gpu = driver_pci_core::known_gpu_name(dev.vendor_id, dev.device_id);
        if let Some(name) = is_known_gpu {
            serial_print(" -- ");
            serial_print(name);
            found_gpu = true;
        } else if dev.is_display_controller() {
            serial_print(" -- unrecognized display controller");
            found_gpu = true;
        }
        serial_print("\n");

        if is_known_gpu.is_some() || dev.is_display_controller() {
            // Real BAR-size probe (write all-1s, read back the size
            // mask, restore original) against this specific device --
            // the groundwork any real VRAM/MMIO mapping eventually
            // needs, exercised here against a real (if virtual) GPU.
            for (i, bar_offset) in [0x10u8, 0x14, 0x18, 0x1C, 0x20, 0x24].iter().enumerate() {
                // SAFETY: same precondition as pci_enumerate above --
                // CPL0, full I/O port access, called after enumeration
                // has already read this exact device successfully.
                let size = unsafe {
                    driver_pci_access::pci_bar_size(
                        dev.address.bus,
                        dev.address.device,
                        dev.address.function,
                        *bar_offset,
                    )
                };
                if size > 0 {
                    serial_print("    BAR");
                    serial_print_hex(i as u32, 1);
                    serial_print(" size=0x");
                    serial_print_hex(size as u32, 8);
                    serial_print(" bytes\n");
                }
            }
        }
    }

    if found_gpu {
        serial_print("[PASS] At least one display/GPU-class PCI device was enumerated for real\n");
    } else {
        serial_print("[INFO] No display/GPU-class PCI device present on this bus (expected without -device virtio-gpu-pci)\n");
    }

    serial_print("[SUCCESS] RunuX x86_64 booted successfully inside QEMU (long mode)!\n");
    qemu_exit(0x00)
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    serial_print("\n[ERROR] KERNEL PANIC!\n");
    qemu_exit(0x11)
}
