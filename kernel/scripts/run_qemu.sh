#!/bin/bash
# Developer utility script to build the 32-bit Multiboot 1 kernel
# and run it interactively in QEMU system emulation.

set -e

echo "=== Building 32-bit Multiboot 1 Kernel ==="
CARGO_TARGET_DIR=/Users/xcallens/.gemini/antigravity-ide/scratch/target \
  cargo build --manifest-path examples/demo_kernel/Cargo.toml --target i686-unknown-linux-gnu

echo "=== Booting Kernel in QEMU System Emulation ==="
echo "Press Ctrl+C to exit QEMU."
qemu-system-i386 -kernel /Users/xcallens/.gemini/antigravity-ide/scratch/target/i686-unknown-linux-gnu/debug/demo_kernel -serial stdio
