#!/usr/bin/env python3
"""
Run 100 Code Functional Tests (Issue vs Positive) and Record Sessions for RL Post-Training.

Executes 100 distinct functional test scenarios across 20 algorithmic categories.
For each scenario:
  - Positive Test: clean, verifiable implementation passing AST AntiStubGuard and all assertions (E = 0).
  - Issue Test: defective implementation exhibiting AST stubs, edge-case bugs, type errors, or wrong logic (E >> 0).
Records execution sessions, physical metrics (latency, RAM, Energy), and attestation verdicts into RedisBus.
Exports 100 aligned preference pairs (prompt, chosen, rejected) for DPO / RL post-training.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from pathlib import Path

import yaml

# Ensure repo root and antigravity_harness are importable
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
harness_dir = REPO_ROOT / "antigravity-harness"
if str(harness_dir) not in sys.path:
    sys.path.insert(0, str(harness_dir))

from anse.config import get_config  # noqa: E402
from anse.symbolic.evaluator import EnergyEvaluator  # noqa: E402
from anse.symbolic.hidden_tests import parse_report  # noqa: E402
from anse.symbolic.sandbox import SandboxExecutor  # noqa: E402
from anse.symbolic.trusted_driver import build_driver, trusted_payload  # noqa: E402
from antigravity_harness.core.anti_stub_guard import AntiStubGuard  # noqa: E402
from antigravity_harness.rl_pipeline.dpo_dataset_builder import DPODatasetBuilder  # noqa: E402
from antigravity_harness.rl_pipeline.trace_extractor import ExtractedSession  # noqa: E402
from antigravity_harness.storage.redis_bus import RedisBus, TraceRecord  # noqa: E402


def generate_issue_code(task_name: str, ref_code: str, scenario_idx: int) -> tuple[str, str]:
    """
    Generate an issue candidate for the given task and scenario variant.
    Returns (code, failure_reason).
    """
    if scenario_idx == 0:
        # Scenario 0: Hollow AST Stub (Anti-stub violation)
        if task_name.startswith("validate_") or task_name.startswith("is_"):
            return (
                "def " + task_name + "(*args, **kwargs):\n    pass  # TODO: implement\n",
                "Hollow stub: pass statement",
            )
        return "def " + task_name + "(*args, **kwargs):\n    ...\n", "Hollow stub: ellipsis (...)"

    elif scenario_idx == 1:
        # Scenario 1: Boundary / Empty Edge Case Bug
        if task_name == "rotate_list":
            return (
                "def rotate_list(lst, k):\n    return lst[-k:] + lst[:-k]\n",
                "Fails on empty list / division by zero",
            )
        elif task_name == "chunk_list":
            return (
                "def chunk_list(lst, size):\n    return [lst[i:i + size] for i in range(0, len(lst), size)]\n",
                "Fails to validate size <= 0",
            )
        elif task_name == "rotate_string":
            return (
                "def rotate_string(s, k):\n    return s[k:] + s[:k]\n",
                "Fails on k > len(s) or empty string",
            )
        elif task_name == "sliding_windows":
            return (
                "def sliding_windows(lst, size):\n    return [lst[i:i+size] for i in range(len(lst) - size + 1)]\n",
                "Fails on size <= 0 or size > len",
            )
        elif task_name == "validate_ipv4":
            return (
                "def validate_ipv4(s):\n    parts = s.split('.')\n    return len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts)\n",
                "Fails on non-digit or leading zero octets",
            )
        elif task_name == "factorial":
            return (
                "def factorial(n):\n    return 1 if n <= 1 else n * factorial(n - 1)\n",
                "Fails on negative n (infinite recursion/ValueError)",
            )
        elif task_name == "median":
            return (
                "def median(numbers):\n    s = sorted(numbers)\n    return float(s[len(s)//2])\n",
                "Fails on even length list (takes right middle instead of average)",
            )
        elif task_name == "nth_fibonacci":
            return (
                "def nth_fibonacci(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n",
                "Off-by-one error on Fibonacci base terms",
            )
        elif task_name == "second_largest":
            return (
                "def second_largest(numbers):\n    s = sorted(numbers)\n    return s[-2]\n",
                "Fails on duplicates or arrays with < 2 unique elements",
            )
        else:
            return (
                f"def {task_name}(*args):\n    if not args[0]: raise IndexError('empty')\n    return {ref_code.splitlines()[-1].strip()}\n",
                "Uncaught boundary edge case exception",
            )

    elif scenario_idx == 2:
        # Scenario 2: Type / Runtime Error on Malformed Input
        if task_name == "parse_duration":
            return (
                "def parse_duration(s):\n    return int(s[:-1]) * 60\n",
                "Fails on units other than 'm' or invalid duration format",
            )
        elif task_name == "parse_size":
            return (
                "def parse_size(s):\n    return int(s[:-2]) * 1024\n",
                "Fails on case-sensitivity, unit multipliers, or bad format",
            )
        elif task_name == "validate_hex_color":
            return (
                "def validate_hex_color(s):\n    return s.startswith('#') and len(s) in (4, 7)\n",
                "Fails on non-hexadecimal characters",
            )
        elif task_name == "camel_to_snake":
            return (
                "def camel_to_snake(s):\n    return s.lower()\n",
                "Wrong conversion: does not insert underscores before capitals",
            )
        elif task_name == "snake_to_camel":
            return (
                "def snake_to_camel(s):\n    return s.replace('_', '').title()\n",
                "Wrong casing: uppercases first character or collapses words",
            )
        elif task_name == "run_length_encode":
            return (
                "def run_length_encode(s):\n    return [(c, s.count(c)) for c in set(s)]\n",
                "Wrong algorithm: counts global occurrences instead of consecutive runs",
            )
        elif task_name == "run_length_decode":
            return (
                "def run_length_decode(runs):\n    return ''.join(c * n for c, n in runs)\n",
                "Fails on reversed tuple order or invalid counts",
            )
        elif task_name == "merge_intervals":
            return (
                "def merge_intervals(intervals):\n    return intervals\n",
                "Returns unmerged intervals directly",
            )
        elif task_name == "compress_ranges":
            return (
                "def compress_ranges(numbers):\n    return [f'{n}' for n in numbers]\n",
                "Fails to compress consecutive ranges",
            )
        elif task_name == "expand_ranges":
            return (
                "def expand_ranges(s):\n    return [int(x) for x in s.split(',')]\n",
                "Fails on hyphenated ranges",
            )
        elif task_name == "missing_ranges":
            return (
                "def missing_ranges(numbers, start, end):\n    return []\n",
                "Always returns empty missing ranges",
            )
        else:
            return (
                f"def {task_name}(*args):\n    raise TypeError('Unsupported argument type')\n",
                "Runtime TypeError",
            )

    elif scenario_idx == 3:
        # Scenario 3: Logic / Inversion Bug
        if task_name == "validate_ipv4":
            return (
                "def validate_ipv4(s):\n    return not ('.' in s)\n",
                "Inverted logic: checks absence of dots",
            )
        elif task_name == "validate_hex_color":
            return "def validate_hex_color(s):\n    return False\n", "Always returns False"
        elif task_name == "rotate_list":
            return (
                "def rotate_list(lst, k):\n    if not lst: return []\n    k %= len(lst)\n    return lst[k:] + lst[:k]\n",
                "Rotates left instead of right",
            )
        elif task_name == "rotate_string":
            return (
                "def rotate_string(s, k):\n    if not s: return ''\n    k %= len(s)\n    return s[-k:] + s[:-k]\n",
                "Rotates right instead of left",
            )
        elif task_name == "factorial":
            return (
                "def factorial(n):\n    if n < 0: raise ValueError('negative')\n    res = 1\n    for i in range(1, n): res *= i\n    return res\n",
                "Off-by-one: multiplies up to n-1 instead of n",
            )
        elif task_name == "median":
            return (
                "def median(numbers):\n    return float(sum(numbers) / len(numbers))\n",
                "Calculates mean instead of median",
            )
        else:
            return f"def {task_name}(*args):\n    return None\n", "Trivial None return"

    else:
        # Scenario 4: Cheating / Mock / Sleep Simulation
        return (
            f"def {task_name}(*args, **kwargs):\n    mock_result = None\n    return mock_result  # simulated mock return\n",
            "Detected synthetic mock variable",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run 100 Code Functional Tests & Record RL Session."
    )
    parser.add_argument(
        "--num-tests", type=int, default=100, help="Total number of functional tests (default: 100)"
    )
    parser.add_argument(
        "--output-dir", type=str, default="results/rl_nightly", help="Output directory"
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("═══════════════════════════════════════════════════════════════════════")
    print("🚀 INITIATING 100 CODE FUNCTIONAL TESTS (POSITIVE & ISSUE SCENARIOS)")
    print(f"   Target:      {args.num_tests} total tests across 20 algorithmic suites")
    print(f"   Output dir:  {out_dir}")
    print("   Physics:     Sandbox execution, AST AntiStubGuard, E = w_t*ms + w_m*RAM")
    print("═══════════════════════════════════════════════════════════════════════\n")

    # 1. Load tasks suite
    yaml_path = REPO_ROOT / "tasks" / "phase1_evolution.yaml"
    if not yaml_path.exists():
        print(f"❌ Tasks file not found at {yaml_path}")
        sys.exit(1)

    suite = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))["tasks"]
    num_tasks = len(suite)

    # 2. Initialize execution sandbox and guards
    cfg = get_config()
    sandbox = SandboxExecutor(config=cfg.sandbox)
    guard = AntiStubGuard()
    evaluator = EnergyEvaluator()
    bus = RedisBus(use_mock=True)

    sessions: list[ExtractedSession] = []
    session_records_path = out_dir / "sessions.jsonl"
    session_file = session_records_path.open("w", encoding="utf-8")

    positive_passed = 0
    issue_caught = 0

    print(
        "Progress | Task Name (Scenario)                   | POS Energy | ISSUE Energy | Delta E | AST Verdict"
    )
    print(
        "---------+----------------------------------------+------------+--------------+---------+------------"
    )

    test_idx = 0
    scenarios_per_task = max(1, (args.num_tests + num_tasks - 1) // num_tasks)

    for scen_idx in range(scenarios_per_task):
        if test_idx >= args.num_tests:
            break
        for task_def in suite:
            if test_idx >= args.num_tests:
                break
            test_idx += 1

            task_name = task_def["name"]
            prompt = task_def["task"]
            ref_code = task_def["reference"]
            hidden_tests = task_def["tests"]

            subtask_id = f"subtask_{task_name}_{scen_idx + 1}"
            session = ExtractedSession(subtask_id=subtask_id, prompt=prompt)

            # ── [A] POSITIVE TEST CANDIDATE ──────────────────────────────────
            pos_audit = guard.audit_code(ref_code)
            pos_nonce = "ANSE-" + secrets.token_hex(8)
            pos_driver = build_driver(pos_nonce, ref_code, budget_seconds=2.0, tests=hidden_tests)
            pos_exec = sandbox.execute(pos_driver, force_tier=1)
            pos_payload = trusted_payload(pos_exec, pos_nonce)
            pos_report = parse_report(pos_payload, pos_nonce) if pos_payload is not None else None
            pos_exec.stdout = ""
            pos_energy = evaluator.evaluate_hidden_tests(pos_exec, pos_report).score

            pos_verdict = "PASSED" if (pos_audit.is_clean and pos_energy == 0.0) else "FAILED"
            if pos_verdict == "PASSED":
                positive_passed += 1

            pos_trace = TraceRecord(
                trace_id=f"pos_{subtask_id}",
                subtask_id=subtask_id,
                prompt=prompt,
                completion=ref_code,
                verdict=pos_verdict,
                energy=pos_energy,
                reasons=[] if pos_audit.is_clean else [v.message for v in pos_audit.violations],
            )
            bus.record_trace(pos_trace)
            session.traces.append(pos_trace)

            # ── [B] ISSUE TEST CANDIDATE ─────────────────────────────────────
            issue_code, expected_reason = generate_issue_code(task_name, ref_code, scen_idx)
            issue_audit = guard.audit_code(issue_code)

            if not issue_audit.is_clean:
                # Anti-stub violation triggers maximum pain directly
                issue_energy = 1000000.0
                issue_verdict = "FAILED"
                issue_reasons = [v.message for v in issue_audit.violations]
                issue_caught += 1
            else:
                # Runs through sandbox to detect test failure
                issue_nonce = "ANSE-" + secrets.token_hex(8)
                issue_driver = build_driver(
                    issue_nonce, issue_code, budget_seconds=2.0, tests=hidden_tests
                )
                issue_exec = sandbox.execute(issue_driver, force_tier=1)
                issue_payload = trusted_payload(issue_exec, issue_nonce)
                issue_report = (
                    parse_report(issue_payload, issue_nonce) if issue_payload is not None else None
                )
                issue_exec.stdout = ""
                issue_energy = evaluator.evaluate_hidden_tests(issue_exec, issue_report).score
                issue_verdict = "FAILED" if issue_energy > 0.0 else "PASSED"
                issue_reasons = [expected_reason]
                if issue_verdict == "FAILED":
                    issue_caught += 1

            issue_trace = TraceRecord(
                trace_id=f"issue_{subtask_id}",
                subtask_id=subtask_id,
                prompt=prompt,
                completion=issue_code,
                verdict=issue_verdict,
                energy=issue_energy,
                reasons=issue_reasons,
            )
            bus.record_trace(issue_trace)
            session.traces.append(issue_trace)

            sessions.append(session)

            # Persist session to JSONL
            session_dict = {
                "subtask_id": subtask_id,
                "task_name": task_name,
                "scenario": scen_idx,
                "prompt": prompt,
                "positive": {
                    "energy": pos_energy,
                    "verdict": pos_verdict,
                    "clean_ast": pos_audit.is_clean,
                },
                "issue": {
                    "energy": issue_energy,
                    "verdict": issue_verdict,
                    "reasons": issue_reasons,
                },
                "delta_energy": pos_energy - issue_energy,
            }
            session_file.write(json.dumps(session_dict) + "\n")
            session_file.flush()

            delta_e = pos_energy - issue_energy
            ast_tag = "CLEAN" if pos_audit.is_clean else "DIRTY"
            print(
                f"[{test_idx:03d}/{args.num_tests:03d}] {task_name[:20]:<20} (scen #{scen_idx}) | E={pos_energy:5.1f}   | E={issue_energy:8.1f}   | {delta_e:7.1f} | POS:{ast_tag}"
            )

    session_file.close()

    # 3. Build DPO preference dataset
    print("\n═══════════════════════════════════════════════════════════════════════")
    print("📦 BUILDING DPO PREFERENCE DATASET FROM RECORDED SESSIONS")
    builder = DPODatasetBuilder(guard=guard)
    pairs = builder.build_pairs_from_sessions(sessions)

    dpo_path = out_dir / "dpo_preference_pairs.jsonl"
    builder.export_to_jsonl(pairs, dpo_path)

    # Format TRL chat split
    train_pairs, val_pairs = builder.split_train_val(pairs, val_ratio=0.1)
    train_path = out_dir / "dpo_train.jsonl"
    val_path = out_dir / "dpo_val.jsonl"
    builder.export_to_jsonl(train_pairs, train_path)
    builder.export_to_jsonl(val_pairs, val_path)

    summary = {
        "total_tests": test_idx,
        "positive_passed": positive_passed,
        "positive_pass_rate": positive_passed / max(1, test_idx),
        "issue_caught": issue_caught,
        "issue_detection_rate": issue_caught / max(1, test_idx),
        "total_preference_pairs": len(pairs),
        "train_pairs": len(train_pairs),
        "val_pairs": len(val_pairs),
        "dpo_file": str(dpo_path),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"✅ Successfully completed {test_idx} functional tests!")
    print(
        f"   Positive Pass Rate:    {positive_passed}/{test_idx} ({100 * positive_passed / test_idx:.1f}%)"
    )
    print(
        f"   Issue Detection Rate:  {issue_caught}/{test_idx} ({100 * issue_caught / test_idx:.1f}%)"
    )
    print(f"   Preference Pairs:      {len(pairs)} pairs exported to {dpo_path}")
    print(f"   Train/Val Split:       {len(train_pairs)} train, {len(val_pairs)} val")
    print("═══════════════════════════════════════════════════════════════════════\n")


if __name__ == "__main__":
    main()
