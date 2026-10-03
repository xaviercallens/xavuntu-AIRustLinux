#!/usr/bin/env bash
# Telemetry harness for the AArch64 boot path: builds
# examples/aarch64_qemu_harness once, then boots it under QEMU N times
# (default 30, per AGENTS.md's "n >= 30 with a stated confidence
# interval" evidence rule), timing wall-clock seconds from QEMU launch
# to its own clean PSCI SYSTEM_OFF exit, checking the same banner
# sequence as scripts/aarch64_boot_test.sh on every run. Writes a
# per-run CSV and a mean/stddev/95% CI summary.
#
# This measures *this harness's* boot latency only -- see
# docs/roadmap/RISCV_BOOT_TELEMETRY.md for why no Linux comparison is
# made; the same reasoning applies here (no scheduler, drivers,
# filesystem, or userspace).
#
# Usage: scripts/aarch64_boot_bench.sh [--runs N] [--timeout SECONDS] [--csv PATH]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS=30
TIMEOUT=10
CSV="/tmp/runux_aarch64_boot_bench.csv"

while [ $# -gt 0 ]; do
    case "$1" in
        --runs) RUNS="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --csv) CSV="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

TARGET_DIR="${CARGO_TARGET_DIR:-/tmp/runux_aarch64_boot_target}"
KERNEL="$TARGET_DIR/aarch64-unknown-none/release/aarch64_qemu_harness"

if ! command -v qemu-system-aarch64 >/dev/null 2>&1; then
    echo "ERROR: qemu-system-aarch64 not found on PATH." >&2
    exit 1
fi

echo "[1/2] Building examples/aarch64_qemu_harness (release, aarch64-unknown-none)..."
(cd "$REPO_ROOT" && CARGO_TARGET_DIR="$TARGET_DIR" cargo build --release \
    --target aarch64-unknown-none -p aarch64_qemu_harness)

echo "[2/2] Booting under QEMU $RUNS times (timeout ${TIMEOUT}s each)..."
echo "run,duration_seconds,exit_code,pass" > "$CSV"

PASS_COUNT=0
for i in $(seq 1 "$RUNS"); do
    LOG="$(mktemp)"
    START="$(date +%s.%N)"
    set +e
    timeout "$TIMEOUT" qemu-system-aarch64 \
        -machine virt -cpu cortex-a72 -nographic -nic none \
        -kernel "$KERNEL" > "$LOG" 2>&1
    EXIT_CODE=$?
    set -e
    END="$(date +%s.%N)"
    DURATION="$(echo "$END - $START" | bc)"

    RUN_PASS=1
    for needle in \
        "Booting RunuX AArch64 QEMU Harness" \
        "RunuX: AArch64 arch init" \
        "RunuX: GIC interrupt controller initialized" \
        "RunuX: AArch64 page tables initialized" \
        "SafePageFrame::new(valid_ptr) -> Some" \
        "SafePageFrame::new(null) -> None" \
        "RunuX AArch64 booted successfully inside QEMU"
    do
        grep -qF "$needle" "$LOG" || RUN_PASS=0
    done
    [ "$EXIT_CODE" -ne 0 ] && RUN_PASS=0

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
