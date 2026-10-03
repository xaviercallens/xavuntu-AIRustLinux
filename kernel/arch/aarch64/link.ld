/* RunuX AArch64 Linker Script
 * Target: aarch64-unknown-none
 * Machine: QEMU virt
 *
 * QEMU virt RAM starts at 0x40000000; kernels conventionally load at
 * a 0x80000 offset into it (the same convention the Linux/arm64 Image
 * boot protocol uses), which is also where QEMU's own -kernel loader
 * expects room below the image for the DTB it places automatically.
 */

OUTPUT_ARCH(aarch64)
ENTRY(_start)

MEMORY {
    RAM (rwx) : ORIGIN = 0x40080000, LENGTH = 128M
}

SECTIONS {
    . = 0x40080000;

    .text : {
        *(.text.entry)
        *(.text .text.*)
    } > RAM

    .rodata : ALIGN(4K) {
        *(.rodata .rodata.*)
    } > RAM

    .data : ALIGN(4K) {
        *(.data .data.*)
    } > RAM

    .bss : ALIGN(4K) {
        __bss_start = .;
        *(.bss .bss.*)
        __bss_end = .;
    } > RAM

    . = ALIGN(16);
    __stack_start = .;
    . += 64K;
    __stack_end = .;

    /DISCARD/ : {
        *(.eh_frame*)
        *(.note*)
        *(.comment)
    }
}
