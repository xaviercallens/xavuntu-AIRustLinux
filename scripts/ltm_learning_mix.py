#!/usr/bin/env python3
"""Build ANSE's next training mix from long-term memory, with dilution control.

Sources
  verified   data/episodes/harvest.jsonl        (episodes with real verdicts)
  new        call_logs/*.jsonl                  (every logged LLM call; prover
             bake-off rows carry a kernel verdict, plain calls carry none)
  new        results/redis_ltm_lora_dataset.jsonl (rows distilled from coding-agent
             transcripts; origin='transcript', see below)

Dilution: at most ``--dilution`` of the final mix may come from the *new*
pool. The ratio guards against catastrophic forgetting: verified prior
episodes anchor the distribution, fresh (partly unverified) signal is folded
in gradually. If the verified pool is too small to honour the ratio, this
script exits BLOCKED — it never silently inverts the mix.

Origin policy (card N-9, anse/v2/origin_policy.py): every row is tagged with an
``origin``. Rows from transcripts (``transcript``, ``claude_code``, ``antigravity``)
are refused until a human writes docs/v2/gates/N8.md; rows without an origin
are refused outright. The report lists how many rows were refused and why.

Output rows carry provenance: {source, origin, verified, verdict, sha}. The
night trainer (scripts/night_training_workflow.py DATA step) can consume the file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from anse.v2.origin_policy import NO_TRAIN_ORIGINS, partition  # noqa: E402

CALL_LOGS = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/call_logs")
EPISODES = REPO / "data" / "episodes" / "harvest.jsonl"
TRANSCRIPT_ROWS = REPO / "results" / "redis_ltm_lora_dataset.jsonl"
GATE_FILE = REPO / "docs" / "v2" / "gates" / "N8.md"
ORIGIN_TRANSCRIPT = "transcript"


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def _label(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def load_verified(path: Path = EPISODES) -> list[dict]:
    """Sandbox-verified episodes. A row may carry its own origin; the harvest file's rows
    come from harvest_episodes.py's sandbox verifier, so that is the default."""
    rows = []
    if path.exists():
        for line in path.open():
            if not line.strip():
                continue
            ep = json.loads(line)
            rows.append({
                "source": _label(path),
                "origin": ep.get("origin") or "sandbox",
                "verified": True,
                "verdict": bool(ep.get("converged")),
                "prompt": ep.get("prompt", ""),
                "completion": ep.get("code", ""),
                "sha": sha(line),
            })
    return rows


def load_new(call_logs: Path = CALL_LOGS) -> list[dict]:
    """Logged LLM calls made by this repo's own pipelines (APIExtractor JSONL)."""
    rows = []
    for f in sorted(call_logs.glob("*.jsonl")):
        for line in f.open():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            msgs = rec.get("input", {}).get("messages") or []
            prompt = " ".join(m.get("content", "") for m in msgs) or rec.get("input", {}).get("prompt", "")
            rows.append({
                "source": f"call_logs/{f.name}",
                "origin": rec.get("origin") or "call_log",
                "verified": False,
                "verdict": None,  # a later join with bakeoff results may set this
                "prompt": prompt,
                "completion": rec.get("output", {}).get("text", ""),
                "sha": sha(line),
            })
    return rows


def load_transcript(path: Path = TRANSCRIPT_ROWS) -> list[dict]:
    """Rows distilled from coding-agent transcripts (execute_local_redis_ltm_lora.py writes
    them from the Redis/transcript_ltm store). Always tagged origin='transcript', whatever
    the row says about itself: provenance is decided by where the row came from."""
    rows = []
    if path.exists():
        for line in path.open():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append({
                "source": _label(path),
                "origin": ORIGIN_TRANSCRIPT,
                "verified": False,
                "verdict": None,
                "prompt": rec.get("prompt", ""),
                "completion": rec.get("response") or rec.get("completion", ""),
                "sha": sha(line),
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dilution", type=float, default=0.3,
                    help="max fraction of the mix drawn from the NEW pool (default 0.3)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=REPO / "data" / "training" / "ltm_mix.jsonl")
    ap.add_argument("--episodes", type=Path, default=EPISODES)
    ap.add_argument("--call-logs", type=Path, default=CALL_LOGS)
    ap.add_argument("--transcript", type=Path, default=TRANSCRIPT_ROWS)
    ap.add_argument("--gate-file", type=Path, default=GATE_FILE,
                    help="the human-written N-8 gate; transcript rows are refused until it exists")
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    args = ap.parse_args()

    if not 0.0 <= args.dilution <= 0.5:
        print(f"BLOCKED: dilution {args.dilution} outside [0, 0.5]; the verified pool must dominate")
        return 1

    verified, refused_verified = partition(load_verified(args.episodes), args.gate_file)
    new_pool = load_new(args.call_logs) + load_transcript(args.transcript)
    new, refused_new = partition(new_pool, args.gate_file)
    by_reason: dict[str, int] = {}
    for reasons in (refused_verified, refused_new):
        for reason, n in reasons.items():
            by_reason[reason] = by_reason.get(reason, 0) + n
    refused = {
        "total": sum(by_reason.values()),
        "by_reason": dict(sorted(by_reason.items())),
        "by_pool": {"verified": sum(refused_verified.values()), "new": sum(refused_new.values())},
        "gate_file": str(args.gate_file),
        "gate_present": args.gate_file.exists(),
        "gated_origins": sorted(NO_TRAIN_ORIGINS),
    }
    rng = random.Random(args.seed)

    if not verified:
        print("BLOCKED: no verified episodes on disk; refusing to train on unverified calls alone")
        print(json.dumps({"refused": refused}, indent=2))
        return 1

    # Mix size is anchored by the verified pool: it always enters whole.
    max_new = int(len(verified) * args.dilution / max(1e-9, 1.0 - args.dilution))
    take_new = min(max_new, len(new))
    mix = verified + rng.sample(new, take_new)
    rng.shuffle(mix)

    if not args.dry_run:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as f:
            for row in mix:
                f.write(json.dumps(row) + "\n")

    frac = take_new / len(mix) if mix else 0.0
    print(json.dumps({
        "written": None if args.dry_run else str(args.out),
        "rows": len(mix),
        "verified_rows": len(verified),
        "new_rows_taken": take_new,
        "new_pool_available": len(new),
        "effective_dilution": round(frac, 3),
        "dilution_cap": args.dilution,
        "refused": refused,
        "at": datetime.now(UTC).isoformat(),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
