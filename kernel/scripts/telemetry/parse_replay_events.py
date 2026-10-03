#!/usr/bin/env python3
"""Parses real strace -f -tt -i captures (see
docs/roadmap/ml_workload_traces/capture_traces.sh) into a compact,
structured events CSV that examples/firewall_replay can replay through
the real ebpf_firewall/ai_detector code. Every field extracted is real:
pid, syscall name/number, instruction pointer, and mmap/mprotect PROT
flags, parsed directly from strace's own text output -- nothing here
is synthesized.

Syscall numbers are looked up against this machine's own
/usr/include/x86_64-linux-gnu/asm/unistd_64.h (the authoritative x86_64
ABI, not a hand-maintained table that could drift from reality).

Usage: parse_replay_events.py TRACES_DIR --workloads name:subdir [...] --runs N --out events.csv
"""
import argparse
import csv
import re
from pathlib import Path

LINE_RE = re.compile(
    r"^(\d+)\s+[\d:.]+\s+\[([0-9a-f]+)\]\s+([a-zA-Z_][a-zA-Z0-9_]*)\((.*)\)\s*="
)
PROT_BITS = {"PROT_NONE": 0x0, "PROT_READ": 0x1, "PROT_WRITE": 0x2, "PROT_EXEC": 0x4}


def load_syscall_table(path: str = "/usr/include/x86_64-linux-gnu/asm/unistd_64.h") -> dict:
    table = {}
    for m in re.finditer(r"#define __NR_([a-z0-9_]+) (\d+)", open(path).read()):
        table[m.group(1)] = int(m.group(2))
    if not table:
        raise SystemExit(f"No syscalls parsed from {path} -- is this an x86_64 Linux machine?")
    return table


def parse_prot(args: str) -> int:
    m = re.search(r"PROT_[A-Z_|]+", args)
    if not m:
        return 0
    val = 0
    for tok in m.group(0).split("|"):
        val |= PROT_BITS.get(tok, 0)
    return val


def parse_trace(path: Path, syscall_table: dict):
    events = []
    with open(path, errors="replace") as f:
        for line in f:
            m = LINE_RE.match(line)
            if not m:
                continue  # signal-delivery lines, exec/exit notices, etc. -- not syscalls
            pid, ip_hex, name, args = m.groups()
            if name not in syscall_table:
                continue
            prot = parse_prot(args) if name in ("mmap", "mprotect") else 0
            events.append((int(pid), int(ip_hex, 16), name, syscall_table[name], prot))
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("traces_dir", type=Path)
    ap.add_argument("--workloads", nargs="+", required=True, help="name:subdir pairs")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    syscall_table = load_syscall_table()
    out_rows = []
    for spec in args.workloads:
        name, subdir = spec.split(":")
        for run in range(1, args.runs + 1):
            trace_path = args.traces_dir / subdir / f"trace_{run}.log"
            events = parse_trace(trace_path, syscall_table)
            for seq, (pid, ip, syscall, nr, prot) in enumerate(events):
                out_rows.append([name, run, seq, pid, syscall, nr, format(ip, "x"), prot])
            print(f"{name} run {run}: {len(events)} real syscall events parsed")

    with open(args.out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["workload", "run", "seq", "pid", "syscall", "syscall_nr", "ip_hex", "prot"])
        writer.writerows(out_rows)
    print(f"\nWrote {len(out_rows)} total events to {args.out}")


if __name__ == "__main__":
    main()
