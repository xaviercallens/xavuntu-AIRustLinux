#!/usr/bin/env python3
"""Generate specs/lean4/AXIOMS.md: an enumeration of every `axiom` declared
in the Lean specs (goal G3 in the v12 plan). Each axiom is an unchecked
assumption -- the plan's target is <=30, each with a written justification.

This script only enumerates (file, line, name); it deliberately does not
guess a justification. Filling in "Justification" is real review work
(T2/T3), not something to fabricate. Until reviewed, every row is flagged
NEEDS-REVIEW so the gap is visible rather than silently papered over.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lean_tools import analyze_tree  # noqa: E402

LEAN_ROOT = REPO_ROOT / "specs" / "lean4"


def main() -> int:
    stats = analyze_tree(LEAN_ROOT)
    total = sum(len(s.axioms) for s in stats)

    lines = [
        "# Lean 4 Axiom Register",
        "",
        f"Total axioms: {total} (target: <=30, see "
        "docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md goal G3).",
        "",
        "Every `axiom` below is an unchecked assumption Lean takes on faith. "
        "Regenerate this table with `scripts/units/emit_axioms.py` after any "
        "change; do not hand-edit the table rows, only the free-text "
        "justification you add next to NEEDS-REVIEW entries (keep the tool "
        "and this file in sync by moving justified entries into "
        "`JUSTIFIED` in the accompanying `scripts/units/axiom_justifications.json` "
        "-- not yet created; add it when the first justification is written).",
        "",
        "| File | Line | Axiom | Status |",
        "|---|---:|---|---|",
    ]
    for fs in stats:
        if not fs.axioms:
            continue
        rel = Path(fs.path).relative_to(LEAN_ROOT)
        for name, line in fs.axioms:
            lines.append(f"| `{rel}` | {line} | `{name}` | NEEDS-REVIEW |")

    out_path = LEAN_ROOT / "AXIOMS.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_path} ({total} axioms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
