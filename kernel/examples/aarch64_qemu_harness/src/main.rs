#![no_std]
#![no_main]

#[cfg(target_arch = "aarch64")]
use core::arch::global_asm;
#[cfg(target_arch = "aarch64")]
use core::panic::PanicInfo;

// QEMU's `virt` machine (TCG, no KVM) starts a `-kernel`-loaded image at
// EL2 by default, with EL3 not present (no secure firmware). This entry
// point handles all three possible starting ELs defensively: EL3 drops
// to EL2h, EL2 drops to EL1h, and EL1 is used directly. Only once EL1 is
// reached does it set up a stack, clear BSS, and call into Rust.
#[cfg(target_arch = "aarch64")]
global_asm!(
    r#"
.section .text.entry
.global _start
_start:
    mrs x0, CurrentEL
    lsr x0, x0, #2
    cmp x0, #3
    b.eq from_el3
    cmp x0, #2
    b.eq from_el2
    b el1_entry

from_el3:
    mov x0, #0x501
    msr scr_el3, x0
    mov x0, #0x3c9
    msr spsr_el3, x0
    adr x0, from_el2
    msr elr_el3, x0
    eret

from_el2:
    mov x0, #0x80000000
    msr hcr_el2, x0
    mov x0, #0x3c5
    msr spsr_el2, x0
    adr x0, el1_entry
    msr elr_el2, x0
    eret

el1_entry:
    adr x0, __bss_start
    adr x1, __bss_end
clear_bss:
    cmp x0, x1
    b.ge bss_done
    str xzr, [x0], #8
    b clear_bss
bss_done:
    adr x0, __stack_end
    mov sp, x0

    bl kmain

hang:
    wfi
    b hang
"#
);

#[no_mangle]
pub extern "C" fn rust_eh_personality() {}

#[cfg(target_arch = "aarch64")]
#[no_mangle]
pub extern "C" fn kmain() -> ! {
    // SAFETY: `kmain` is called exactly once, by the entry assembly
    // above, only after BSS has been cleared and a valid stack is set
    // up in EL1 -- the preconditions every `runux_aarch64` function
    // called here requires (UART reachable via the identity mapping
    // QEMU provides by default, PSCI available on `virt`).
    unsafe {
        runux_aarch64::uart_puts("[INFO] Booting RunuX AArch64 QEMU Harness...\n");
        runux_aarch64::uart_puts("[INFO] Reached EL1, active core id: ");
        let id = runux_aarch64::core_id();
        let digit = (b'0' + (id as u8)) as char;
        let mut buf = [0u8; 2];
        buf[0] = digit as u8;
        buf[1] = b'\n';
        runux_aarch64::uart_puts(core::str::from_utf8_unchecked(&buf));

        runux_aarch64::uart_puts("[INFO] Initializing AArch64 subsystems...\n");
        runux_aarch64::aarch64_arch_init();
        runux_aarch64::aarch64_irq_init();
        runux_aarch64::aarch64_pgtable_init();

        // Exercise a real workspace type, not just print statements --
        // the same RAII newtype wrapper the x86_64 harness exercises
        // (AGENTS.md invariant #2: "SafePageFrame"), so all three
        // architectures now run genuine kernel_types logic at boot.
        let mut sample: u64 = 0xC0FFEE;
        let ptr = &mut sample as *mut u64 as *mut core::ffi::c_void;

        match kernel_types::SafePageFrame::new(ptr, 0) {
            Some(_frame) => runux_aarch64::uart_puts("[PASS] SafePageFrame::new(valid_ptr) -> Some\n"),
            None => panic_and_off(),
        }

        match kernel_types::SafePageFrame::new(core::ptr::null_mut(), 0) {
            None => runux_aarch64::uart_puts("[PASS] SafePageFrame::new(null) -> None (rejected as required)\n"),
            Some(_) => panic_and_off(),
        }

        runux_aarch64::uart_puts("[SUCCESS] RunuX AArch64 booted successfully inside QEMU!\n");

        // Clean shutdown via PSCI SYSTEM_OFF -- QEMU exits with code 0.
        runux_aarch64::psci_system_off();
    }
}

#[cfg(target_arch = "aarch64")]
unsafe fn panic_and_off() -> ! {
    runux_aarch64::uart_puts("\n[ERROR] KERNEL PANIC inside AArch64 Boot Harness!\n");
    runux_aarch64::psci_system_off();
}

#[cfg(target_arch = "aarch64")]
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    // SAFETY: same preconditions as `kmain`'s unsafe block -- the panic
    // handler only ever runs after boot has already reached EL1 with
    // UART and PSCI available.
    unsafe { panic_and_off() }
}

#[cfg(not(target_arch = "aarch64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
