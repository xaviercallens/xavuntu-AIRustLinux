#!/usr/bin/env python3
import subprocess
import sys
import time
import argparse

def main():
    parser = argparse.ArgumentParser(description="Automated QEMU boot smoke test")
    parser.add_argument(
        "--kernel",
        default="examples/demo_kernel/target/i686-unknown-linux-gnu/release/demo_kernel",
        help="Path to the compiled bare-metal kernel ELF"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Max time in seconds to wait for successful boot"
    )
    args = parser.parse_args()

    print(f"[INFO] Starting QEMU boot smoke test...")
    print(f"[INFO] Kernel path: {args.kernel}")
    print(f"[INFO] Timeout: {args.timeout} seconds")

    cmd = [
        "qemu-system-i386",
        "-kernel", args.kernel,
        "-display", "none",
        "-serial", "stdio"
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
        print(f"\n[INFO] QEMU reached timeout of {args.timeout} seconds (expected).")
    
    # Check for success indicators
    booted_banner = "RUST LINUX MINI KERNEL - DEMO" in stdout
    booted_modules = "Loaded Modules:" in stdout or "[OK] kernel_types" in stdout

    if booted_banner and booted_modules:
        print(f"\n[SUCCESS] Kernel boot sequence validated successfully!")
        sys.exit(0)
    else:
        print(f"\n[ERROR] Kernel failed to output expected banners.")
        print(f"--- QEMU OUTPUT ---\n{stdout}\n-------------------")
        sys.exit(1)

if __name__ == "__main__":
    main()
