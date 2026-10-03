#!/usr/bin/env bash
# Builds examples/riscv_qemu_harness and boots it under QEMU with OpenSBI.
# This is a real boot: OpenSBI (M-mode firmware) loads the kernel at
# 0x80200000, hands off to S-mode, our _start runs, and RunuX code
# (runux_riscv64::riscv_arch_init/irq_init/pgtable_init) executes and prints
# over a real 16550 UART. Exit code and the expected banner sequence are
# checked; QEMU shutdown is triggered by the kernel itself via the SiFive
# test-finisher device (write 0x5555 = success, 0x3333 = panic).
#
# Usage: scripts/riscv_boot_test.sh [--timeout SECONDS]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMEOUT=10
if [ "${1:-}" = "--timeout" ]; then TIMEOUT="$2"; fi
TARGET_DIR="${CARGO_TARGET_DIR:-/tmp/runux_riscv_boot_target}"
KERNEL="$TARGET_DIR/riscv64gc-unknown-none-elf/release/riscv_qemu_harness"
LOG="$(mktemp)"

if ! command -v qemu-system-riscv64 >/dev/null 2>&1; then
    echo "ERROR: qemu-system-riscv64 not found on PATH." >&2
    echo "  Debian/Ubuntu: sudo apt-get install qemu-system-misc" >&2
    echo "  macOS:         brew install qemu" >&2
    exit 1
fi

echo "[1/2] Building examples/riscv_qemu_harness (release, riscv64gc-unknown-none-elf)..."
(cd "$REPO_ROOT" && CARGO_TARGET_DIR="$TARGET_DIR" cargo build --release \
    --target riscv64gc-unknown-none-elf -p riscv_qemu_harness)

echo "[2/2] Booting under QEMU (OpenSBI -> S-mode -> RunuX), timeout ${TIMEOUT}s..."
set +e
timeout "$TIMEOUT" qemu-system-riscv64 \
    -machine virt -nographic -bios default \
    -kernel "$KERNEL" > "$LOG" 2>&1
EXIT_CODE=$?
set -e

cat "$LOG"

FAIL=0
for needle in \
    "Booting RunuX RISC-V QEMU Harness" \
    "RunuX: RISC-V arch init" \
    "RunuX: PLIC interrupt controller initialized" \
    "RunuX: Sv39 page tables initialized" \
    "RunuX RISC-V booted successfully inside QEMU"
do
    if ! grep -qF "$needle" "$LOG"; then
        echo "MISSING banner line: $needle" >&2
        FAIL=1
    fi
done

if [ "$EXIT_CODE" -ne 0 ]; then
    echo "FAIL: QEMU exited $EXIT_CODE (expected 0 -- the SiFive test-finisher success code)" >&2
    FAIL=1
fi

rm -f "$LOG"

if [ "$FAIL" -ne 0 ]; then
    echo "FAIL: RISC-V boot test did not pass" >&2
    exit 1
fi

echo "PASS: RunuX boots under QEMU riscv64 virt via OpenSBI (exit 0, full banner sequence)"
