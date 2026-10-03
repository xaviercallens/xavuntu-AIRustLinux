#!/usr/bin/env bash
# Builds examples/aarch64_qemu_harness and boots it directly under QEMU's
# virt machine (no firmware/bootloader needed -- QEMU's -kernel loader
# for aarch64 loads a raw ELF and starts it directly, unlike x86_64's
# multiboot loader).
#
# This is a real boot: the CPU starts execution at whatever exception
# level QEMU's virt machine puts it in (EL2 on TCG with no secure
# firmware); our entry code defensively handles EL3/EL2/EL1 and drops
# to EL1 before ever touching Rust. Once there it clears BSS, sets up a
# stack, and calls kmain, which exercises real workspace code
# (kernel_types::SafePageFrame, both the valid-pointer and
# null-rejection paths) over a real PL011 UART, then shuts QEMU down
# cleanly via PSCI SYSTEM_OFF (exit code 0).
#
# Usage: scripts/aarch64_boot_test.sh [--timeout SECONDS]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMEOUT=10
if [ "${1:-}" = "--timeout" ]; then TIMEOUT="$2"; fi
TARGET_DIR="${CARGO_TARGET_DIR:-/tmp/runux_aarch64_boot_target}"
KERNEL="$TARGET_DIR/aarch64-unknown-none/release/aarch64_qemu_harness"
LOG="$(mktemp)"

if ! command -v qemu-system-aarch64 >/dev/null 2>&1; then
    echo "ERROR: qemu-system-aarch64 not found on PATH." >&2
    echo "  Debian/Ubuntu: sudo apt-get install qemu-system-arm" >&2
    echo "  macOS:         brew install qemu" >&2
    exit 1
fi

echo "[1/2] Building examples/aarch64_qemu_harness (release, aarch64-unknown-none)..."
(cd "$REPO_ROOT" && CARGO_TARGET_DIR="$TARGET_DIR" cargo build --release \
    --target aarch64-unknown-none -p aarch64_qemu_harness)

echo "[2/2] Booting under QEMU (virt -> EL1 -> RunuX), timeout ${TIMEOUT}s..."
set +e
timeout "$TIMEOUT" qemu-system-aarch64 \
    -machine virt -cpu cortex-a72 -nographic -nic none \
    -kernel "$KERNEL" > "$LOG" 2>&1
EXIT_CODE=$?
set -e

cat "$LOG"

FAIL=0
for needle in \
    "Booting RunuX AArch64 QEMU Harness" \
    "RunuX: AArch64 arch init" \
    "RunuX: GIC interrupt controller initialized" \
    "RunuX: AArch64 page tables initialized" \
    "SafePageFrame::new(valid_ptr) -> Some" \
    "SafePageFrame::new(null) -> None" \
    "RunuX AArch64 booted successfully inside QEMU"
do
    if ! grep -qF "$needle" "$LOG"; then
        echo "MISSING banner line: $needle" >&2
        FAIL=1
    fi
done

if [ "$EXIT_CODE" -ne 0 ]; then
    echo "FAIL: QEMU exited $EXIT_CODE (expected 0 -- clean PSCI SYSTEM_OFF)" >&2
    FAIL=1
fi

rm -f "$LOG"

if [ "$FAIL" -ne 0 ]; then
    echo "FAIL: AArch64 boot test did not pass" >&2
    exit 1
fi

echo "PASS: RunuX boots under qemu-system-aarch64 virt (exit 0, full banner sequence, real kernel_types logic exercised)"
