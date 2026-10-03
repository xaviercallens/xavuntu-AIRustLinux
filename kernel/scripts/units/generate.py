#!/usr/bin/env python3
"""Generate oracle-checkable work units for the low-tier-model workflow
described in docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md section 4.

Each unit is a small JSON "card": one sorry to eliminate, one unsafe block
needing a SAFETY comment, one static mut to replace, or one placeholder
crate to triage. Cards are written as JSON (not YAML, despite the example
in the plan) so scripts/check_unit.py has zero third-party dependencies.

Usage:
    scripts/units/generate.py --type lean_sorry --limit 20 --out-dir docs/roadmap/units
    scripts/units/generate.py --summary-only   # counts only, no files written

Generated cards are NOT meant to be committed in bulk (they are fully
reproducible from the tree, and there would be ~1,400 of them). The
--out-dir default is docs/roadmap/units/, which is gitignored; commit only
docs/roadmap/units_summary.json (small, produced by --summary-only) and any
hand-picked example cards a PR wants to show.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lean_tools import analyze_tree as lean_analyze_tree  # noqa: E402
from rust_tools import analyze_workspace, UNSAFE_BLOCK_RE, STATIC_MUT_RE  # noqa: E402

LEAN_ROOT = REPO_ROOT / "specs" / "lean4"
CRATES_ROOT = REPO_ROOT / "crates"


def gen_lean_sorry_units() -> list[dict]:
    """One unit per theorem containing >=1 `sorry` in a ~40-line window
    after its header. This is a heuristic grouping for work assignment; it
    can over- or under-attribute a sorry when theorems sit close together.
    The authoritative sorry count is metrics.py's lean.sorry (raw token
    count), not len(units) here -- the oracle for a unit is always a real
    `lake env lean` run, so a wrong attribution just fails cleanly rather
    than producing a false pass."""
    units = []
    for fs in lean_analyze_tree(LEAN_ROOT):
        rel = str(Path(fs.path).relative_to(LEAN_ROOT))
        for t in fs.theorems:
            if not t.has_sorry:
                continue
            units.append({
                "id": f"lean_sorry::{rel}::{t.name}",
                "type": "lean_sorry",
                "file": f"specs/lean4/{rel}",
                "target": f"theorem {t.name}",
                "line": t.line,
                "statement_hash": t.statement_hash,
                "allowed_edits": [f"specs/lean4/{rel}"],
                "hints": [
                    "try: simp [*]",
                    "try: omega",
                    "try: decide",
                    "try: aesop",
                    "try: induction on the relevant argument, then simp_all",
                ],
                "oracle": f"scripts/check_unit.py --type lean_sorry --file specs/lean4/{rel} --theorem {t.name}",
                "max_attempts": 3,
                "escalate_to": "T2",
            })
    return units


def gen_unsafe_safety_units() -> list[dict]:
    units = []
    for crate in analyze_workspace(CRATES_ROOT):
        if crate.unsafe_blocks == 0:
            continue
        for rs_file in crate.rs_files:
            text = rs_file.read_text(encoding="utf-8", errors="replace")
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if not UNSAFE_BLOCK_RE.search(line):
                    continue
                window = "\n".join(lines[max(0, i - 5):i])
                if "SAFETY:" in window:
                    continue
                rel = str(rs_file.relative_to(REPO_ROOT))
                units.append({
                    "id": f"unsafe_safety::{rel}::{i + 1}",
                    "type": "unsafe_safety",
                    "file": rel,
                    "line": i + 1,
                    "crate": crate.name,
                    "allowed_edits": [rel],
                    "instructions": (
                        "Add a `// SAFETY:` comment immediately above this "
                        "unsafe block explaining why it is sound: pointer "
                        "non-null/alignment/validity, lifetime, no data "
                        "race. Do not change behavior."
                    ),
                    "oracle": f"scripts/check_unit.py --type unsafe_safety --file {rel} --crate {crate.name}",
                    "max_attempts": 3,
                    "escalate_to": "T2",
                })
    return units


def gen_static_mut_units() -> list[dict]:
    units = []
    for crate in analyze_workspace(CRATES_ROOT):
        if crate.static_mut == 0:
            continue
        for rs_file in crate.rs_files:
            text = rs_file.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.split("\n")):
                if not STATIC_MUT_RE.search(line):
                    continue
                rel = str(rs_file.relative_to(REPO_ROOT))
                units.append({
                    "id": f"static_mut::{rel}::{i + 1}",
                    "type": "static_mut",
                    "file": rel,
                    "line": i + 1,
                    "crate": crate.name,
                    "allowed_edits": [rel],
                    "instructions": (
                        "Replace this `static mut` with a safe kernel-side "
                        "primitive (AtomicX, a spinlock-guarded UnsafeCell, "
                        "or a once-cell), preserving behavior. The crate "
                        "must still build and its existing tests must pass."
                    ),
                    "oracle": f"scripts/check_unit.py --type static_mut --file {rel} --crate {crate.name}",
                    "max_attempts": 3,
                    "escalate_to": "T2",
                })
    return units


def gen_placeholder_triage_units() -> list[dict]:
    units = []
    for crate in analyze_workspace(CRATES_ROOT):
        if crate.loc > 25:
            continue
        rel = str(crate.path.relative_to(REPO_ROOT))
        units.append({
            "id": f"placeholder_triage::{crate.name}",
            "type": "placeholder_triage",
            "crate": crate.name,
            "path": rel,
            "loc": crate.loc,
            "instructions": (
                "This crate is a near-empty placeholder. Decide IMPLEMENT "
                "(it is on the boot-critical path or needed by the core "
                "set), MERGE (fold into a named parent crate), or REMOVE "
                "(out of scope for a minimal verified core). Record the "
                "decision in docs/roadmap/placeholder_triage.csv; do not "
                "act on REMOVE without human/T3 sign-off."
            ),
            "oracle": "human/T3 review of docs/roadmap/placeholder_triage.csv row",
            "escalate_to": "T3",
        })
    return units


GENERATORS = {
    "lean_sorry": gen_lean_sorry_units,
    "unsafe_safety": gen_unsafe_safety_units,
    "static_mut": gen_static_mut_units,
    "placeholder_triage": gen_placeholder_triage_units,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--type", choices=sorted(GENERATORS) + ["all"], default="all")
    parser.add_argument("--limit", type=int, default=None, help="cap units per type (for a pilot wave)")
    parser.add_argument("--file-contains", default=None, help="only include units whose file path contains this substring (for hand-picked example sets)")
    parser.add_argument("--out-dir", default="docs/roadmap/units")
    parser.add_argument("--summary-only", action="store_true", help="print counts, write only units_summary.json")
    args = parser.parse_args()

    types = list(GENERATORS) if args.type == "all" else [args.type]
    summary = {}
    out_dir = REPO_ROOT / args.out_dir
    total = 0
    for t in types:
        units = GENERATORS[t]()
        summary[t] = len(units)
        total += len(units)
        if args.summary_only:
            continue
        filtered = (
            [u for u in units if args.file_contains in u.get("file", u.get("path", ""))]
            if args.file_contains else units
        )
        capped = filtered[: args.limit] if args.limit else filtered
        type_dir = out_dir / t
        type_dir.mkdir(parents=True, exist_ok=True)
        for u in capped:
            safe_id = u["id"].replace("/", "_").replace("::", "__")
            (type_dir / f"{safe_id}.json").write_text(json.dumps(u, indent=2) + "\n", encoding="utf-8")
        print(f"{t}: {len(capped)}/{len(units)} cards written to {type_dir}")

    print(f"\nTotal units: {total}")
    # Only a full, unfiltered run describes the whole tree; filtered/partial runs
    # must not overwrite the committed summary.
    if args.type == "all" and not args.file_contains and not args.limit:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
        summary_path = REPO_ROOT / "docs" / "roadmap" / "units_summary.json"
        summary_path.write_text(json.dumps({"git.commit": commit, "total": total, "by_type": summary}, indent=2) + "\n", encoding="utf-8")
        print(f"Summary written to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
