#![no_std]
#![no_main]

#[cfg(target_arch = "riscv64")]
use core::panic::PanicInfo;
#[cfg(target_arch = "riscv64")]
use core::arch::global_asm;

#[cfg(target_arch = "riscv64")]
global_asm!(r#"
.section .text.entry
.global _start
_start:
    # Save hartid in sscratch
    csrw sscratch, a0

    # Setup stack pointer for S-mode execution
    la sp, __stack_start
    li t0, 65536         # 64 KiB stack size
    addi t1, a0, 1       # (hartid + 1)
    mul t0, t0, t1       # (hartid + 1) * 64K
    add sp, sp, t0       # sp = __stack_start + (hartid + 1) * 64K

    # Clear BSS on hart 0
    bnez a0, .Lskip_bss
    la t0, __bss_start
    la t1, __bss_end
.Lclear_bss:
    bgeu t0, t1, .Lskip_bss
    sd zero, 0(t0)
    addi t0, t0, 8
    j .Lclear_bss
.Lskip_bss:
    # Call S-mode kmain
    call kmain
    
.Lloop:
    wfi
    j .Lloop
"#);

#[no_mangle]
pub extern "C" fn rust_eh_personality() {}

#[cfg(target_arch = "riscv64")]
#[no_mangle]
pub extern "C" fn kmain() -> ! {
    unsafe {
        runux_riscv64::uart_puts("[INFO] Booting RunuX RISC-V QEMU Harness...\n");
        runux_riscv64::uart_puts("[INFO] Active HART ID: ");
        let id = runux_riscv64::hartid();
        let digit = (b'0' + (id as u8)) as char;
        let mut buf = [0u8; 2];
        buf[0] = digit as u8;
        buf[1] = b'\n';
        runux_riscv64::uart_puts(core::str::from_utf8_unchecked(&buf));

        // Initialize core subsystems using arch stubs
        runux_riscv64::uart_puts("[INFO] Initializing RISC-V subsystems...\n");
        runux_riscv64::riscv_arch_init();
        runux_riscv64::riscv_irq_init();
        runux_riscv64::riscv_pgtable_init();

        runux_riscv64::uart_puts("[SUCCESS] RunuX RISC-V booted successfully inside QEMU!\n");

        // Trigger successful QEMU shutdown (SiFive Test finisher at 0x100000)
        core::ptr::write_volatile(0x100000 as *mut u32, 0x5555);
    }

    loop {}
}

#[cfg(target_arch = "riscv64")]
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    unsafe {
        runux_riscv64::uart_puts("\n[ERROR] KERNEL PANIC inside RISC-V Boot Harness!\n");
        // Trigger failed QEMU shutdown (SiFive Test finisher at 0x100000)
        core::ptr::write_volatile(0x100000 as *mut u32, 0x3333);
    }
    loop {}
}

#[cfg(not(target_arch = "riscv64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
