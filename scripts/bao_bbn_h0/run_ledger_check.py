"""Run the Elenchus ledger gate on results/bao_bbn_h0/ledger and save its real output + exit code.

Usage: python3 scripts/bao_bbn_h0/run_ledger_check.py <output-file-name under results/bao_bbn_h0/ledger/>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER_DIR = ROOT / "results" / "bao_bbn_h0" / "ledger"
TOOL = Path("/home/callensxavier_gmail_com/.claude/jobs/4d188676/tmp/elenchus_survey/"
            "SocrateAI-Scientific-Elenchus/tools/ledger.py")


def main(argv: list[str]) -> int:
    out_name = argv[1] if len(argv) > 1 else "ledger_check.txt"
    cmd = ["python3", str(TOOL), "--evidence-dir", str(LEDGER_DIR / "evidence"), str(LEDGER_DIR / "ledger.json")]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    text = f"# command: {' '.join(cmd)}\n{p.stdout}{p.stderr}\nrc={p.returncode}\n"
    (LEDGER_DIR / out_name).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
