#!/usr/bin/env python3
"""Build results/v2/capability_matrix.json from the real result files (glue, no logic).

Sources, each optional and each recorded as the cell's ``source``:
  results/hardness/baseline.json       (lean, tiers T0-T4, both provers, greedy)
  results/hardness/retrieval_ab.json   (lean, arm k=5 -> model name suffixed '+premises')
  results/phase1_evolution/results.json (coding, tier P1, whichever model that run used)

Usage:  .venv/bin/python scripts/hardness/capability_matrix.py [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from anse.v2.model_router import CapabilityMatrix, record_outcome, summarize  # noqa: E402

BASELINE = REPO / "results/hardness/baseline.json"
RETRIEVAL = REPO / "results/hardness/retrieval_ab.json"
PHASE1 = REPO / "results/phase1_evolution/results.json"
OUT = REPO / "results/v2/capability_matrix.json"
TIERS = ["T0", "T1", "T2", "T3", "T4"]


def fold_ladder_runs(mx: CapabilityMatrix, runs: list[dict], source: str, suffix: str = "") -> tuple[CapabilityMatrix, int]:
    n = 0
    for r in runs:
        if "error" in r and "clean" not in r:
            continue  # transport error, no verdict (run_ladder drops these on resume)
        mx = record_outcome(mx, "lean", r["tier"], r["model"] + suffix,
                            passed=bool(r.get("clean")), truth=r.get("truth"), source=source)
        n += 1
    return mx, n


def fold_phase1(mx: CapabilityMatrix, data: dict, source: str) -> tuple[CapabilityMatrix, int]:
    """Phase 1 use case 2 ("Learning from pain") holds one row per (task, seed) with a
    sandbox-verified ``converged`` flag; the tier is the row's split (P1-train / P1-test)."""
    model = str(data.get("model", "unknown"))
    n = 0
    for rec in (data.get("uc2") or {}).get("rows", []):
        if isinstance(rec, dict) and "converged" in rec:
            tier = f"P1-{rec.get('split', 'all')}"
            mx = record_outcome(mx, "coding", tier, model, passed=bool(rec["converged"]), truth=True, source=source)
            n += 1
    return mx, n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    mx = CapabilityMatrix()
    provenance: dict[str, int | str] = {}
    if BASELINE.exists():
        mx, n = fold_ladder_runs(mx, json.loads(BASELINE.read_text())["runs"], "hardness/baseline.json")
        provenance["hardness/baseline.json"] = n
    if RETRIEVAL.exists():
        data = json.loads(RETRIEVAL.read_text())
        runs = [r for r in data.get("runs", []) if r.get("arm") == "k5"]
        mx, n = fold_ladder_runs(mx, runs, "hardness/retrieval_ab.json", suffix="+premises")
        provenance["hardness/retrieval_ab.json (arm k5)"] = n
    else:
        provenance["hardness/retrieval_ab.json"] = "absent"
    if PHASE1.exists():
        mx, n = fold_phase1(mx, json.loads(PHASE1.read_text()), "phase1_evolution/results.json")
        provenance["phase1_evolution/results.json"] = n

    lean_models = sorted({m for (d, _t, m) in mx.cells if d == "lean"})
    report = {
        "built_from": provenance,
        "cells": mx.to_dict(),
        "lean_routing_summary": summarize(mx, "lean", TIERS, lean_models) if lean_models else [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1))
    print(json.dumps({"built_from": provenance, "lean_routing_summary": report["lean_routing_summary"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
