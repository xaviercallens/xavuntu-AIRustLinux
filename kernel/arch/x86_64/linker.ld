OUTPUT_FORMAT(elf64-x86-64)
OUTPUT_ARCH(i386:x86-64)
ENTRY(_start)
KERNEL_BASE = 0x100000;

SECTIONS
{
    . = KERNEL_BASE;
    .text ALIGN(4K) : {
        KEEP(*(.multiboot))
        *(.text .text.*)
    }
    .rodata ALIGN(4K) : { *(.rodata .rodata.*) }
    .data ALIGN(4K) : { *(.data .data.*) }
    .bss ALIGN(4K) : {
        __bss_start = .;
        *(.bss .bss.*)
        *(COMMON)
        __bss_end = .;
    }
    /DISCARD/ : {
        *(.comment)
        *(.eh_frame)
        *(.note.*)
    }
    . = ALIGN(4K);
    __kernel_end = .;
}
