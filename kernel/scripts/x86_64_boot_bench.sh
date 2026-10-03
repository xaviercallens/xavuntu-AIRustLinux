#!/usr/bin/env bash
# Telemetry harness for the x86_64 long-mode boot path: builds
# examples/x86_64_qemu_harness and its GRUB Multiboot2 ISO once, then
# boots it under QEMU N times (default 30, per AGENTS.md's "n >= 30 with
# a stated confidence interval" evidence rule), timing wall-clock
# seconds from QEMU launch to its own clean exit (via isa-debug-exit)
# and checking the same banner sequence as scripts/x86_64_boot_test.sh
# on every run. Writes a per-run CSV and a mean/stddev/95% CI summary.
#
# This measures *this harness's* boot latency only -- see
# docs/roadmap/RISCV_BOOT_TELEMETRY.md for why no Linux comparison is
# made; the same reasoning applies here (no scheduler, drivers,
# filesystem, or userspace).
#
# Usage: scripts/x86_64_boot_bench.sh [--runs N] [--timeout SECONDS] [--csv PATH]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS=30
TIMEOUT=15
CSV="/tmp/runux_x86_64_boot_bench.csv"

while [ $# -gt 0 ]; do
    case "$1" in
        --runs) RUNS="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --csv) CSV="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

TARGET_DIR="${CARGO_TARGET_DIR:-/tmp/runux_x86_64_boot_target}"
KERNEL="$TARGET_DIR/x86_64-unknown-linux-gnu/release/x86_64_qemu_harness"
ISO_ROOT="$(mktemp -d)"
ISO_PATH="$(mktemp --suffix=.iso)"

for tool in qemu-system-x86_64 grub-mkrescue; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "ERROR: $tool not found on PATH." >&2
        exit 1
    fi
done

echo "[1/2] Building examples/x86_64_qemu_harness and its GRUB ISO..."
(cd "$REPO_ROOT/examples/x86_64_qemu_harness" && CARGO_TARGET_DIR="$TARGET_DIR" cargo build --release)
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

echo "[2/2] Booting under QEMU $RUNS times (timeout ${TIMEOUT}s each)..."
echo "run,duration_seconds,exit_code,pass" > "$CSV"

PASS_COUNT=0
for i in $(seq 1 "$RUNS"); do
    LOG="$(mktemp)"
    START="$(date +%s.%N)"
    set +e
    timeout "$TIMEOUT" qemu-system-x86_64 \
        -cdrom "$ISO_PATH" -nographic -vga none -nic none \
        -device isa-debug-exit,iobase=0xf4,iosize=0x04 -no-reboot \
        > "$LOG" 2>&1
    EXIT_CODE=$?
    set -e
    END="$(date +%s.%N)"
    DURATION="$(echo "$END - $START" | bc)"

    RUN_PASS=1
    for needle in \
        "Booting RunuX x86_64 QEMU Harness" \
        "PAE + EFER.LME + CR0.PG enabled" \
        "SafePageFrame::new(valid_ptr) -> Some" \
        "SafePageFrame::new(null) -> None" \
        "RunuX x86_64 booted successfully inside QEMU"
    do
        grep -qF "$needle" "$LOG" || RUN_PASS=0
    done
    [ "$EXIT_CODE" -ne 1 ] && RUN_PASS=0

    if [ "$RUN_PASS" -eq 1 ]; then
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "  run $i FAILED (exit=$EXIT_CODE) -- log follows:" >&2
        cat "$LOG" >&2
    fi
    printf '%d,%s,%d,%d\n' "$i" "$DURATION" "$EXIT_CODE" "$RUN_PASS" >> "$CSV"
    rm -f "$LOG"
    echo "  run $i/$RUNS: ${DURATION}s, exit=$EXIT_CODE, pass=$RUN_PASS"
done

rm -f "$ISO_PATH"
rm -rf "$ISO_ROOT"

echo
echo "Results CSV: $CSV"
echo "Pass rate: $PASS_COUNT/$RUNS"

python3 - "$CSV" "$RUNS" "$PASS_COUNT" <<'PYEOF'
import csv
import math
import sys

csv_path, runs, pass_count = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
durations = []
with open(csv_path, newline="") as f:
    for row in csv.DictReader(f):
        if row["pass"] == "1":
            durations.append(float(row["duration_seconds"]))

if not durations:
    print("No passing runs; cannot compute timing statistics.")
    sys.exit(1)

n = len(durations)
mean = sum(durations) / n
variance = sum((x - mean) ** 2 for x in durations) / (n - 1) if n > 1 else 0.0
stddev = math.sqrt(variance)
margin = 1.96 * stddev / math.sqrt(n) if n > 1 else 0.0

print(f"Passing runs used for timing stats: n={n}")
print(f"Mean boot time: {mean:.4f}s")
print(f"Stddev: {stddev:.4f}s")
print(f"95% CI: [{mean - margin:.4f}s, {mean + margin:.4f}s]")
print(f"Min: {min(durations):.4f}s  Max: {max(durations):.4f}s")

if pass_count != runs:
    print(f"NOTE: {runs - pass_count} of {runs} runs failed -- see stderr output above for logs.")
PYEOF
