"""Run the Elenchus ledger gate on the real ledger and on three hand-built mutations.

Real ledger: expect zero block-severity findings; the only acceptable flag is
LEDGER_UNAUDITED_TIER_A (round 2: Tier A rows carry model-referee audits, so
none is expected). Mutations 1-3 must each produce a block finding:
  1. a comparison-to-published claim (EVD-L-0006) promoted to Tier B exact_harness
     -> LEDGER_TIER_INVERSION (it rests on Tier L citations);
  2. one evidence blob altered by one byte -> LEDGER_EVIDENCE_MISMATCH;
  3. a citation claim filed as Tier A -> LEDGER_KIND_OVERCLAIM.
  4. the audit object of EVD-A-0004 removed -> LEDGER_UNAUDITED_TIER_A flag, rc 1
     (shows the rc 0 of the real ledger depends on the recorded audits).
Writes results/eboss_vs_desi/ledger/gate_check.json.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LDIR = ROOT / "results" / "eboss_vs_desi" / "ledger"
GATE = Path("/home/callensxavier_gmail_com/.claude/jobs/4d188676/tmp/elenchus_survey/"
            "SocrateAI-Scientific-Elenchus/tools/ledger.py")


def run_gate(ledger: Path, evid: Path) -> dict[str, Any]:
    p = subprocess.run(["python3", str(GATE), "--json", "--evidence-dir", str(evid), str(ledger)],
                       capture_output=True, text=True, check=False)
    res = json.loads(p.stdout)
    codes = sorted({(f["severity"], f["code"]) for f in res["findings"]})
    return {"rc": p.returncode, "n_claims": res["claims"],
            "n_block": sum(f["severity"] == "block" for f in res["findings"]),
            "n_flag": sum(f["severity"] == "flag" for f in res["findings"]),
            "codes": [list(c) for c in codes], "skipped": res["skipped"]}


def main() -> int:
    out: dict[str, Any] = {"gate": str(GATE)}
    out["real"] = run_gate(LDIR / "ledger.json", LDIR / "evidence")
    base = json.loads((LDIR / "ledger.json").read_text())
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        ev = t / "evidence"
        shutil.copytree(LDIR / "evidence", ev)

        m1 = json.loads(json.dumps(base))
        for c in m1["claims"]:
            if c["id"] == "EVD-L-0006":
                c["id"], c["tier"], c["kind"] = "EVD-B-0099", "B", "exact_harness"
        (t / "m1.json").write_text(json.dumps(m1))
        out["mutation_tier_inversion"] = run_gate(t / "m1.json", ev)

        victim = base["claims"][9]["evidence"].split(":", 1)[1]
        bp = ev / f"{victim}.json"
        raw = bytearray(bp.read_bytes())
        raw[-2] = ord(" ") if raw[-2] != ord(" ") else ord("\t")
        bp.write_bytes(bytes(raw))
        out["mutation_blob_tamper"] = run_gate(LDIR / "ledger.json", ev)
        out["mutation_blob_tamper"]["tampered_claim"] = base["claims"][9]["id"]
        shutil.rmtree(ev)
        shutil.copytree(LDIR / "evidence", ev)

        m3 = json.loads(json.dumps(base))
        for c in m3["claims"]:
            if c["id"] == "EVD-L-0002":
                c["id"], c["tier"] = "EVD-A-0099", "A"
        (t / "m3.json").write_text(json.dumps(m3))
        out["mutation_kind_overclaim"] = run_gate(t / "m3.json", ev)

        m4 = json.loads(json.dumps(base))
        for c in m4["claims"]:
            if c["id"] == "EVD-A-0004":
                c["audit"] = None
        (t / "m4.json").write_text(json.dumps(m4))
        out["mutation_drop_audit"] = run_gate(t / "m4.json", ev)


    def has(r: dict[str, Any], code: str) -> bool:
        return ["block", code] in r["codes"]

    out["verdict"] = {
        "real_zero_block": out["real"]["n_block"] == 0 and not out["real"]["skipped"],
        "real_only_flags_are_unaudited_tier_A": out["real"]["codes"] in ([], [["flag", "LEDGER_UNAUDITED_TIER_A"]]),
        "tier_inversion_caught": has(out["mutation_tier_inversion"], "LEDGER_TIER_INVERSION"),
        "blob_tamper_caught": has(out["mutation_blob_tamper"], "LEDGER_EVIDENCE_MISMATCH"),
        "kind_overclaim_caught": has(out["mutation_kind_overclaim"], "LEDGER_KIND_OVERCLAIM"),
        "drop_audit_flagged": ["flag", "LEDGER_UNAUDITED_TIER_A"] in out["mutation_drop_audit"]["codes"]
                              and out["mutation_drop_audit"]["rc"] == 1,
    }
    (LDIR / "gate_check.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0 if all(out["verdict"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
