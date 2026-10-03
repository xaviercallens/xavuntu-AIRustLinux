#!/usr/bin/env python3
"""Build the tiered Lean hardness ladder from Sage-verified curve facts.

Tiers (the label is a hypothesis; the measured pass rate decides difficulty):
  T0  Mathlib-level arithmetic/algebra lemmas
  T1  a Sage-supplied point lies on a Cremona curve
  T2  the curve's discriminant equals Sage's value
  T3  group law: 2P computed with Mathlib's slope/addX/addY equals Sage's 2P
  T4  sentinel: the BSD rank statement itself (expected to fail)

Each curve tier mixes TRUE facts with FALSE variants (Sage-verified false).
A FALSE item that passes the Lean gate means the gate is broken.

Validation before any prover sees the ladder:
  * every statement elaborates with `sorry` (well-formed on this Mathlib)
  * no statement's proposition is vacuous (`True`)
  * reference proofs (positive controls) are attempted; kept in a separate
    controls file and NEVER placed in a prover prompt.

Output: results/hardness/ladder.json + results/hardness/validation.json
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FACTS = REPO / "results" / "hardness" / "curve_facts.json"
OUT = REPO / "results" / "hardness"
FORMAL = Path("/home/callensxavier_gmail_com/AutoevolveAI/formal")
TMP = Path("/home/callensxavier_gmail_com/.claude/jobs/4d188676/tmp/ladder")

HEADER = """import Mathlib.AlgebraicGeometry.EllipticCurve.Affine.Formula
import Mathlib.AlgebraicGeometry.EllipticCurve.Weierstrass
import Mathlib.Data.Real.Basic
import Mathlib.Data.ZMod.Basic
import Mathlib.Tactic.NormNum
import Mathlib.Tactic.Ring
import Mathlib.Tactic.Linarith
import Mathlib.Tactic.Positivity
"""

TRUSTED = {"propext", "Classical.choice", "Quot.sound"}
PER_TIER_TRUE = 12
PER_TIER_FALSE = 4


def q(s: str) -> str:
    """Sage rational string -> Lean ℚ literal."""
    return f"({s} : ℚ)"


def curve_def(name: str, a: list[str]) -> str:
    return f"def {name} : WeierstrassCurve ℚ := ⟨{', '.join(q(x) for x in a)}⟩"


T0 = [
    ("t0_add_comm", "theorem t0_add_comm (a b : ℕ) : a + b = b + a", "by omega"),
    ("t0_mul_comm", "theorem t0_mul_comm (a b : ℤ) : a * b = b * a", "by ring"),
    ("t0_sq_nonneg", "theorem t0_sq_nonneg (x : ℝ) : 0 ≤ x ^ 2", "by positivity"),
    ("t0_two_dvd", "theorem t0_two_dvd (n : ℕ) : 2 ∣ n * (n + 1)",
     "by exact Nat.even_iff_two_dvd.mp (Nat.even_mul_succ_self n)"),
    ("t0_sum_sq", "theorem t0_sum_sq (a b : ℝ) : 2 * a * b ≤ a ^ 2 + b ^ 2",
     "by nlinarith [sq_nonneg (a - b)]"),
    ("t0_cube_diff", "theorem t0_cube_diff (a b : ℤ) : a ^ 3 - b ^ 3 = (a - b) * (a ^ 2 + a * b + b ^ 2)", "by ring"),
    ("t0_abs_tri", "theorem t0_abs_tri (a b : ℝ) : |a + b| ≤ |a| + |b|", "by exact abs_add_le a b"),
    ("t0_sq_eq", "theorem t0_sq_eq (x : ℝ) (h : x ^ 2 = 4) (hx : 0 < x) : x = 2",
     "by nlinarith [sq_nonneg (x - 2), sq_nonneg (x + 2)]"),
    ("t0_zmod", "theorem t0_zmod : (3 : ZMod 7) * 5 = 1", "by decide"),
    ("t0_amgm", "theorem t0_amgm (a b : ℝ) (ha : 0 ≤ a) (hb : 0 ≤ b) : a * b ≤ ((a + b) / 2) ^ 2",
     "by nlinarith [sq_nonneg (a - b)]"),
]

REF_T1 = "by rw [WeierstrassCurve.Affine.equation_iff]; norm_num [{W}]"
REF_T2 = ("by norm_num [{W}, WeierstrassCurve.Δ, WeierstrassCurve.b₂, "
          "WeierstrassCurve.b₄, WeierstrassCurve.b₆, WeierstrassCurve.b₈]")
REF_T3 = ("by norm_num [{W}, WeierstrassCurve.Affine.slope, WeierstrassCurve.Affine.addX, "
          "WeierstrassCurve.Affine.addY, WeierstrassCurve.Affine.negY, "
          "WeierstrassCurve.Affine.negAddY]")


def build_items() -> list[dict]:
    facts = json.loads(FACTS.read_text())
    items: list[dict] = []
    for name, stmt, ref in T0:
        items.append({"id": name, "tier": "T0", "truth": True, "defs": "",
                      "statement": stmt, "reference": ref})

    def add_curve_tier(tier: str, key: str, make, ref_tmpl: str) -> None:
        trues = [r for r in facts if key in r][:PER_TIER_TRUE]
        falses = [r for r in facts if f"false_{key}" in r][-PER_TIER_FALSE:]
        for r, truth in [(r, True) for r in trues] + [(r, False) for r in falses]:
            w = "W_" + re.sub(r"\W", "_", r["label"])
            val = r[key] if truth else r[f"false_{key}"]
            tid = f"{tier.lower()}_{r['label']}_{'T' if truth else 'F'}"
            items.append({
                "id": tid, "tier": tier, "truth": truth, "label": r["label"],
                "defs": curve_def(w, r["a"]),
                "statement": f"theorem {tid} : {make(w, r, val)}",
                "reference": ref_tmpl.format(W=w),
            })

    add_curve_tier("T1", "point",
                   lambda w, r, v: f"{w}.toAffine.Equation {q(v[0])} {q(v[1])}", REF_T1)
    add_curve_tier("T2", "disc",
                   lambda w, r, v: f"{w}.Δ = {q(v)}", REF_T2)

    def dbl(w: str, r: dict, v: list[str]) -> str:
        x, y = q(r["point"][0]), q(r["point"][1])
        ell = f"({w}.toAffine.slope {x} {x} {y} {y})"
        return (f"{w}.toAffine.addX {x} {x} {ell} = {q(v[0])} ∧ "
                f"{w}.toAffine.addY {x} {x} {y} {ell} = {q(v[1])}")

    add_curve_tier("T3", "double", dbl, REF_T3)

    items.append({
        "id": "t4_bsd_rank", "tier": "T4", "truth": None, "defs": "",
        "statement": "theorem t4_bsd_rank : ANSE.BSD_RankStatement",
        "reference": "", "note": "sentinel: open problem; any pass = gate bug",
        "extra_imports": "import ANSE.BSD_RankStatement\n",
    })
    return items


def lean_file(item: dict, proof: str) -> str:
    return (HEADER + item.get("extra_imports", "") + "\n" + item["defs"] + "\n\n"
            + f"{item['statement']} := {proof}\n\n#print axioms {item['id']}\n")


def compile_one(src: str, tag: str) -> dict:
    TMP.mkdir(parents=True, exist_ok=True)
    f = TMP / f"{tag}.lean"
    f.write_text(src, encoding="utf-8")
    t0 = time.time()
    res = subprocess.run(["lake", "env", "lean", str(f)], cwd=str(FORMAL),
                         capture_output=True, text=True, timeout=900)
    out = res.stdout + res.stderr
    axioms: list[str] = []
    if "depends on axioms:" in out:
        part = out.split("depends on axioms:")[1].split("\n")[0]
        axioms = [a.strip() for a in part.strip(" []").split(",") if a.strip()]
    elif "does not depend on any axioms" in out:
        axioms = []
    return {"rc": res.returncode, "axioms": axioms, "secs": round(time.time() - t0, 1),
            "clean": res.returncode == 0 and "sorryAx" not in out and set(axioms) <= TRUSTED,
            "tail": out[-300:]}


def main() -> int:
    items = build_items()
    report = []
    for it in items:
        vacuous = bool(re.search(r":\s*True\s*$", it["statement"]))
        wf = compile_one(lean_file(it, "by sorry"), f"wf_{it['id']}")
        # well-formed = elaborates, and the only axiom trouble is sorry itself
        well_formed = wf["rc"] == 0 and "error" not in wf["tail"].lower()
        ref = compile_one(lean_file(it, it["reference"]), f"ref_{it['id']}") if it["reference"] else None
        row = {"id": it["id"], "tier": it["tier"], "truth": it["truth"],
               "vacuous": vacuous, "well_formed": well_formed,
               "reference_clean": ref["clean"] if ref else None}
        # Control semantics: a FALSE item's reference proof must NOT go through.
        if it["truth"] is False and ref and ref["clean"]:
            row["CONTROL_FAILURE"] = "reference proof accepted a false statement"
        report.append(row)
        print(json.dumps(row), flush=True)

    usable = [it for it, r in zip(items, report) if r["well_formed"] and not r["vacuous"]]
    OUT.mkdir(parents=True, exist_ok=True)
    # Prompts never see references: strip them from the ladder, keep them in controls.
    (OUT / "ladder.json").write_text(json.dumps(
        [{k: v for k, v in it.items() if k != "reference"} for it in usable], indent=1))
    (OUT / "controls.json").write_text(json.dumps(
        {it["id"]: it["reference"] for it in usable}, indent=1))
    (OUT / "validation.json").write_text(json.dumps(report, indent=1))
    bad = [r for r in report if r.get("CONTROL_FAILURE")]
    print(f"\nitems={len(items)} usable={len(usable)} control_failures={len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
