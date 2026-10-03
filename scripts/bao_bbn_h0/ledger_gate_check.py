"""Run the Elenchus ledger gate on the real bao_bbn_h0 ledger and on three hand-built mutations.

Real ledger: expect zero block-severity findings (Tier-A 'unaudited' flags are
expected and left open; they make ledger.py exit 1). Mutations, each must
produce a block finding:
  1. the headline verdict claim (BBNH0-L-0008, a comparison with a published
     number) promoted to Tier B exact_harness -> LEDGER_TIER_INVERSION;
  2. one evidence blob altered by one byte -> LEDGER_EVIDENCE_MISMATCH;
  3. a citation claim (BBNH0-L-0001) filed as Tier A -> LEDGER_KIND_OVERCLAIM.
Writes results/bao_bbn_h0/ledger/gate_check.json (with the real gate's stdout).

Run: /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python scripts/bao_bbn_h0/ledger_gate_check.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LDIR = ROOT / "results" / "bao_bbn_h0" / "ledger"
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
    plain = subprocess.run(["python3", str(GATE), "--evidence-dir", str(LDIR / "evidence"), str(LDIR / "ledger.json")],
                           capture_output=True, text=True, check=False)
    out["real_plain"] = {"rc": plain.returncode, "stdout": plain.stdout, "stderr": plain.stderr}
    base = json.loads((LDIR / "ledger.json").read_text())
    ids = [c["id"] for c in base["claims"]]
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        ev = t / "evidence"
        shutil.copytree(LDIR / "evidence", ev)

        m1 = json.loads(json.dumps(base))
        for c in m1["claims"]:
            if c["id"] == "BBNH0-L-0008":
                c["id"], c["tier"], c["kind"] = "BBNH0-B-0099", "B", "exact_harness"
        (t / "m1.json").write_text(json.dumps(m1))
        out["mutation_tier_inversion"] = run_gate(t / "m1.json", ev)

        vi = ids.index("BBNH0-B-0001")
        victim = base["claims"][vi]["evidence"].split(":", 1)[1]
        bp = ev / f"{victim}.json"
        raw = bytearray(bp.read_bytes())
        raw[-2] = ord(" ") if raw[-2] != ord(" ") else ord("\t")
        bp.write_bytes(bytes(raw))
        out["mutation_blob_tamper"] = run_gate(LDIR / "ledger.json", ev)
        out["mutation_blob_tamper"]["tampered_claim"] = "BBNH0-B-0001"
        shutil.rmtree(ev)
        shutil.copytree(LDIR / "evidence", ev)

        m3 = json.loads(json.dumps(base))
        for c in m3["claims"]:
            if c["id"] == "BBNH0-L-0001":
                c["id"], c["tier"] = "BBNH0-A-0099", "A"
        (t / "m3.json").write_text(json.dumps(m3))
        out["mutation_kind_overclaim"] = run_gate(t / "m3.json", ev)

    def has(r: dict[str, Any], code: str) -> bool:
        return ["block", code] in r["codes"]

    out["verdict"] = {
        "real_zero_block": out["real"]["n_block"] == 0 and not out["real"]["skipped"],
        "real_only_flags_are_unaudited_tier_A": out["real"]["codes"] in ([], [["flag", "LEDGER_UNAUDITED_TIER_A"]]),
        "tier_inversion_caught": has(out["mutation_tier_inversion"], "LEDGER_TIER_INVERSION"),
        "blob_tamper_caught": has(out["mutation_blob_tamper"], "LEDGER_EVIDENCE_MISMATCH"),
        "kind_overclaim_caught": has(out["mutation_kind_overclaim"], "LEDGER_KIND_OVERCLAIM"),
    }
    (LDIR / "gate_check.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "real_plain"}, indent=1))
    print(out["real_plain"]["stdout"] + f"exit code {out['real_plain']['rc']}")
    return 0 if all(out["verdict"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
