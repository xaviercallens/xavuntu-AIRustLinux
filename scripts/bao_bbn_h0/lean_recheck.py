"""Re-run the kernel check and the Elenchus scan of formal/ANSE/BAO_BBN_H0.lean (ledger stage; fix round).

Compiles the worktree file read-only against the main checkout's Lean build
(`lake env lean`, pinned imports) and writes the raw output plus the exit code
to results/bao_bbn_h0/lean_compile_5_fixround.txt (the ledger stage wrote
lean_compile_3_ledger_recheck.txt, kept as history). Then runs
SocrateAI-Scientific-Elenchus `elenchus_check.py` under `lake env` (so it sees
Mathlib, LL.md 11a) and writes its raw output plus `elenchus_rc=<code>` to
results/bao_bbn_h0/elenchus_check.txt. Nothing git-tracked in the shared
checkout is written.

Run: /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python scripts/bao_bbn_h0/lean_recheck.py
"""
from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEAN_FILE = ROOT / "formal" / "ANSE" / "BAO_BBN_H0.lean"
FORMAL_MAIN = Path("/home/callensxavier_gmail_com/AutoevolveAI/formal")
OUT = ROOT / "results" / "bao_bbn_h0" / "lean_compile_5_fixround.txt"
ELENCHUS = Path("/home/callensxavier_gmail_com/.claude/jobs/4d188676/tmp/elenchus_survey/"
                "SocrateAI-Scientific-Elenchus/tools/elenchus_check.py")
ELENCHUS_OUT = ROOT / "results" / "bao_bbn_h0" / "elenchus_check.txt"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    sha = hashlib.sha256(LEAN_FILE.read_bytes()).hexdigest()
    started = now()
    p = subprocess.run(["timeout", "1500", "lake", "env", "lean", str(LEAN_FILE)],
                       cwd=FORMAL_MAIN, capture_output=True, text=True, check=False)
    body = (f"# command: cd {FORMAL_MAIN} && timeout 1500 lake env lean {LEAN_FILE}\n"
            f"# started_utc: {started}\n# source_sha256: {sha}\n"
            f"{p.stdout}{p.stderr}rc={p.returncode}\n")
    OUT.write_text(body)
    print(body)

    e_started = now()
    e = subprocess.run(["timeout", "1500", "lake", "env", "python3", str(ELENCHUS), str(LEAN_FILE)],
                       cwd=FORMAL_MAIN, capture_output=True, text=True, check=False)
    e_body = (f"# command: cd {FORMAL_MAIN} && lake env python3 {ELENCHUS} {LEAN_FILE}\n"
              f"# started_utc: {e_started}\n# source_sha256: {sha}\n"
              f"{e.stdout}{e.stderr}elenchus_rc={e.returncode}\n")
    ELENCHUS_OUT.write_text(e_body)
    print(e_body)
    return p.returncode if p.returncode != 0 else e.returncode


if __name__ == "__main__":
    raise SystemExit(main())
