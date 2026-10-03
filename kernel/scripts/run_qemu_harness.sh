#!/bin/bash
set -e

CARGO_TARGET_DIR=/Users/xcallens/.gemini/antigravity/scratch/target \
  cargo build --manifest-path examples/qemu_harness/Cargo.toml --target i686-unknown-linux-gnu

echo "[INFO] Running QEMU Harness..."
qemu-system-i386 \
  -kernel /Users/xcallens/.gemini/antigravity/scratch/target/i686-unknown-linux-gnu/debug/qemu_harness \
  -display none \
  -serial stdio \
  -device isa-debug-exit,iobase=0xf4,iosize=0x04 || exit_code=$?

if [ "$exit_code" -eq 1 ]; then
    echo "[SUCCESS] QEMU Harness passed."
    exit 0
else
    echo "[ERROR] QEMU Harness failed or panicked."
    exit 1
fi
