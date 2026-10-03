/* RunuX RISC-V Linker Script
 * Target: riscv64gc-unknown-none-elf
 * Machine: QEMU virt / Banana Pi BPI-F3 (SpacemiT K1)
 *
 * QEMU virt RAM starts at 0x80000000
 * OpenSBI firmware loads kernel at 0x80200000
 */

OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY {
    /* Kernel loaded by OpenSBI at 0x80200000 */
    RAM (rwx) : ORIGIN = 0x80200000, LENGTH = 128M
}

SECTIONS {
    . = 0x80200000;

    .text : {
        *(.text.entry)      /* _start entry point */
        *(.text .text.*)
    } > RAM

    .rodata : ALIGN(4K) {
        *(.rodata .rodata.*)
        *(.srodata .srodata.*)
    } > RAM

    .data : ALIGN(4K) {
        *(.data .data.*)
        *(.sdata .sdata.*)
    } > RAM

    .bss : ALIGN(4K) {
        __bss_start = .;
        *(.bss .bss.*)
        *(.sbss .sbss.*)
        __bss_end = .;
    } > RAM

    /* Kernel stack (64 KiB per HART, 8 HARTs for K1) */
    . = ALIGN(4K);
    __stack_start = .;
    . += 64K * 8;
    __stack_end = .;

    /* Heap starts after stack */
    __heap_start = .;

    /DISCARD/ : {
        *(.eh_frame*)
        *(.note*)
    }
}
