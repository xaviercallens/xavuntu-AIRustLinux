#!/usr/bin/env python3
"""H1 experiment: do dedicated Lean prover models beat general models?

For each (model, theorem statement): generate a proof via Ollama, compile it
with `lake env lean` against the real Mathlib toolchain, and check
`#print axioms` against the trusted whitelist. Every LLM call is appended to
a JSONL log. Nothing is simulated; the pass/fail table is whatever the Lean
kernel says.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, "/mnt/disks/disk-socrateai-local-1/gpu_lease")

from gpu_lease import gpu_lease  # noqa: E402

TRUSTED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
LEASE_HOLDER = "autoevolve-prover-bakeoff"

# `import Mathlib` is NOT available here: the local Mathlib build is partial
# (3,431 oleans, no umbrella). This header is exactly what the already-built
# ANSE.MasterMathTribunal module imports, so every module in it has an olean.
HEADER = """import Mathlib.GroupTheory.Index
import Mathlib.Analysis.InnerProductSpace.Basic
import Mathlib.Data.Real.Basic
import Mathlib.Data.ZMod.Basic
import Mathlib.Tactic.Ring
import Mathlib.Tactic.Linarith
"""

STATEMENTS = [
    ("add_comm_nat", "theorem add_comm_nat (a b : ℕ) : a + b = b + a"),
    ("two_dvd_consec", "theorem two_dvd_consec (n : ℕ) : 2 ∣ n * (n + 1)"),
    ("sq_nonneg_real", "theorem sq_nonneg_real (x : ℝ) : 0 ≤ x ^ 2"),
]


def generate(model: str, statement: str, call_log: Path, temperature: float = 0.0,
             timeout_s: float = 900.0) -> str:
    prompt = (
        "Complete the following Lean 4 theorem with a correct proof. "
        "Use Lean 4 / Mathlib syntax only (no Lean 3). Do not use sorry. "
        "Output only the complete Lean 4 code block.\n\n"
        f"```lean4\n{HEADER}\n{statement} := by\n```"
    )
    t0 = time.time()
    resp = httpx.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 800},
        },
        timeout=timeout_s,
    )
    resp.raise_for_status()
    body = resp.json()
    text = body.get("response", "")
    with open(call_log, "a") as f:
        f.write(json.dumps({
            "timestamp": datetime.now(UTC).isoformat(),
            "model": model,
            "input": {"prompt": prompt, "temperature": 0.0, "num_predict": 800},
            "output": {"text": text, "eval_count": body.get("eval_count", 0)},
            "elapsed_s": round(time.time() - t0, 2),
        }) + "\n")
    return text


def extract_lean(text: str, statement: str) -> str:
    blocks = re.findall(r"```(?:lean4|lean)?\s*\n(.*?)```", text, re.DOTALL)
    code = max(blocks, key=len).strip() if blocks else text.strip()
    # Strip every model-emitted import: `import Mathlib` does not resolve on
    # this partial build, so imports are OURS to control via HEADER.
    body = "\n".join(ln for ln in code.splitlines() if not ln.lstrip().startswith("import "))
    body = body.strip()
    if not body.startswith(("theorem", "lemma", "example", "open", "set_option")):
        # Model emitted only the proof body after `:= by`.
        body = f"{statement} := by\n" + "\n".join(
            "  " + ln if ln.strip() else ln for ln in body.splitlines()
        )
    return HEADER + "\n" + body


def verify(name: str, code: str, formal_dir: Path, tmp_dir: Path) -> dict:
    src = code + f"\n\n#print axioms {name}\n"
    lean_file = tmp_dir / f"bakeoff_{name}_{int(time.time())}.lean"
    lean_file.write_text(src, encoding="utf-8")
    t0 = time.time()
    res = subprocess.run(
        ["lake", "env", "lean", str(lean_file)],
        cwd=str(formal_dir), capture_output=True, text=True, timeout=600,
    )
    out = (res.stdout + "\n" + res.stderr).strip()
    axioms: list[str] = []
    if "depends on axioms:" in out:
        part = out.split("depends on axioms:")[1].strip()
        axioms = [a.strip() for a in part.replace("[", "").replace("]", "").split(",") if a.strip()]
    compiled = res.returncode == 0
    clean = compiled and "sorryAx" not in out and set(axioms) <= TRUSTED_AXIOMS
    return {
        "compiled": compiled,
        "axioms": axioms,
        "verified_clean": clean,
        "compile_s": round(time.time() - t0, 1),
        "output_tail": out[-400:],
        "file": str(lean_file),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--formal-dir", default="/home/callensxavier_gmail_com/AutoevolveAI/formal")
    ap.add_argument("--tmp-dir", default="/home/callensxavier_gmail_com/.claude/jobs/4d188676/tmp")
    ap.add_argument("--out", default="/home/callensxavier_gmail_com/.claude/jobs/4d188676/tmp/bakeoff_results.json")
    ap.add_argument("--models", nargs="+", default=[
        "hf.co/unsloth/DeepSeek-Prover-V2-7B-GGUF:Q8_0",
        "hf.co/mradermacher/Goedel-Prover-V2-8B-GGUF:Q6_K",
    ])
    args = ap.parse_args()

    tmp_dir = Path(args.tmp_dir)
    call_log = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/call_logs/prover_bakeoff.jsonl")
    call_log.parent.mkdir(parents=True, exist_ok=True)

    results = {"started": datetime.now(UTC).isoformat(), "runs": []}
    attempts = [(0.0, "greedy"), (0.7, "sample1"), (0.7, "sample2")]  # pass@3
    with gpu_lease(LEASE_HOLDER, "prover bake-off: Ollama generation per theorem", ttl_s=3600, timeout_s=3600):
        for model in args.models:
            for name, stmt in STATEMENTS:
                for temp, tag in attempts:
                    run = {"model": model, "theorem": name, "attempt": tag}
                    print(f"[{model.split('/')[-1]}] {name} ({tag}) ...", flush=True)
                    try:
                        text = generate(model, stmt, call_log, temperature=temp)
                        code = extract_lean(text, stmt)
                        run["verify"] = verify(name, code, Path(args.formal_dir), tmp_dir)
                        print(f"  -> compiled={run['verify']['compiled']} clean={run['verify']['verified_clean']} axioms={run['verify']['axioms']}", flush=True)
                    except Exception as e:
                        run["error"] = f"{type(e).__name__}: {e}"
                        print(f"  -> ERROR {run['error']}", flush=True)
                    results["runs"].append(run)
                    Path(args.out).write_text(json.dumps(results, indent=2))
                    if run.get("verify", {}).get("verified_clean"):
                        break  # first clean proof settles this (model, theorem) pair

    results["finished"] = datetime.now(UTC).isoformat()
    Path(args.out).write_text(json.dumps(results, indent=2))
    clean_by_model: dict[str, int] = {}
    for r in results["runs"]:
        if r.get("verify", {}).get("verified_clean"):
            clean_by_model[r["model"]] = clean_by_model.get(r["model"], 0) + 1
    print("\nVERIFIED-CLEAN COUNTS:", json.dumps(clean_by_model, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
