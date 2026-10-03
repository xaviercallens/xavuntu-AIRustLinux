"""Regenerate the paper inputs and build papers/bao_bbn_h0/bao_bbn_h0.pdf with pdflatex (two passes).

Writes papers/bao_bbn_h0/build_log.json with each pass's exit code and the
warnings found in the final .log (undefined references/citations, rerun
requests, missing characters, overfull boxes).

Run: /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python scripts/bao_bbn_h0/build_paper.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "papers" / "bao_bbn_h0"
TEX = "bao_bbn_h0.tex"


def main() -> int:
    gen = subprocess.run([sys.executable, str(ROOT / "scripts" / "bao_bbn_h0" / "make_paper_inputs.py")],
                         capture_output=True, text=True, check=False)
    print(gen.stdout, gen.stderr)
    if gen.returncode != 0:
        return gen.returncode
    passes = []
    for i in (1, 2):
        p = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", TEX],
                           cwd=PAPER, capture_output=True, text=True, check=False)
        passes.append({"pass": i, "rc": p.returncode, "tail": p.stdout[-1500:]})
        print(f"pass {i}: rc={p.returncode}")
        if p.returncode != 0:
            print(p.stdout[-4000:])
            break
    log = (PAPER / "bao_bbn_h0.log").read_text(errors="replace")
    warn = {
        "undefined": re.findall(r"^.*undefined.*$", log, flags=re.M),
        "rerun": re.findall(r"^.*Rerun.*$", log, flags=re.M),
        "missing_character": re.findall(r"^.*Missing character.*$", log, flags=re.M),
        "overfull": re.findall(r"^Overfull.*$", log, flags=re.M),
    }
    pages = re.findall(r"Output written on .*? \((\d+) pages", log)
    out = {"passes": passes, "warnings": warn, "pages": pages}
    (PAPER / "build_log.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({"rc": [x["rc"] for x in passes], "pages": pages,
                      "counts": {k: len(v) for k, v in warn.items()}, "warn": warn}, indent=1))
    return 0 if all(x["rc"] == 0 for x in passes) and len(passes) == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
