#!/bin/bash
while ! cargo clippy --workspace --exclude qemu_harness --target-dir /Users/xcallens/.gemini/antigravity/scratch/target -- -D clippy::all -D clippy::pedantic; do
    echo "Running auto_patch_clippy.py..."
    python3 auto_patch_clippy.py
done
echo "All crates passed clippy!"
