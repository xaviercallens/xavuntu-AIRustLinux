"""Regenerate results/bao_bbn_h0/lean_verification.json from the fix-round logs (every verdict parsed, none typed).

Inputs: lean_compile_4_fixround_attempt1.txt (failed attempt, kept), lean_compile_5_fixround.txt (accepted),
lean_negative_control_sorry_fixround.txt, elenchus_check.txt, and the Lean source itself.
Run: /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python scripts/bao_bbn_h0/write_lean_verification.py
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "bao_bbn_h0"
LEAN = ROOT / "formal" / "ANSE" / "BAO_BBN_H0.lean"
TRUSTED = ["propext", "Classical.choice", "Quot.sound"]


def rc_of(text: str) -> int:
    m = re.search(r"^rc=(\d+)$", text, flags=re.M)
    if m is None:
        raise ValueError("no rc line")
    return int(m.group(1))


def footprints(text: str) -> dict[str, list[str]]:
    return {n: [a.strip() for a in ax.split(",")]
            for n, ax in re.findall(r"'ANSE\.BAOBBNH0\.(\w+)' depends on axioms: \[(.*?)\]", text)}


def main() -> int:
    src = LEAN.read_text()
    sha = hashlib.sha256(LEAN.read_bytes()).hexdigest()
    theorems = re.findall(r"^theorem (\w+)", src, flags=re.M)
    imports = re.findall(r"^import (\S+)", src, flags=re.M)
    a1 = (RES / "lean_compile_4_fixround_attempt1.txt").read_text()
    a2 = (RES / "lean_compile_5_fixround.txt").read_text()
    neg = (RES / "lean_negative_control_sorry_fixround.txt").read_text()
    el = (RES / "elenchus_check.txt").read_text()
    if f"# source_sha256: {sha}" not in a2 or f"# source_sha256: {sha}" not in el:
        raise RuntimeError("accepted compile / Elenchus log is not for the current source")
    fp = footprints(a2)
    if sorted(fp) != sorted(theorems):
        raise RuntimeError(f"footprint set {sorted(fp)} != theorems {sorted(theorems)}")
    clean = rc_of(a2) == 0 and all(sorted(v) == sorted(TRUSTED) for v in fp.values()) \
        and "error" not in a2.lower() and "warning" not in a2.lower()
    fp_neg = footprints(neg)
    neg_sorry = [n for n, v in fp_neg.items() if "sorryAx" in v]
    out = {
        "problem": "bao_bbn_h0", "stage": "Lean 4 formalization (referee fix round)",
        "file": "formal/ANSE/BAO_BBN_H0.lean", "namespace": "ANSE.BAOBBNH0",
        "file_sha256_after_final_compile": sha,
        "previous_file_sha256": "c0663994721a6113ad4569c29298c516d659a97ffc93db91a2123fe113483689",
        "regenerated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fix_round_changes": [
            "docstrings/header: 'depends on (h, r_d) only through h r_d' now says AT FIXED E (referee issue 1)",
            "new theorems hrd_mono_generic and hrd_strictMonoOn_h: the preregistered identifiability statement "
            "'h r_d(h) strictly increasing in h', with the hypothesis omega_nu <= (1-2a) Omega_m h^2 (referee issue 2)",
            "import added: Mathlib.Analysis.Convex.SpecificFunctions.Basic (for Bernoulli's inequality "
            "rpow_one_add_le_one_add_mul_self; its .olean is present in the partial build)",
        ],
        "environment": "main checkout build: cd /home/callensxavier_gmail_com/AutoevolveAI/formal && timeout 1500 lake env "
                       "lean <worktree file> (pinned imports; no 'import Mathlib', no lake build, LeanMaster fallback NOT used)",
        "imports": imports, "theorems": theorems,
        "compile_runs": [
            {"log": "results/bao_bbn_h0/lean_compile_4_fixround_attempt1.txt", "rc": rc_of(a1),
             "n_errors": len(re.findall(r": error", a1)),
             "sorryAx_in": [n for n, v in footprints(a1).items() if "sorryAx" in v],
             "verdict": "fail"},
            {"log": "results/bao_bbn_h0/lean_compile_5_fixround.txt", "rc": rc_of(a2),
             "verdict": "pass" if clean else "fail"},
        ],
        "axioms_per_theorem": fp, "sorryAx_present": any("sorryAx" in v for v in fp.values()),
        "accepted": clean,
        "negative_control": {
            "log": "results/bao_bbn_h0/lean_negative_control_sorry_fixround.txt",
            "mutation": "copy in /tmp with the proof of hrd_strictMonoOn_h replaced by `sorry`",
            "rc": rc_of(neg), "theorems_with_sorryAx": neg_sorry,
            "discriminating": rc_of(neg) == 0 and neg_sorry == ["hrd_strictMonoOn_h"],
        },
        "elenchus": {"log": "results/bao_bbn_h0/elenchus_check.txt",
                     "output": "no findings" if "no findings" in el else "findings",
                     "rc": int(re.search(r"elenchus_rc=(\d+)", el).group(1))},
        "scope_note": "Theorems concern the SECONDARY (Aubourg eq. 16) r_d and the shared D_H/r_d and gate algebra "
                      "as coded in scripts/bao_bbn_h0/common.py; nothing about the PRIMARY CAMB r_d or any fitted number. "
                      "The CAMB-table analogue of hrd_strictMonoOn_h is checked numerically only "
                      "(results/bao_bbn_h0/fixround_diagnostics.json).",
    }
    (RES / "lean_verification.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("accepted", "compile_runs", "negative_control", "elenchus")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
