#!/usr/bin/env bash
# Runs on a target VM: captures pre-run state (dmesg, sysfs snapshot),
# runs pci_probe_userspace in read-only mode N times, captures post-run
# state, and packages everything into one tarball for offline analysis
# by scripts/telemetry/pci_diff.py.
#
# This never disturbs the running system: no BAR sizing, no writes of
# any kind to hardware beyond what pci_enumerate's read-only config
# reads perform.
#
# Usage: pci_topology_run.sh --binary PATH [--iterations N] [--out PATH]
set -euo pipefail

BINARY=""
ITERATIONS=30
OUT="pci_topology_$(hostname)_$(date -u +%Y%m%dT%H%M%SZ).tar.gz"

while [ $# -gt 0 ]; do
    case "$1" in
        --binary) BINARY="$2"; shift 2 ;;
        --iterations) ITERATIONS="$2"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

if [ -z "$BINARY" ] || [ ! -x "$BINARY" ]; then
    echo "ERROR: --binary must point to an executable pci_probe_userspace" >&2
    exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: must run as root (needed for iopl(3) and full sysfs/dmesg access)" >&2
    exit 1
fi

WORK="$(mktemp -d)"
mkdir -p "$WORK/runs" "$WORK/sysfs"

echo "[1/4] Capturing pre-run state..."
dmesg > "$WORK/dmesg_pre.log" 2>&1 || true
for dev in /sys/bus/pci/devices/*/; do
    bdf="$(basename "$dev")"
    mkdir -p "$WORK/sysfs/$bdf"
    for f in vendor device class subsystem_vendor subsystem_device revision; do
        [ -r "${dev}${f}" ] && cp "${dev}${f}" "$WORK/sysfs/$bdf/$f" 2>/dev/null || true
    done
    [ -r "${dev}config" ] && cp "${dev}config" "$WORK/sysfs/$bdf/config" 2>/dev/null || true
    [ -L "${dev}driver" ] && basename "$(readlink -f "${dev}driver")" > "$WORK/sysfs/$bdf/driver_name" 2>/dev/null || true
    [ -r "${dev}numa_node" ] && cp "${dev}numa_node" "$WORK/sysfs/$bdf/numa_node" 2>/dev/null || true
    for bar in resource; do
        [ -r "${dev}${bar}" ] && cp "${dev}${bar}" "$WORK/sysfs/$bdf/resource" 2>/dev/null || true
    done
done
uname -a > "$WORK/uname.txt"
lscpu > "$WORK/lscpu.txt" 2>&1 || true

echo "[2/4] Running $BINARY $ITERATIONS times (read-only, --json --dump-config)..."
for i in $(seq 1 "$ITERATIONS"); do
    "$BINARY" --json --dump-config > "$WORK/runs/run_$i.json" 2> "$WORK/runs/run_$i.stderr" || \
        echo "run $i exited non-zero" >> "$WORK/runs_errors.log"
done

echo "[3/4] Capturing post-run state..."
dmesg > "$WORK/dmesg_post.log" 2>&1 || true

echo "[4/4] Packaging $OUT..."
tar -C "$WORK" -czf "$OUT" .
rm -rf "$WORK"
echo "Wrote $OUT"
