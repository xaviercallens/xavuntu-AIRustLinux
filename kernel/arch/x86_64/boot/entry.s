# Rust Linux Mini Kernel - x86_64 Entry Point
# This is called by the bootloader (multiboot2 or direct boot)

.section .text
.global _start
.code64

_start:
    # Disable interrupts
    cli

    # Set up stack (bootloader should have done this, but be safe)
    # Stack grows downward, so set rsp to top of stack area
    movq $stack_top, %rsp

    # Clear frame pointer for clean backtraces
    xorq %rbp, %rbp

    # Align stack to 16 bytes (required by System V ABI)
    andq $-16, %rsp

    # Zero out BSS section
    movq $__bss_start, %rdi
    movq $__bss_end, %rcx
    subq %rdi, %rcx          # Calculate size
    xorb %al, %al            # Zero byte
    rep stosb                # Fill BSS with zeros

    # Call Rust kernel entry point
    # This will never return
    call start_kernel

    # If somehow we return, halt forever
halt_loop:
    cli
    hlt
    jmp halt_loop

# Kernel stack
.section .bss
.align 16
stack_bottom:
    .skip 16384              # 16 KB stack
stack_top:

# BSS symbols (defined by linker script)
.extern __bss_start
.extern __bss_end

# x86 Port I/O functions for Rust
# These are used by printk for serial output

.global x86_out8
.global x86_in8

# void x86_out8(u16 port, u8 value)
# rdi = port, rsi = value
x86_out8:
    movw %di, %dx            # port to dx
    movb %sil, %al           # value to al
    outb %al, %dx            # output byte
    ret

# u8 x86_in8(u16 port)
# rdi = port, returns value in al
x86_in8:
    movw %di, %dx            # port to dx
    inb %dx, %al             # input byte to al
    ret
