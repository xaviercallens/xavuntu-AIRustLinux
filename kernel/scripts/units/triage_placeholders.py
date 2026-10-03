#!/usr/bin/env python3
"""Generate docs/roadmap/placeholder_triage.csv (goal G6 in the v12 plan).

Applies ONLY the explicit, already-agreed rules from
docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md section 3.2.4:

  - The named boot-critical crates -> IMPLEMENT
  - sys_* -> MERGE into syscall_table
  - driver_base_*, driver_block_*, driver_char_*, driver_tty_* -> MERGE into
    one parent crate per family
  - ext4_*, ipc_*, swap*, security_keyring, security_keys -> REMOVE

Every other placeholder crate is left as REVIEW: the plan itself says this
triage needs a human (or T3) decision for the boot-critical list (see plan
section 8, item 5), so a generator has no business silently deciding scope
for ~90 crates it wasn't told the answer to. Re-run this script whenever
the placeholder set changes (scripts/rust_tools.py defines "placeholder" as
<=25 total LOC in the crate).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from rust_tools import analyze_workspace  # noqa: E402

CRATES_ROOT = REPO_ROOT / "crates"

# From the plan's explicit IMPLEMENT list (boot-critical path).
IMPLEMENT_NAMED = {
    "arch_entry", "arch_irq", "arch_pgtable", "arch_traps", "arch_tlb",
    "sys_read", "sys_write", "sys_open", "sys_close", "sys_exit", "sys_getpid",
    "munmap", "sys_munmap",
    "time_tick", "softirq", "rbtree", "kref", "idr", "percpu", "panic",
}

# From the plan's explicit REMOVE list.
REMOVE_PREFIXES = ("ext4_", "ipc_", "swap")
REMOVE_NAMED = {"security_keyring", "security_keys"}

# From the plan's explicit MERGE rule.
MERGE_RULES = [
    ("sys_", "syscall_table"),
    ("driver_base_", "driver_base"),
    ("driver_block_", "driver_block"),
    ("driver_char_", "driver_char"),
    ("driver_tty_", "driver_tty"),
]


def classify(name: str) -> tuple[str, str]:
    if name in IMPLEMENT_NAMED:
        return "IMPLEMENT", "named in plan section 3.2.4 boot-critical list"
    if name in REMOVE_NAMED or name.startswith(REMOVE_PREFIXES):
        return "REMOVE", "named in plan section 3.2.4 out-of-scope list (ext4_*/ipc_*/swap*/security_key*)"
    for prefix, parent in MERGE_RULES:
        if name.startswith(prefix):
            return "MERGE", f"plan rule: {prefix}* -> {parent}"
    return "REVIEW", "not covered by an explicit plan rule; needs human/T3 decision"


def main() -> int:
    rows = []
    for crate in analyze_workspace(CRATES_ROOT):
        if crate.loc > 25:
            continue
        decision, rationale = classify(crate.name)
        merge_target = ""
        for prefix, parent in MERGE_RULES:
            if crate.name.startswith(prefix):
                merge_target = parent
                break
        rows.append({
            "crate": crate.name,
            "loc": crate.loc,
            "decision": decision,
            "merge_target": merge_target,
            "rationale": rationale,
        })

    rows.sort(key=lambda r: (r["decision"] != "REVIEW", r["crate"]))

    out_path = REPO_ROOT / "docs" / "roadmap" / "placeholder_triage.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["crate", "loc", "decision", "merge_target", "rationale"])
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["decision"]] = counts.get(r["decision"], 0) + 1
    print(f"wrote {out_path} ({len(rows)} crates)")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
