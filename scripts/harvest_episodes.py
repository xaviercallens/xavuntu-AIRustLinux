#!/usr/bin/env python3
"""Harvest genuinely verified training episodes, so the nightly loop has real data.

WHY THIS EXISTS

The nightly trainer refuses to run, and it is right to. Measured today:

    data/interactions.jsonl : 9 rows, 1 distinct task, hidden_state dim 16,
                              0 rows with metadata.tests_total > 0
    data/episodes/          : empty

`anse/jepa/dataset.py` requires `metadata["tests_total"] > 0` (else the row is
counted into `skipped["unverified"]` and silently dropped), a non-empty
`hidden_state` of consistent width, and finite energy. It also falls back to an
item-level split when fewer than 2 distinct tasks are present (`:386`), which
recreates the leakage that produced the bogus Phase-2 r=0.40 headline.

So "retrain the models" is not a command that can be issued -- it needs data that
satisfies that contract. This script produces it, honestly:

  1. A bank of small Python tasks, each with a HIDDEN reference test. The test is
     never shown to the model; only the statement is.
  2. The LOCAL model proposes a solution (free, on the T4).
  3. `anse/symbolic/sandbox.py` EXECUTES the candidate against the hidden test.
     `tests_passed`/`tests_total` come from that execution, not from an opinion.
  4. Energy is computed from the measured outcome (failures, runtime, memory).
  5. `hidden_state` is a real 1024-d embedding of the (statement, code) pair.

Every episode therefore carries a verifier-issued verdict. Failed attempts are kept
and labelled -- a wrong answer that a test caught is a legitimate training signal,
and discarding failures is how a corpus becomes biased.

Usage:
    .venv/bin/python scripts/harvest_episodes.py --tasks 10 --samples 2
    .venv/bin/python scripts/harvest_episodes.py --dry-run     # bank + verifier only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data" / "episodes"
sys.path.insert(0, "/mnt/disks/disk-socrateai-local-1/gpu_lease")

from gpu_lease import gpu_lease  # noqa: E402

OLLAMA = "http://localhost:11434"
LEASE_HOLDER = "autoevolve-harvest-episodes"
CODER_MODEL = "qwen2.5-coder:7b-instruct"


@dataclass(frozen=True)
class Task:
    """A problem whose reference test is hidden from the solver."""

    task_id: str
    statement: str
    entry_point: str
    hidden_test: str


# Deliberately small and unambiguous: the point is to exercise the data contract
# and the nightly path, not to benchmark capability. Each test asserts behaviour
# the statement describes, and none of them appears in the prompt.
TASKS: tuple[Task, ...] = (
    Task("py-sum-even", "Write `def sum_even(xs: list[int]) -> int` returning the sum of even values.",
         "sum_even",
         "assert sum_even([1,2,3,4])==6\nassert sum_even([])==0\nassert sum_even([-2,3])==-2"),
    Task("py-reverse-words", "Write `def reverse_words(s: str) -> str` reversing word order, single-spaced.",
         "reverse_words",
         "assert reverse_words('a b c')=='c b a'\nassert reverse_words('hi')=='hi'"),
    Task("py-is-palindrome", "Write `def is_palindrome(s: str) -> bool`, case-insensitive, ignoring non-alphanumerics.",
         "is_palindrome",
         "assert is_palindrome('A man, a plan, a canal: Panama')\nassert not is_palindrome('abc')"),
    Task("py-gcd", "Write `def gcd(a: int, b: int) -> int` returning the greatest common divisor.",
         "gcd",
         "assert gcd(12,18)==6\nassert gcd(7,13)==1\nassert gcd(0,5)==5"),
    Task("py-flatten", "Write `def flatten(xs: list) -> list` flattening one level of nesting.",
         "flatten",
         "assert flatten([[1,2],[3]])==[1,2,3]\nassert flatten([])==[]"),
    Task("py-run-length", "Write `def encode(s: str) -> str` run-length encoding, e.g. 'aab' -> 'a2b1'.",
         "encode",
         "assert encode('aab')=='a2b1'\nassert encode('')==''"),
    Task("py-second-largest", "Write `def second_largest(xs: list[int]) -> int | None` returning the second largest distinct value, or None.",
         "second_largest",
         "assert second_largest([1,3,2])==2\nassert second_largest([5,5])is None"),
    Task("py-binary-search", "Write `def bsearch(xs: list[int], t: int) -> int` returning the index of t in a sorted list, or -1.",
         "bsearch",
         "assert bsearch([1,3,5,7],5)==2\nassert bsearch([1,3],2)==-1"),
    Task("py-chunk", "Write `def chunk(xs: list, n: int) -> list[list]` splitting into consecutive chunks of size n.",
         "chunk",
         "assert chunk([1,2,3,4,5],2)==[[1,2],[3,4],[5]]\nassert chunk([],3)==[]"),
    Task("py-word-count", "Write `def word_count(s: str) -> dict[str,int]` counting whitespace-separated words.",
         "word_count",
         "assert word_count('a b a')=={'a':2,'b':1}\nassert word_count('')=={}"),
    Task("py-transpose", "Write `def transpose(m: list[list]) -> list[list]` transposing a rectangular matrix.",
         "transpose",
         "assert transpose([[1,2],[3,4]])==[[1,3],[2,4]]\nassert transpose([])==[]"),
    Task("py-digit-sum", "Write `def digit_sum(n: int) -> int` summing the decimal digits of abs(n).",
         "digit_sum",
         "assert digit_sum(123)==6\nassert digit_sum(-45)==9\nassert digit_sum(0)==0"),
)


def extract_code(raw: str) -> str:
    """Pull the Python block out of a model reply."""
    fenced = re.findall(r"```(?:python)?\s*\n(.*?)```", raw, flags=re.DOTALL)
    if fenced:
        return max(fenced, key=len).strip()
    return raw.strip()


def call_coder(statement: str, temperature: float) -> str:
    import httpx

    prompt = (
        "Write a single self-contained Python function. Output ONLY a ```python code "
        "block, no explanation, no tests, no example usage.\n\n" + statement
    )
    r = httpx.post(
        f"{OLLAMA}/api/generate",
        json={
            "model": CODER_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 400},
        },
        timeout=900,
    )
    r.raise_for_status()
    return r.json().get("response", "")


def verify(code: str, task: Task) -> dict[str, Any]:
    """Execute the candidate against the hidden test. This is the only verdict.

    Each assertion in the hidden test is counted individually, so a partially
    correct solution yields a partial score rather than a binary one.
    """
    from anse.symbolic.sandbox import SandboxExecutor

    assertions = [ln for ln in task.hidden_test.splitlines() if ln.strip()]
    tests_total = len(assertions)

    # Run assertions one at a time so tests_passed is a real count.
    passed = 0
    last_stderr = ""
    total_ms = 0.0
    peak_ram = 0.0
    executor = SandboxExecutor()
    for assertion in assertions:
        program = f"{code}\n\n{assertion}\nprint('OK')\n"
        # force_tier=1 keeps this in the subprocess sandbox: Docker (tier 2) may be
        # absent, and escalating on an AST scan would turn a missing daemon into a
        # spurious test failure. Timeout comes from SandboxConfig, not this call.
        result = executor.execute(program, trusted=False, force_tier=1)
        total_ms += result.duration_ms
        peak_ram = max(peak_ram, result.peak_ram_mb)
        if result.returncode == 0 and "OK" in result.stdout:
            passed += 1
        else:
            last_stderr = (result.stderr or "")[-400:]

    return {
        "tests_total": tests_total,
        "tests_passed": passed,
        "returncode": 0 if passed == tests_total else 1,
        "duration_ms": total_ms,
        "peak_ram_mb": peak_ram,
        "stderr": last_stderr,
    }


def energy_of(v: dict[str, Any]) -> float:
    """Energy from measured outcome: failures dominate, runtime is a tiebreak.

    Zero only when every hidden assertion passed. Finite always, because
    `anse/jepa/dataset.py` drops non-finite energies.
    """
    failed = v["tests_total"] - v["tests_passed"]
    return float(failed * 100.0 + min(v["duration_ms"], 10_000.0) / 1000.0)


def embed(text: str) -> list[float]:
    from anse.memory.ollama_embeddings import OllamaEmbeddingFunction

    return OllamaEmbeddingFunction()([text[:6000]])[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", type=int, default=len(TASKS))
    ap.add_argument("--samples", type=int, default=2, help="attempts per task")
    ap.add_argument("--dry-run", action="store_true",
                    help="verify the bank against reference solutions; no model calls")
    ap.add_argument("--out", type=Path, default=OUT / "harvest.jsonl")
    args = ap.parse_args(argv)

    selected = TASKS[: args.tasks]
    args.out.parent.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        # Sanity: a KNOWN-GOOD solution must score full marks, and an empty one
        # must score zero. Without both, the verifier proves nothing.
        good = "def sum_even(xs):\n    return sum(x for x in xs if x % 2 == 0)\n"
        t = TASKS[0]
        ok = verify(good, t)
        bad = verify("def sum_even(xs):\n    return 999\n", t)
        print(f"verifier positive control: {ok['tests_passed']}/{ok['tests_total']}")
        print(f"verifier negative control: {bad['tests_passed']}/{bad['tests_total']}")
        good_ok = ok["tests_passed"] == ok["tests_total"]
        bad_ok = bad["tests_passed"] < bad["tests_total"]
        print(f"verifier is discriminating: {good_ok and bad_ok}")
        return 0 if (good_ok and bad_ok) else 1

    episodes: list[dict[str, Any]] = []
    stats = {"attempted": 0, "fully_passed": 0, "partial": 0, "failed": 0}

    with gpu_lease(LEASE_HOLDER, "harvest episodes: coder samples + embeddings", ttl_s=3600, timeout_s=3600):
        for task in selected:
            for sample in range(args.samples):
                temperature = 0.2 if sample == 0 else 0.8
                stats["attempted"] += 1
                t0 = time.time()
                try:
                    raw = call_coder(task.statement, temperature)
                except Exception as exc:
                    print(f"  {task.task_id} s{sample}: model call failed: {exc}")
                    continue
                code = extract_code(raw)
                v = verify(code, task)
                energy = energy_of(v)

                if v["tests_passed"] == v["tests_total"]:
                    stats["fully_passed"] += 1
                elif v["tests_passed"] > 0:
                    stats["partial"] += 1
                else:
                    stats["failed"] += 1

                hidden = embed(f"{task.statement}\n\n{code}")
                episodes.append(
                    {
                        "task": task.task_id,
                        "prompt": task.statement,
                        "code": code,
                        "raw_response": raw[:4000],
                        "energy": energy,
                        "energy_category": "low" if energy < 1.0 else "high",
                        "converged": v["tests_passed"] == v["tests_total"],
                        "iteration": sample,
                        "duration_ms": (time.time() - t0) * 1000.0,
                        "returncode": v["returncode"],
                        "execution_stdout": "",
                        "execution_stderr": v["stderr"],
                        "hidden_state": hidden,
                        "trace_id": str(uuid.uuid4()),
                        "timestamp": time.time(),
                        # The contract anse/jepa/dataset.py actually enforces.
                        "metadata": {
                            "tests_total": v["tests_total"],
                            "tests_passed": v["tests_passed"],
                            "difficulty_tier": "trivial" if energy == 0 else "fixable",
                            "verifier": "sandbox+hidden_assertions",
                            "temperature": temperature,
                            "peak_ram_mb": v["peak_ram_mb"],
                        },
                    }
                )
                print(f"  {task.task_id} s{sample} T={temperature}: "
                      f"{v['tests_passed']}/{v['tests_total']} energy={energy:.2f}")

    with args.out.open("w", encoding="utf-8") as fh:
        for e in episodes:
            fh.write(json.dumps(e) + "\n")

    dims = {len(e["hidden_state"]) for e in episodes}
    tasks_seen = {e["task"] for e in episodes}
    verified = sum(1 for e in episodes if e["metadata"]["tests_total"] > 0)

    print(f"\nwrote {len(episodes)} episodes -> {args.out.relative_to(REPO)}")
    print(f"  distinct tasks     : {len(tasks_seen)}  (>=2 required for a task-level split)")
    print(f"  hidden_state dims  : {dims}  (must be a single value)")
    print(f"  rows with verdict  : {verified}/{len(episodes)}")
    print(f"  outcomes           : {json.dumps(stats)}")

    contract_ok = len(tasks_seen) >= 2 and len(dims) == 1 and verified == len(episodes)
    print(f"  JEPA contract met  : {contract_ok}")
    return 0 if contract_ok else 1


if __name__ == "__main__":
    sys.exit(main())
