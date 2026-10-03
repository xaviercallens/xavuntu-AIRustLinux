#!/usr/bin/env python3
"""Kernel gate for formal/ANSE/DESI_DR2_wCDM.lean (problem slug: desi_dr2_bao).

Runs `lake env lean <file>` read-only against the MAIN checkout's Lake build
(the worktree has no build of its own), records the real return code, parses
the `#print axioms` output the file emits for each theorem, and applies the
LL.md §2 rule: accept only rc == 0 AND every theorem's axiom set is a subset of
{propext, Classical.choice, Quot.sound}. `sorry` compiles with rc 0, so the
sorryAx check is the only thing that catches it. Optionally runs the Elenchus
scanner in the same `lake env` (LL.md §11a) and records its verdict verbatim.

Writes results/desi_dr2_bao/lean_gate.json and lean_gate.log.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEAN_FILE = REPO / "formal" / "ANSE" / "DESI_DR2_wCDM.lean"
FORMAL_MAIN = Path("/home/callensxavier_gmail_com/AutoevolveAI/formal")
ELENCHUS = Path("/home/callensxavier_gmail_com/.claude/jobs/4d188676/tmp/elenchus_survey/"
                "SocrateAI-Scientific-Elenchus/tools/elenchus_check.py")
RESULTS = REPO / "results" / "desi_dr2_bao"
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
TIMEOUT_S = 1500

AXIOM_RE = re.compile(r"'([^']+)' depends on axioms: \[([^\]]*)\]")
NO_AXIOM_RE = re.compile(r"'([^']+)' does not depend on any axioms")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return 124, out + "\n[TIMEOUT after %d s]" % timeout


def parse_axioms(output: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for name, axioms in AXIOM_RE.findall(output):
        found[name] = [a.strip() for a in axioms.split(",") if a.strip()]
    for name in NO_AXIOM_RE.findall(output):
        found[name] = []
    return found


def expected_theorems(src: str) -> list[str]:
    return re.findall(r"^#print axioms\s+(\S+)", src, flags=re.M)


def main() -> int:
    src = LEAN_FILE.read_text()
    expected = expected_theorems(src)
    ns_match = re.search(r"^namespace\s+(\S+)", src, flags=re.M)
    namespace = ns_match.group(1) if ns_match else ""

    lean_cmd = ["lake", "env", "lean", str(LEAN_FILE)]
    rc, out = run(lean_cmd, FORMAL_MAIN, TIMEOUT_S)
    axioms = parse_axioms(out)
    has_error = bool(re.search(r"^.*: error:", out, flags=re.M))

    per_theorem: dict[str, dict[str, object]] = {}
    all_ok = rc == 0 and not has_error and len(expected) > 0
    for short in expected:
        full = f"{namespace}.{short}" if namespace else short
        ax = axioms.get(full)
        if ax is None:
            ax = axioms.get(short)
        ok = ax is not None and set(ax) <= ALLOWED_AXIOMS
        per_theorem[full] = {"axioms": ax, "footprint_ok": ok,
                             "sorry_free": (ax is not None and "sorryAx" not in ax)}
        all_ok = all_ok and ok

    elenchus: dict[str, object] = {"ran": False}
    if ELENCHUS.exists():
        e_rc, e_out = run(["lake", "env", "python3", str(ELENCHUS), str(LEAN_FILE)], FORMAL_MAIN, TIMEOUT_S)
        elenchus = {"ran": True, "rc": e_rc, "output": e_out, "tool": str(ELENCHUS)}
    else:
        elenchus = {"ran": False, "reason": f"tool not found at {ELENCHUS}"}

    report = {
        "timestamp_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "lean_file": str(LEAN_FILE),
        "lean_file_sha256": sha256(LEAN_FILE),
        "toolchain": (FORMAL_MAIN / "lean-toolchain").read_text().strip(),
        "build_root": str(FORMAL_MAIN),
        "command": " ".join(lean_cmd),
        "rc": rc,
        "compile_errors_present": has_error,
        "allowed_axioms": sorted(ALLOWED_AXIOMS),
        "theorems": per_theorem,
        "gate_pass": all_ok,
        "elenchus": elenchus,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "lean_gate.json").write_text(json.dumps(report, indent=2))
    (RESULTS / "lean_gate.log").write_text(out)
    print(json.dumps({k: v for k, v in report.items() if k not in ("elenchus",)}, indent=2))
    print("ELENCHUS rc:", elenchus.get("rc"), "ran:", elenchus.get("ran"))
    print(elenchus.get("output", elenchus.get("reason", "")))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
