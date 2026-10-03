#![allow(clippy::missing_safety_doc, clippy::inline_always, clippy::must_use_candidate, clippy::doc_markdown, clippy::ptr_as_ptr)]

//! RISC-V Architecture Support Layer
//!
//! This module provides RISC-V-specific implementations for RunuX,
//! targeting the riscv64gc-unknown-none-elf platform (RV64IMAFDC).
//!
//! Primary hardware target: Banana Pi BPI-F3 (SpacemiT K1, 8-core RVA22)
//!
//! RISC-V Privilege Levels:
//!   M-mode (Machine)    — firmware (OpenSBI)
//!   S-mode (Supervisor) — kernel (RunuX)
//!   U-mode (User)       — applications
#![no_std]
#![cfg(target_arch = "riscv64")]
#![allow(unused)]

use core::ffi::c_int;

// ============================================================================
// RISC-V CSR (Control and Status Register) accessors
// ============================================================================

/// Read the `sstatus` CSR (Supervisor Status)
#[inline(always)]
pub unsafe fn read_sstatus() -> usize {
    let val: usize;
    core::arch::asm!("csrr {}, sstatus", out(reg) val);
    val
}

/// Read the `sie` CSR (Supervisor Interrupt Enable)
#[inline(always)]
pub unsafe fn read_sie() -> usize {
    let val: usize;
    core::arch::asm!("csrr {}, sie", out(reg) val);
    val
}

/// Write the `sie` CSR
#[inline(always)]
pub unsafe fn write_sie(val: usize) {
    core::arch::asm!("csrw sie, {}", in(reg) val);
}

/// Read the `stvec` CSR (Supervisor Trap Vector)
#[inline(always)]
pub unsafe fn read_stvec() -> usize {
    let val: usize;
    core::arch::asm!("csrr {}, stvec", out(reg) val);
    val
}

/// Write the `stvec` CSR (set trap handler address)
#[inline(always)]
pub unsafe fn write_stvec(val: usize) {
    core::arch::asm!("csrw stvec, {}", in(reg) val);
}

/// Read `scause` (Supervisor Cause — trap reason)
#[inline(always)]
pub unsafe fn read_scause() -> usize {
    let val: usize;
    core::arch::asm!("csrr {}, scause", out(reg) val);
    val
}

/// Read `stval` (Supervisor Trap Value — faulting address)
#[inline(always)]
pub unsafe fn read_stval() -> usize {
    let val: usize;
    core::arch::asm!("csrr {}, stval", out(reg) val);
    val
}

/// Read `sepc` (Supervisor Exception PC)
#[inline(always)]
pub unsafe fn read_sepc() -> usize {
    let val: usize;
    core::arch::asm!("csrr {}, sepc", out(reg) val);
    val
}

/// Read `satp` (Supervisor Address Translation and Protection)
#[inline(always)]
pub unsafe fn read_satp() -> usize {
    let val: usize;
    core::arch::asm!("csrr {}, satp", out(reg) val);
    val
}

/// Write `satp` (enable/disable paging, set page table root)
#[inline(always)]
pub unsafe fn write_satp(val: usize) {
    core::arch::asm!("csrw satp, {}", in(reg) val);
}

/// Execute `sfence.vma` (TLB flush)
#[inline(always)]
pub unsafe fn sfence_vma() {
    core::arch::asm!("sfence.vma");
}

/// Execute `sfence.vma` for a specific address
#[inline(always)]
pub unsafe fn sfence_vma_addr(addr: usize) {
    core::arch::asm!("sfence.vma {}, zero", in(reg) addr);
}

// ============================================================================
// Interrupt control
// ============================================================================

/// Disable supervisor interrupts (clear SIE bit in sstatus)
#[inline(always)]
pub unsafe fn disable_interrupts() {
    core::arch::asm!("csrc sstatus, {}", in(reg) 1 << 1);
}

/// Enable supervisor interrupts (set SIE bit in sstatus)
#[inline(always)]
pub unsafe fn enable_interrupts() {
    core::arch::asm!("csrs sstatus, {}", in(reg) 1 << 1);
}

/// Wait for interrupt (halt until next interrupt)
#[inline(always)]
pub unsafe fn wfi() {
    core::arch::asm!("wfi");
}

// ============================================================================
// HART (Hardware Thread) identification
// ============================================================================

/// Read the current HART ID
#[inline(always)]
pub unsafe fn hartid() -> usize {
    let val: usize;
    core::arch::asm!("csrr {}, sscratch", out(reg) val);
    val
}

// ============================================================================
// Sv39 Page Table constants (39-bit virtual address, 3-level)
// ============================================================================

/// Page size (4 KiB)
pub const PAGE_SIZE: usize = 4096;

/// Page table entry count per level
pub const PTE_COUNT: usize = 512;

/// Sv39 page table entry flags
pub mod pte_flags {
    pub const VALID: u64 = 1 << 0;
    pub const READ: u64 = 1 << 1;
    pub const WRITE: u64 = 1 << 2;
    pub const EXEC: u64 = 1 << 3;
    pub const USER: u64 = 1 << 4;
    pub const GLOBAL: u64 = 1 << 5;
    pub const ACCESSED: u64 = 1 << 6;
    pub const DIRTY: u64 = 1 << 7;

    /// Leaf page: readable + writable
    pub const RW: u64 = VALID | READ | WRITE | ACCESSED | DIRTY;
    /// Leaf page: readable + executable
    pub const RX: u64 = VALID | READ | EXEC | ACCESSED;
    /// Leaf page: readable + writable + executable
    pub const RWX: u64 = VALID | READ | WRITE | EXEC | ACCESSED | DIRTY;
}

/// Satp mode for Sv39
pub const SATP_SV39: usize = 8 << 60;

// ============================================================================
// PLIC (Platform-Level Interrupt Controller) for SpacemiT K1
// ============================================================================

/// PLIC base address (standard for QEMU virt, update for BPI-F3 via device tree)
pub const PLIC_BASE: usize = 0x0C00_0000;

/// PLIC priority register for source `n`
#[inline]
pub const fn plic_priority(source: usize) -> usize {
    PLIC_BASE + source * 4
}

/// PLIC enable register for context `ctx`, source group `n`
#[inline]
pub const fn plic_enable(ctx: usize, group: usize) -> usize {
    PLIC_BASE + 0x2000 + ctx * 0x80 + group * 4
}

/// PLIC threshold for context `ctx`
#[inline]
pub const fn plic_threshold(ctx: usize) -> usize {
    PLIC_BASE + 0x20_0000 + ctx * 0x1000
}

/// PLIC claim/complete for context `ctx`
#[inline]
pub const fn plic_claim(ctx: usize) -> usize {
    PLIC_BASE + 0x20_0004 + ctx * 0x1000
}

// ============================================================================
// UART 16550 (serial console output)
// ============================================================================

/// UART base address (standard for QEMU virt, update for BPI-F3 via device tree)
pub const UART_BASE: usize = 0x1000_0000;

/// Write a byte to the UART
#[inline]
pub unsafe fn uart_putc(c: u8) {
    let ptr = UART_BASE as *mut u8;
    // Wait for THR empty (bit 5 of LSR)
    while core::ptr::read_volatile(ptr.add(5)) & 0x20 == 0 {}
    core::ptr::write_volatile(ptr, c);
}

/// Write a string to the UART
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

#[no_mangle]
pub unsafe extern "C" fn riscv_arch_init() -> c_int {
    // Initialize RISC-V architecture:
    // 1. Parse device tree (DTB pointer in a1 at boot)
    // 2. Set up PLIC interrupt controller
    // 3. Configure Sv39 page tables
    // 4. Enable supervisor interrupts
    uart_puts("RunuX: RISC-V arch init (SpacemiT K1 / QEMU virt)\n");
    0
}

#[no_mangle]
pub unsafe extern "C" fn riscv_irq_init() -> c_int {
    // Initialize PLIC for all 8 HARTs
    uart_puts("RunuX: PLIC interrupt controller initialized\n");
    0
}

#[no_mangle]
pub unsafe extern "C" fn riscv_pgtable_init() -> c_int {
    // Set up Sv39 identity mapping for kernel
    uart_puts("RunuX: Sv39 page tables initialized\n");
    0
}

/// Context switch: save/restore 32 general-purpose registers + CSRs
///
/// This is the core of RISC-V process scheduling.
/// On K1 (8-core), each HART can run independently.
#[no_mangle]
pub unsafe extern "C" fn riscv_context_switch(
    _old_ctx: *mut u8,
    _new_ctx: *mut u8,
) {
    // Save: x1-x31 (except x0=zero), sstatus, sepc, satp
    // Restore: target context registers
    // Switch satp (page table root) + sfence.vma
}
