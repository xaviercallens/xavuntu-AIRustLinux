#!/usr/bin/env python3
"""RunuX v12 truth-and-metrics gate.

Computes the metrics defined in docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md
section 2, from static analysis only (no cargo/lake invocation required —
see rust_tools.py / lean_tools.py for why). Two subcommands:

  metrics.py measure   [--out FILE] [--md FILE]
      Computes current metrics, writes JSON (and optionally a markdown
      table), prints a summary to stdout.

  metrics.py ratchet --baseline FILE [--current FILE]
      Compares current metrics against a baseline snapshot. Fails (exit 1)
      if any metric moved in the wrong direction. Never updates the
      baseline itself -- that is a separate, reviewed commit, to keep the
      floor from silently sliding (see plan section 4.2 "anti-cheat").

  metrics.py snapshot-baseline --out FILE
      Writes the current measurement as a new baseline. Meant to be run
      deliberately by a human/T3 reviewer, never by CI.

Exit codes: 0 = pass / wrote output. 1 = ratchet regression or bad usage.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lean_tools import analyze_tree as lean_analyze_tree  # noqa: E402
from rust_tools import analyze_workspace  # noqa: E402

# metric_name -> "lower_is_better" | "higher_is_better" | "info"
DIRECTIONS: dict[str, str] = {
    "lean.sorry": "lower_is_better",
    "lean.axiom": "lower_is_better",
    "lean.theorem": "info",
    "lean.files": "info",
    "lean.extracted_thm": "higher_is_better",
    "rust.crates": "info",
    "rust.loc": "info",
    "rust.blanket_clippy_allow_crates": "lower_is_better",
    "rust.lax_allow_crates": "lower_is_better",
    "rust.unsafe_blocks": "info",
    "rust.unsafe_fns": "info",
    "rust.safety_comments": "info",
    "rust.safety_ratio": "higher_is_better",
    "rust.static_mut": "lower_is_better",
    "rust.stub_marker_lines": "lower_is_better",
    "rust.stub_marker_crates": "lower_is_better",
    "rust.const_stub_fns": "lower_is_better",
    "rust.placeholder_crates": "lower_is_better",
    "test.count": "higher_is_better",
    "test.crates": "higher_is_better",
    "fuzz.targets": "higher_is_better",
    "git.commit": "info",
}


def git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def measure() -> dict:
    lean_stats = lean_analyze_tree(REPO_ROOT / "specs" / "lean4")
    rust_stats = analyze_workspace(REPO_ROOT / "crates")
    fuzz_dir = REPO_ROOT / "fuzz" / "fuzz_targets"
    fuzz_targets = len(list(fuzz_dir.glob("*.rs"))) if fuzz_dir.is_dir() else 0

    lean_sorry = sum(s.sorry for s in lean_stats)
    lean_axiom = sum(len(s.axioms) for s in lean_stats)
    lean_theorem = sum(len(s.theorems) for s in lean_stats)

    unsafe_blocks = sum(s.unsafe_blocks for s in rust_stats)
    safety_comments = sum(s.safety_comments for s in rust_stats)
    safety_ratio = round(safety_comments / unsafe_blocks, 4) if unsafe_blocks else 1.0

    metrics = {
        "lean.sorry": lean_sorry,
        "lean.axiom": lean_axiom,
        "lean.theorem": lean_theorem,
        "lean.files": len(lean_stats),
        "lean.extracted_thm": 0,  # WS4: populated once Aeneas/hax extraction lands
        "rust.crates": len(rust_stats),
        "rust.loc": sum(s.loc for s in rust_stats),
        "rust.blanket_clippy_allow_crates": sum(1 for s in rust_stats if s.blanket_clippy_allow),
        "rust.lax_allow_crates": sum(1 for s in rust_stats if s.lax_allow),
        "rust.unsafe_blocks": unsafe_blocks,
        "rust.unsafe_fns": sum(s.unsafe_fns for s in rust_stats),
        "rust.safety_comments": safety_comments,
        "rust.safety_ratio": safety_ratio,
        "rust.static_mut": sum(s.static_mut for s in rust_stats),
        "rust.stub_marker_lines": sum(s.stub_marker_lines for s in rust_stats),
        "rust.stub_marker_crates": sum(1 for s in rust_stats if s.stub_marker_lines > 0),
        "rust.const_stub_fns": sum(s.const_stub_fns for s in rust_stats),
        "rust.placeholder_crates": sum(1 for s in rust_stats if s.loc <= 25),
        "test.count": sum(s.tests for s in rust_stats),
        "test.crates": sum(1 for s in rust_stats if s.tests > 0),
        "fuzz.targets": fuzz_targets,
        "git.commit": git_head(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return metrics


def write_markdown(metrics: dict, path: Path) -> None:
    lines = [
        "# RunuX Metrics Snapshot",
        "",
        f"Commit: `{metrics['git.commit']}`  ",
        f"Generated: {metrics['generated_at']}",
        "",
        "| Metric | Value | Direction |",
        "|---|---:|---|",
    ]
    for key in DIRECTIONS:
        if key == "git.commit":
            continue
        value = metrics.get(key, "n/a")
        lines.append(f"| `{key}` | {value} | {DIRECTIONS[key]} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_measure(args: argparse.Namespace) -> int:
    metrics = measure()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.md:
        write_markdown(metrics, Path(args.md))
    print(f"wrote {out_path}")
    for k in ("lean.sorry", "lean.axiom", "rust.placeholder_crates", "rust.const_stub_fns",
              "rust.safety_ratio", "test.count"):
        print(f"  {k} = {metrics[k]}")
    return 0


def cmd_snapshot_baseline(args: argparse.Namespace) -> int:
    metrics = measure()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"baseline written to {out_path} at commit {metrics['git.commit']}")
    return 0


def cmd_ratchet(args: argparse.Namespace) -> int:
    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        print(f"ERROR: baseline file not found: {baseline_path}", file=sys.stderr)
        return 1
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    if args.current:
        current = json.loads(Path(args.current).read_text(encoding="utf-8"))
    else:
        current = measure()

    regressions = []
    improvements = []
    for key, direction in DIRECTIONS.items():
        if direction == "info" or key not in baseline:
            continue
        base_val = baseline[key]
        cur_val = current.get(key)
        if not isinstance(base_val, (int, float)) or not isinstance(cur_val, (int, float)):
            continue
        if direction == "lower_is_better" and cur_val > base_val:
            regressions.append((key, base_val, cur_val))
        elif direction == "higher_is_better" and cur_val < base_val:
            regressions.append((key, base_val, cur_val))
        elif direction == "lower_is_better" and cur_val < base_val:
            improvements.append((key, base_val, cur_val))
        elif direction == "higher_is_better" and cur_val > base_val:
            improvements.append((key, base_val, cur_val))

    print(f"Baseline commit: {baseline.get('git.commit', '?')}")
    print(f"Current commit:  {current.get('git.commit', '?')}")
    print()
    if improvements:
        print("Improvements:")
        for key, base_val, cur_val in improvements:
            print(f"  {key}: {base_val} -> {cur_val}")
        print()
    if regressions:
        print("REGRESSIONS (metric moved the wrong way):", file=sys.stderr)
        for key, base_val, cur_val in regressions:
            print(f"  {key}: {base_val} -> {cur_val}", file=sys.stderr)
        print()
        print(
            "A metric got worse relative to the baseline. If this is an "
            "intentional, reviewed trade-off, update the baseline in a "
            "separate, human-reviewed commit via "
            "`scripts/metrics.py snapshot-baseline` -- do not silently "
            "work around this check.",
            file=sys.stderr,
        )
        return 1
    print("No regressions. Ratchet holds.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_measure = sub.add_parser("measure", help="compute current metrics and write JSON/markdown")
    p_measure.add_argument("--out", default="docs/roadmap/metrics/metrics.json")
    p_measure.add_argument("--md", default="docs/roadmap/metrics/metrics.md")
    p_measure.set_defaults(func=cmd_measure)

    p_baseline = sub.add_parser("snapshot-baseline", help="write current metrics as the new baseline (human-run only)")
    p_baseline.add_argument("--out", default="docs/roadmap/metrics/metrics.baseline.json")
    p_baseline.set_defaults(func=cmd_snapshot_baseline)

    p_ratchet = sub.add_parser("ratchet", help="compare current metrics against baseline; nonzero exit on regression")
    p_ratchet.add_argument("--baseline", default="docs/roadmap/metrics/metrics.baseline.json")
    p_ratchet.add_argument("--current", default=None, help="path to a precomputed metrics.json; if omitted, measures live")
    p_ratchet.set_defaults(func=cmd_ratchet)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
