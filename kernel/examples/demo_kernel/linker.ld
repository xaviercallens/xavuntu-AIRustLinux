ENTRY(_start)

SECTIONS {
    . = 1M;

    .boot :
    {
        /* Ensure boot section is first */
        KEEP(*(.multiboot))
    }

    .text :
    {
        *(.text .text.*)
    }

    .rodata :
    {
        *(.rodata .rodata.*)
    }

    .data :
    {
        *(.data .data.*)
    }

    .bss :
    {
        *(.bss .bss.*)
    }
}
