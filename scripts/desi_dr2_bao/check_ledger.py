"""Run the Elenchus ledger gate on the desi_dr2_bao ledger, with controls.

Real run: the committed ledger + evidence store. Since the fix round the six
Tier A rows carry audit objects from the automated workflow referee (a model,
not a person), so the expected real state is rc 0 with no findings; the
pre-audit state (rc 1, 6 unaudited-Tier-A flags) is kept in
ledger/gate_check_pre_audit.{json,log}. Positive control: the gate on
the parent results/bao_flcdm ledger (known state: 3 unaudited-Tier-A flags,
no blocks). Negative controls, on /tmp copies only: (1) a comparison claim
refiled L -> B (must block LEDGER_TIER_INVERSION), (2) one byte of a blob
flipped (must block LEDGER_EVIDENCE_MISMATCH), (3) a citation claim filed at
Tier A (must block LEDGER_KIND_OVERCLAIM). Writes ledger/gate_check.json and
ledger/gate_check.log (verbatim stdout + rc of every run).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LEDGER_DIR = ROOT / "results" / "desi_dr2_bao" / "ledger"
GATE = Path("/home/callensxavier_gmail_com/.claude/jobs/4d188676/tmp/elenchus_survey/"
            "SocrateAI-Scientific-Elenchus/tools/ledger.py")


def run(ledger: Path, evid: Path) -> dict[str, Any]:
    cmd = [sys.executable, str(GATE), "--evidence-dir", str(evid), str(ledger)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    pj = subprocess.run(cmd[:2] + ["--json"] + cmd[2:], capture_output=True, text=True, timeout=120)
    js = json.loads(pj.stdout) if pj.stdout.strip() else {"findings": [], "skipped": ["no json"]}
    codes = sorted({(f["severity"], f["code"]) for f in js["findings"]})
    return {"command": " ".join(cmd), "rc": p.returncode, "stdout": p.stdout, "stderr": p.stderr,
            "n_claims": js.get("claims"), "n_block": sum(f["severity"] == "block" for f in js["findings"]),
            "n_flag": sum(f["severity"] == "flag" for f in js["findings"]), "codes": [list(c) for c in codes],
            "skipped": js.get("skipped", [])}


def mutated(mutate: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="dr2_ledger_negctrl_") as td:
        t = Path(td)
        shutil.copytree(LEDGER_DIR / "evidence", t / "evidence")
        led = json.loads((LEDGER_DIR / "ledger.json").read_text())
        note = mutate(led, t / "evidence")
        (t / "ledger.json").write_text(json.dumps(led, indent=1))
        out = run(t / "ledger.json", t / "evidence")
        out["mutation"] = note
        return out


def to_b(led: dict[str, Any], _: Path) -> str:
    c = next(c for c in led["claims"] if c["id"] == "DR2-L-0006")
    c["id"], c["tier"], c["kind"] = "DR2-B-0999", "B", "exact_harness"
    return "DR2-L-0006 (pull comparison, depends on L citations) refiled as DR2-B-0999 exact_harness"


def tamper(led: dict[str, Any], evid: Path) -> str:
    c = next(c for c in led["claims"] if c["id"] == "DR2-B-0001")
    blob = evid / (c["evidence"].split(":", 1)[1] + ".json")
    raw = bytearray(blob.read_bytes())
    i = raw.index(b"0.29")
    raw[i + 3] = ord("8") if raw[i + 3] != ord("8") else ord("7")
    blob.write_bytes(bytes(raw))
    return f"one digit flipped in the DR2-B-0001 blob at byte {i + 3}"


def overclaim(led: dict[str, Any], _: Path) -> str:
    c = next(c for c in led["claims"] if c["id"] == "DR2-L-0001")
    c["id"], c["tier"] = "DR2-A-0999", "A"
    return "citation DR2-L-0001 refiled at Tier A as DR2-A-0999"


def main() -> int:
    real = run(LEDGER_DIR / "ledger.json", LEDGER_DIR / "evidence")
    parent = ROOT / "results" / "bao_flcdm" / "ledger"
    pos = run(parent / "ledger.json", parent / "evidence")
    n1, n2, n3 = mutated(to_b), mutated(tamper), mutated(overclaim)
    verdict = {
        "real_zero_block": real["n_block"] == 0 and not real["skipped"],
        "real_only_flags_are_unaudited_tier_A": all(c == ["flag", "LEDGER_UNAUDITED_TIER_A"] for c in real["codes"]),
        "real_rc_zero_no_findings": real["rc"] == 0 and real["n_block"] == 0 and real["n_flag"] == 0,
        "positive_control_parent_ledger_zero_block": pos["n_block"] == 0,
        "tier_inversion_caught": ["block", "LEDGER_TIER_INVERSION"] in n1["codes"] and n1["rc"] == 1,
        "blob_tamper_caught": ["block", "LEDGER_EVIDENCE_MISMATCH"] in n2["codes"] and n2["rc"] == 1,
        "kind_overclaim_caught": ["block", "LEDGER_KIND_OVERCLAIM"] in n3["codes"] and n3["rc"] == 1,
    }
    out = {"gate": str(GATE), "real": real, "positive_control_parent_bao_flcdm": pos,
           "neg_tier_inversion": n1, "neg_blob_tamper": n2, "neg_kind_overclaim": n3, "verdict": verdict}
    (LEDGER_DIR / "gate_check.json").write_text(json.dumps(out, indent=1) + "\n")
    with (LEDGER_DIR / "gate_check.log").open("w") as fh:
        for k in ("real", "positive_control_parent_bao_flcdm", "neg_tier_inversion", "neg_blob_tamper", "neg_kind_overclaim"):
            fh.write(f"### {k}\n# command: {out[k]['command']}\n{out[k]['stdout']}{out[k]['stderr']}rc={out[k]['rc']}\n\n")
    print(json.dumps(verdict, indent=1))
    print("real rc", real["rc"])
    print(real["stdout"])
    return 0 if all(verdict.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
