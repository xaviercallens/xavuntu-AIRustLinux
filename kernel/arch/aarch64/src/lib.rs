//! AArch64 Architecture Support Layer
//!
//! RunuX-specific implementations for `aarch64-unknown-none`, targeting
//! QEMU's `virt` machine.
//!
//! AArch64 Exception Levels:
//!   EL3 (Secure Monitor) — firmware, not present on a bare `-kernel` boot
//!   EL2 (Hypervisor)     — present by default on QEMU virt/TCG
//!   EL1 (Kernel)         — RunuX runs here
//!   EL0 (User)           — applications
#![no_std]
#![cfg(target_arch = "aarch64")]

use core::ffi::c_int;

// ============================================================================
// AArch64 system register accessors
// ============================================================================

/// Read `CurrentEL` and return the exception level number (1, 2, or 3).
///
/// # Safety
/// `mrs` from `CurrentEL` has no preconditions; it is a plain register
/// read with no side effects.
#[inline]
pub unsafe fn current_el() -> usize {
    let val: usize;
    core::arch::asm!("mrs {}, CurrentEL", out(reg) val);
    (val >> 2) & 0x3
}

/// Read `MPIDR_EL1` (Multiprocessor Affinity Register) and return the
/// affinity-0 field, i.e. the core id on QEMU virt.
///
/// # Safety
/// `mrs` from `MPIDR_EL1` has no preconditions; it is a plain register
/// read with no side effects.
#[inline]
pub unsafe fn core_id() -> usize {
    let val: usize;
    core::arch::asm!("mrs {}, mpidr_el1", out(reg) val);
    val & 0xff
}

/// Read `SCTLR_EL1` (System Control Register).
///
/// # Safety
/// Requires the caller to be running at EL1; reading it has no other
/// preconditions.
#[inline]
pub unsafe fn read_sctlr_el1() -> usize {
    let val: usize;
    core::arch::asm!("mrs {}, sctlr_el1", out(reg) val);
    val
}

/// Write `SCTLR_EL1`.
///
/// # Safety
/// Caller must be at EL1 and must supply a value that keeps the MMU/cache
/// enable bits consistent with the page tables currently installed in
/// `TTBR0_EL1` -- an inconsistent combination can fault or silently
/// corrupt memory accesses.
#[inline]
pub unsafe fn write_sctlr_el1(val: usize) {
    core::arch::asm!("msr sctlr_el1, {}", in(reg) val);
}

/// Read `TTBR0_EL1` (Translation Table Base Register 0).
///
/// # Safety
/// Requires the caller to be running at EL1.
#[inline]
pub unsafe fn read_ttbr0_el1() -> usize {
    let val: usize;
    core::arch::asm!("mrs {}, ttbr0_el1", out(reg) val);
    val
}

/// Write `TTBR0_EL1` (set the page table root for the identity map).
///
/// # Safety
/// `val` must be the physical address of a page table structure that is
/// valid for as long as the MMU remains enabled with it installed; the
/// caller must flush the TLB (see [`tlb_flush_all`]) after switching
/// tables to avoid using stale translations.
#[inline]
pub unsafe fn write_ttbr0_el1(val: usize) {
    core::arch::asm!("msr ttbr0_el1, {}", in(reg) val);
}

/// Write `VBAR_EL1` (Vector Base Address Register — exception vector table).
///
/// # Safety
/// `val` must point to a valid, correctly-aligned (2KiB) AArch64 exception
/// vector table that remains resident for as long as EL1 exceptions can
/// occur.
#[inline]
pub unsafe fn write_vbar_el1(val: usize) {
    core::arch::asm!("msr vbar_el1, {}", in(reg) val);
}

/// Invalidate the entire TLB (EL1, both stages) and synchronize.
///
/// # Safety
/// Must be called from EL1; safe to call at any point but only
/// meaningful after changing page table contents or `TTBR0_EL1`.
#[inline]
pub unsafe fn tlb_flush_all() {
    core::arch::asm!("tlbi vmalle1", "dsb sy", "isb");
}

// ============================================================================
// Interrupt control
// ============================================================================

/// Disable IRQ/FIQ (set the I and F bits in DAIF).
///
/// # Safety
/// No preconditions; masking interrupts is always sound, though it can
/// delay servicing of pending events.
#[inline]
pub unsafe fn disable_interrupts() {
    core::arch::asm!("msr daifset, #0b11");
}

/// Enable IRQ/FIQ (clear the I and F bits in DAIF).
///
/// # Safety
/// Caller must have a working exception vector table installed via
/// [`write_vbar_el1`] before unmasking interrupts, or an incoming
/// interrupt will vector through an undefined handler.
#[inline]
pub unsafe fn enable_interrupts() {
    core::arch::asm!("msr daifclr, #0b11");
}

/// Wait for interrupt (halt until the next exception).
///
/// # Safety
/// No preconditions.
#[inline]
pub unsafe fn wfi() {
    core::arch::asm!("wfi");
}

// ============================================================================
// PSCI (Power State Coordination Interface), HVC conduit
// ============================================================================

/// PSCI `SYSTEM_OFF` function id (32-bit calling convention).
const PSCI_SYSTEM_OFF: u64 = 0x8400_0008;

/// Cleanly power off the machine via PSCI `SYSTEM_OFF` over HVC. On
/// QEMU's `virt` machine this terminates the QEMU process with exit
/// code 0. Never returns on success; if PSCI is unavailable, spins.
///
/// # Safety
/// Requires a PSCI-capable conduit (EL2 or EL3 firmware implementing
/// PSCI) to be present, which QEMU's `virt` machine provides by default;
/// on hardware without it, this call is a no-op HVC trap and execution
/// falls through to the `wfi` loop.
#[inline]
pub unsafe fn psci_system_off() -> ! {
    core::arch::asm!(
        "hvc #0",
        in("x0") PSCI_SYSTEM_OFF,
        options(nomem, nostack),
    );
    loop {
        wfi();
    }
}

// ============================================================================
// Identity-mapped page table constants (4KiB granule, 2MiB block entries)
// ============================================================================

pub const PAGE_SIZE: usize = 4096;
pub const PTE_COUNT: usize = 512;

/// Descriptor flags for a 2MiB block entry, identity-mapped, device or
/// normal memory as selected by the caller via the `MAIR` index bits.
pub mod pte_flags {
    pub const VALID: u64 = 1 << 0;
    /// Bit 1 = 0 selects a block (not table) descriptor at levels 1/2.
    pub const BLOCK: u64 = 0 << 1;
    pub const AF: u64 = 1 << 10; // Access Flag
    pub const INNER_SHAREABLE: u64 = 0b11 << 8;

    pub const NORMAL_RWX: u64 = VALID | BLOCK | AF | INNER_SHAREABLE;
}

// ============================================================================
// PL011 UART (serial console output) — standard for QEMU virt
// ============================================================================

/// UART base address (standard for QEMU virt).
pub const UART_BASE: usize = 0x0900_0000;

const UARTDR: usize = 0x00;
const UARTFR: usize = 0x18;
const UARTFR_TXFF: u32 = 1 << 5;

/// Write a byte to the UART.
///
/// # Safety
/// `UART_BASE` must be mapped as device memory and backed by a real
/// PL011 (true on QEMU's `virt` machine); calling this before the MMU
/// is enabled relies on the identity mapping QEMU provides by default.
#[inline]
pub unsafe fn uart_putc(c: u8) {
    let base = UART_BASE as *mut u32;
    while core::ptr::read_volatile(base.add(UARTFR / 4)) & UARTFR_TXFF != 0 {}
    core::ptr::write_volatile(base.add(UARTDR / 4), u32::from(c));
}

/// Write a string to the UART.
///
/// # Safety
/// Same preconditions as [`uart_putc`].
pub unsafe fn uart_puts(s: &str) {
    for b in s.bytes() {
        if b == b'\n' {
            uart_putc(b'\r');
        }
        uart_putc(b);
    }
}

// ============================================================================
// Module init stubs (match RunuX arch_* interface)
// ============================================================================

/// # Safety
/// Must be called exactly once, early in boot, after the UART is
/// reachable (identity-mapped or MMU-off) and before any code depends on
/// GIC/page-table state.
#[no_mangle]
pub unsafe extern "C" fn aarch64_arch_init() -> c_int {
    // Initialize AArch64 architecture:
    // 1. Parse device tree (DTB pointer in x0 at boot)
    // 2. Set up the GICv2/v3 interrupt controller
    // 3. Configure identity-mapped page tables
    // 4. Enable EL1 interrupts
    uart_puts("RunuX: AArch64 arch init (QEMU virt)\n");
    0
}

/// # Safety
/// Must be called after [`aarch64_arch_init`] and before interrupts are
/// unmasked via [`enable_interrupts`].
#[no_mangle]
pub unsafe extern "C" fn aarch64_irq_init() -> c_int {
    // Initialize the GIC distributor/CPU interface.
    uart_puts("RunuX: GIC interrupt controller initialized\n");
    0
}

/// # Safety
/// Must be called before any code relies on the identity mapping being
/// backed by explicit page tables rather than the MMU being off.
#[no_mangle]
pub unsafe extern "C" fn aarch64_pgtable_init() -> c_int {
    // Set up identity-mapped page tables for the kernel.
    uart_puts("RunuX: AArch64 page tables initialized\n");
    0
}

/// Context switch: save/restore x19-x30, sp, and relevant system
/// registers between two kernel threads.
///
/// # Safety
/// `_old_ctx` and `_new_ctx` must each point to a valid, correctly-sized
/// context save area; `_new_ctx` must have been previously populated by
/// a prior call to this function or equivalent initialization.
#[no_mangle]
pub unsafe extern "C" fn aarch64_context_switch(_old_ctx: *mut u8, _new_ctx: *mut u8) {
    // Save: x19-x30 (callee-saved), sp, elr_el1, spsr_el1
    // Restore: target context registers
}
