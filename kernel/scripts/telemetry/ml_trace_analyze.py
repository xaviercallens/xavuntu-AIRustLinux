#!/usr/bin/env python3
"""Analyzes syscall traces captured by capture_traces.sh (see
docs/roadmap/ml_workload_traces/) into summary CSVs: total/unique
syscall counts per run, the "stable" syscall set present in every run
of a workload, and per-syscall frequency. Never publishes raw traces
(they can be large and may contain local file paths) -- only these
aggregate summaries are meant to be committed.

Usage: ml_trace_analyze.py TRACES_DIR --workloads name:subdir:timing_csv [...] --out OUT_DIR

Example (matches the layout capture_traces.sh produces):
  ml_trace_analyze.py ~/ml_traces \
    --workloads device_enum:device_enum:device_enum_timing.csv \
                matmul_512x512:matmul:matmul_timing.csv \
    --out docs/roadmap/ml_workload_traces
"""
import argparse
import csv
import re
import statistics
from collections import Counter
from pathlib import Path

SYSCALL_RE = re.compile(r"^\d+\s+[\d:.]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\(")


def find_run_count(trace_dir: Path) -> int:
    return len(list(trace_dir.glob("trace_*.log")))


def analyze_workload(name: str, trace_dir: Path, timing_csv: Path):
    n = find_run_count(trace_dir)
    if n == 0:
        raise SystemExit(f"No trace_*.log files found in {trace_dir}")

    per_run_counts = []
    global_syscall_counter = Counter()
    for i in range(1, n + 1):
        path = trace_dir / f"trace_{i}.log"
        counter = Counter()
        with open(path, errors="replace") as f:
            for line in f:
                m = SYSCALL_RE.match(line)
                if m:
                    counter[m.group(1)] += 1
        per_run_counts.append(counter)
        global_syscall_counter.update(counter)

    totals = [sum(c.values()) for c in per_run_counts]
    unique_per_run = [len(c) for c in per_run_counts]

    stable_syscalls = set(per_run_counts[0].keys())
    for c in per_run_counts[1:]:
        stable_syscalls &= set(c.keys())
    all_seen = set(global_syscall_counter.keys())
    variable_syscalls = all_seen - stable_syscalls

    timings = []
    with open(timing_csv) as f:
        for row in csv.DictReader(f):
            timings.append(float(row["wall_seconds"]))

    print(f"=== {name} (n={n}) ===")
    print(f"Total syscalls per run: mean={statistics.mean(totals):.0f} stdev={statistics.stdev(totals):.0f} min={min(totals)} max={max(totals)}")
    print(f"Unique syscall names per run: mean={statistics.mean(unique_per_run):.1f} min={min(unique_per_run)} max={max(unique_per_run)}")
    print(f"Wall time: mean={statistics.mean(timings):.3f}s stdev={statistics.stdev(timings):.3f}s min={min(timings):.3f}s max={max(timings):.3f}s")
    print(f"Stable syscall set (present in all {n} runs): {len(stable_syscalls)}")
    print(f"Variable syscalls (present in some but not all runs): {sorted(variable_syscalls) if variable_syscalls else 'none'}")
    print()

    summary = {
        "workload": name,
        "n": n,
        "mean_syscalls": statistics.mean(totals),
        "stdev_syscalls": statistics.stdev(totals),
        "min_syscalls": min(totals),
        "max_syscalls": max(totals),
        "mean_unique_syscalls": statistics.mean(unique_per_run),
        "stable_syscall_count": len(stable_syscalls),
        "variable_syscall_count": len(variable_syscalls),
        "mean_wall_seconds": statistics.mean(timings),
        "stdev_wall_seconds": statistics.stdev(timings),
    }
    return summary, stable_syscalls, global_syscall_counter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("traces_dir", type=Path)
    ap.add_argument("--workloads", nargs="+", required=True, help="name:subdir:timing_csv triples")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    results = []
    for spec in args.workloads:
        name, subdir, timing_csv = spec.split(":")
        r, stable, counter = analyze_workload(name, args.traces_dir / subdir, args.traces_dir / timing_csv)
        results.append((r, stable, counter))

    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "workload_summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0][0].keys()))
        writer.writeheader()
        for r, _, _ in results:
            writer.writerow(r)

    with open(args.out / "syscall_frequency.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["workload", "syscall", "total_count_across_runs", "in_every_run"])
        for r, stable, counter in results:
            for name_, count in sorted(counter.items(), key=lambda x: -x[1]):
                writer.writerow([r["workload"], name_, count, name_ in stable])

    print(f"Wrote {args.out / 'workload_summary.csv'} and {args.out / 'syscall_frequency.csv'}")


if __name__ == "__main__":
    main()
