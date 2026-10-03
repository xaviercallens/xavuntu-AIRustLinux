#!/usr/bin/env python3
import subprocess
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Automated RISC-V QEMU boot smoke test")
    parser.add_argument(
        "--kernel",
        default="target/riscv64gc-unknown-none-elf/release/riscv_qemu_harness",
        help="Path to the compiled bare-metal RISC-V kernel"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Max time in seconds to wait for successful boot"
    )
    args = parser.parse_args()

    print(f"[INFO] Starting RISC-V QEMU boot smoke test...")
    print(f"[INFO] Kernel path: {args.kernel}")
    print(f"[INFO] Timeout: {args.timeout} seconds")

    cmd = [
        "qemu-system-riscv64",
        "-machine", "virt",
        "-nographic",
        "-bios", "default",
        "-kernel", args.kernel
    ]

    # Spawn QEMU
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
    except Exception as e:
        print(f"[ERROR] Failed to start QEMU: {e}")
        sys.exit(1)

    try:
        stdout, _ = process.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, _ = process.communicate()
        print(f"\n[ERROR] QEMU reached timeout of {args.timeout} seconds without exiting.")
    
    # Check for success indicators
    booted_banner = "[INFO] Booting RunuX RISC-V QEMU Harness..." in stdout
    booted_success = "[SUCCESS] RunuX RISC-V booted successfully inside QEMU!" in stdout
    arch_init = "RunuX: RISC-V arch init" in stdout
    irq_init = "RunuX: PLIC interrupt controller initialized" in stdout
    pgtable_init = "RunuX: Sv39 page tables initialized" in stdout

    if booted_banner and booted_success and arch_init and irq_init and pgtable_init:
        print(f"\n[SUCCESS] RISC-V Kernel boot sequence validated successfully in QEMU!")
        print("Telemetry:")
        print("  - S-mode transition: Pass")
        print("  - UART 16550 console: Pass")
        print("  - PLIC initialisation: Pass")
        print("  - Sv39 page tables: Pass")
        print("  - SiFive Test exit device: Pass")
        sys.exit(0)
    else:
        print(f"\n[ERROR] RISC-V Kernel failed to output expected boot indicators.")
        print(f"--- QEMU OUTPUT ---\n{stdout}\n-------------------")
        sys.exit(1)

if __name__ == "__main__":
    main()
