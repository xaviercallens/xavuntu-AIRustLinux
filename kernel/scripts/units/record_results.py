#!/usr/bin/env python3
"""Append a workflow run's per-crate results to docs/roadmap/units_status.csv.

Deterministic replacement for the LLM bookkeeping agent used in the wave-1
Lean pilot (~47k tokens to append a CSV). Input is the JSON the
runux-quickwins workflow returns (its `results` list), saved to a file.

Usage:
    scripts/units/record_results.py RESULT.json [--type harden]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CSV_PATH = REPO_ROOT / "docs" / "roadmap" / "units_status.csv"
FIELDS = ["id", "type", "file", "theorem", "tier", "status", "attempts", "pr_url"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("result_json")
    ap.add_argument("--type", default="harden", help="value for the csv `type` column")
    args = ap.parse_args()

    data = json.loads(Path(args.result_json).read_text())
    results = data.get("result", data).get("results", [])
    if not results:
        sys.exit("no `results` list found in input")

    rows = [{
        "id": f"{args.type}::{r['crate']}",
        "type": args.type,
        "file": f"crates/{r['crate']}",
        "theorem": "",
        "tier": r.get("tier") or "",
        "status": r.get("status") or "",
        "attempts": "",
        "pr_url": r.get("pr_url") or "",
    } for r in results]

    new_file = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerows(rows)
    print(f"appended {len(rows)} rows to {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
