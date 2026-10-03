; Rust Linux Mini Kernel - x86_64 Entry Point
BITS 64
section .text
global _start, x86_out8, x86_in8
extern start_kernel, __bss_start, __bss_end

_start:
    cli
    mov rsp, stack_top
    xor rbp, rbp
    and rsp, -16
    mov rdi, __bss_start
    mov rcx, __bss_end
    sub rcx, rdi
    xor al, al
    rep stosb
    call start_kernel
.halt_loop:
    cli
    hlt
    jmp .halt_loop

x86_out8:
    mov dx, di
    mov al, sil
    out dx, al
    ret

x86_in8:
    mov dx, di
    in al, dx
    ret

section .bss
align 16
stack_bottom:
    resb 16384
stack_top:
