#!/usr/bin/env bash
# Builds examples/x86_64_qemu_harness, packages it into a bootable
# Multiboot2 ISO with GRUB, and boots it under qemu-system-x86_64.
#
# This is a real boot, not the older examples/demo_kernel trick: the CPU
# starts in 32-bit protected mode per the Multiboot spec (GRUB loads an
# ELF64 kernel directly), our hand-written entry code builds identity-
# mapped page tables, enables PAE + EFER.LME + CR0.PG, far-jumps into a
# 64-bit code segment, and only then calls genuine 64-bit Rust that
# exercises a real workspace type (kernel_types::SafePageFrame) before
# shutting QEMU down via the isa-debug-exit device (0x00 = success ->
# exit code 1, 0x11 = panic -> exit code 35).
#
# Requires: qemu-system-x86 (qemu-system-x86_64), grub-pc-bin,
# grub-common, xorriso, mtools.
#
# Usage: scripts/x86_64_boot_test.sh [--timeout SECONDS]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMEOUT=15
if [ "${1:-}" = "--timeout" ]; then TIMEOUT="$2"; fi
TARGET_DIR="${CARGO_TARGET_DIR:-/tmp/runux_x86_64_boot_target}"
KERNEL="$TARGET_DIR/x86_64-unknown-linux-gnu/release/x86_64_qemu_harness"
ISO_ROOT="$(mktemp -d)"
ISO_PATH="$(mktemp --suffix=.iso)"
LOG="$(mktemp)"

for tool in qemu-system-x86_64 grub-mkrescue; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "ERROR: $tool not found on PATH." >&2
        echo "  Debian/Ubuntu: sudo apt-get install qemu-system-x86 grub-pc-bin grub-common xorriso mtools" >&2
        exit 1
    fi
done

echo "[1/3] Building examples/x86_64_qemu_harness (release, x86_64-unknown-linux-gnu)..."
(cd "$REPO_ROOT/examples/x86_64_qemu_harness" && CARGO_TARGET_DIR="$TARGET_DIR" cargo build --release)

echo "[2/3] Building Multiboot2 GRUB ISO..."
mkdir -p "$ISO_ROOT/boot/grub"
cp "$KERNEL" "$ISO_ROOT/boot/x86_64_qemu_harness"
cat > "$ISO_ROOT/boot/grub/grub.cfg" <<'EOF'
set timeout=0
set default=0

menuentry "RunuX x86_64" {
    multiboot2 /boot/x86_64_qemu_harness
    boot
}
EOF
grub-mkrescue -o "$ISO_PATH" "$ISO_ROOT" >/dev/null 2>&1

echo "[3/3] Booting under QEMU (GRUB -> Multiboot2 -> long mode -> RunuX), timeout ${TIMEOUT}s..."
set +e
timeout "$TIMEOUT" qemu-system-x86_64 \
    -cdrom "$ISO_PATH" -nographic -vga none -nic none \
    -device isa-debug-exit,iobase=0xf4,iosize=0x04 -no-reboot \
    > "$LOG" 2>&1
EXIT_CODE=$?
set -e

cat "$LOG"

FAIL=0
for needle in \
    "Booting RunuX x86_64 QEMU Harness" \
    "PAE + EFER.LME + CR0.PG enabled" \
    "SafePageFrame::new(valid_ptr) -> Some" \
    "SafePageFrame::new(null) -> None" \
    "RunuX x86_64 booted successfully inside QEMU"
do
    if ! grep -qF "$needle" "$LOG"; then
        echo "MISSING banner line: $needle" >&2
        FAIL=1
    fi
done

if [ "$EXIT_CODE" -ne 1 ]; then
    echo "FAIL: QEMU exited $EXIT_CODE (expected 1 -- the isa-debug-exit success sentinel)" >&2
    FAIL=1
fi

rm -f "$LOG" "$ISO_PATH"
rm -rf "$ISO_ROOT"

if [ "$FAIL" -ne 0 ]; then
    echo "FAIL: x86_64 boot test did not pass" >&2
    exit 1
fi

echo "PASS: RunuX boots under qemu-system-x86_64 via GRUB Multiboot2 (exit 1, full banner sequence, real kernel_types logic exercised)"
