#!/usr/bin/env python3
"""Freeze the hardness ladder as the held-out test split.

Every ladder item's *proposition* (statement minus `theorem <name>`) is
normalized and hashed. The trainer's DATA step drops any training row whose
text contains a frozen proposition, so benchmark items (or renamed copies of
them — e.g. run one's `two_dvd_consec` is the ladder's `t0_two_dvd`) can never
leak into training and inflate the eval.

Output: results/hardness/frozen_split.json
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "results" / "hardness"


def normalize_prop(statement: str) -> str:
    """`theorem foo (n : ℕ) : P n` -> `(n : ℕ) : P n` with whitespace collapsed."""
    s = re.sub(r"^\s*(theorem|lemma)\s+\S+\s*", "", statement)
    return re.sub(r"\s+", " ", s).strip()


def main() -> int:
    ladder = json.loads((OUT / "ladder.json").read_text())
    frozen = []
    for it in ladder:
        prop = normalize_prop(it["statement"])
        frozen.append({"id": it["id"], "tier": it["tier"], "prop": prop,
                       "sha": hashlib.sha256(prop.encode()).hexdigest()[:16]})
    (OUT / "frozen_split.json").write_text(json.dumps(frozen, indent=1))
    print(f"frozen {len(frozen)} propositions -> {OUT / 'frozen_split.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
