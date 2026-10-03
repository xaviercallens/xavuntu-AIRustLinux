#!/usr/bin/env python3
"""
Post-implementation training pass. Runs after the card runner each night.

Retrains one model at a time, in dependency order, and records what actually
happened to each. The T4 holds 15,360 MiB against ~27 GB of pulled weights, so
sequential is not a style choice -- two of these cannot be resident together.

WHAT THIS WILL NOT DO:

  * It will not report a model as trained when it was not. Every stage returns
    one of TRAINED / SKIPPED / FAILED with a reason, and SKIPPED is a normal,
    frequent outcome tonight (no GPU driver -- card P0-3 is human-tier and
    open). A skip is a result; a fabricated loss curve is not.
  * It will not promote anything into service. Candidates are written with
    their measured metrics and a promote/reject decision; activation is card
    P4-5's gate. The lake's flagship Qwen artifact is the output of an 8-step
    run whose loss ROSE 3.532 -> 3.692 while labelling itself SUCCESS -- which
    is precisely why a label never promotes a checkpoint here.
  * It will not invent a metric. If an evaluation cannot run, the stage is
    SKIPPED, not scored.

Ordering is deliberate: the cheapest model that can actually train tonight goes
first, so a night with no GPU still produces a real result.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger("post_train")

REPO_ROOT = Path(__file__).resolve().parent.parent
DISK2 = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI")
STAGE = DISK2 / "datalake"
CANDIDATES = DISK2 / "candidates"
RUNS = DISK2 / "training_runs"

T4_TOTAL_MIB = 15360  # measured, not the marketing 16 GB


class Status(StrEnum):
    TRAINED = "TRAINED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


@dataclass
class StageResult:
    model: str
    status: Status
    reason: str
    metrics: dict[str, Any] = field(default_factory=dict)
    artifact: str | None = None
    duration_s: float = 0.0
    promoted: bool = False
    promote_reason: str = "not evaluated"
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ------------------------------------------------------------------ capability


@dataclass(frozen=True)
class Capability:
    gpu: bool
    gpu_name: str | None
    vram_free_mib: int | None
    detail: str


def probe_capability() -> Capability:
    """Live probe. Never assumes, never caches, never trusts a hint."""
    if shutil.which("nvidia-smi") is None:
        return Capability(False, None, None, "nvidia-smi not on PATH")
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return Capability(False, None, None, f"nvidia-smi failed: {exc}")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        return Capability(
            False, None, None, detail[0] if detail else f"exit {proc.returncode}"
        )
    first = proc.stdout.strip().splitlines()[0]
    name, _, free = first.partition(",")
    try:
        free_mib = int(free.strip())
    except ValueError:
        free_mib = 0
    return Capability(True, name.strip(), free_mib, "ok")


# ----------------------------------------------------------------- the stages


def stage_jepa(cap: Capability, dry_run: bool) -> StageResult:
    """JEPA world model.

    First because it is the only genuine trainer here that runs on CPU
    (anse/jepa/trainer.py has a real AdamW loop and loss.backward()), and it
    has never had data. The lake's LTM corpus is now staged on disk 2, so this
    is the one stage that can produce a real result on a night with no GPU.
    """
    corpus = STAGE / "data/redis/redis_ltm_lora_dataset.jsonl"
    if not corpus.exists():
        return StageResult(
            "jepa",
            Status.SKIPPED,
            f"no corpus at {corpus}; run bootstrap_from_datalake.py --only data",
        )
    rows = sum(1 for _ in corpus.open())
    if rows < 50:
        return StageResult(
            "jepa",
            Status.SKIPPED,
            f"corpus has {rows} rows; too few to train on honestly",
            metrics={"rows": rows},
        )
    if dry_run:
        return StageResult(
            "jepa", Status.SKIPPED, "dry-run", metrics={"rows": rows, "device": "cpu"}
        )

    # The real trainer needs the harvester's interactions.jsonl schema, which
    # card P4-1 fixes. Until that lands, refuse rather than feed it a corpus
    # whose fields it will silently misread.
    if not (REPO_ROOT / "data/interactions.jsonl").exists():
        return StageResult(
            "jepa",
            Status.SKIPPED,
            "data/interactions.jsonl absent; card P4-1 must land before JEPA "
            "trains, or the trainer silently zero-pads a mismatched schema",
            metrics={"corpus_rows": rows},
        )
    return StageResult(
        "jepa", Status.SKIPPED, "reachable but not yet wired; see card P4-1"
    )


def stage_energy_surrogate(cap: Capability, dry_run: bool) -> StageResult:
    """Energy surrogate -- shadow mode only.

    The roadmap gates this at AUROC >= 0.80 on a task-split, de-duplicated
    evaluation. The Phase-2 headline of r=0.40 was leakage: 49/120 duplicate
    rows across a random split. Never score this on a row-level split, and
    never promote it on MAE against a zero-inflated target.
    """
    return StageResult(
        "energy_surrogate",
        Status.SKIPPED,
        "shadow mode: requires a task-split de-duplicated eval and AUROC >= 0.80 "
        "before any promotion (card P4-8)",
    )


def stage_qlora(cap: Capability, dry_run: bool) -> StageResult:
    """QLoRA on the target base. Needs the GPU that is currently unreachable."""
    if not cap.gpu:
        return StageResult(
            "qlora_7b",
            Status.SKIPPED,
            f"no usable GPU ({cap.detail}); card P0-3 installs the driver. "
            "Refusing to fall back to CPU or to a dry-run that records a "
            "deployment -- that is the defect in daily_trainer_daemon.",
        )
    need = 11_000  # 7B at 4-bit + optimizer + activations, order of magnitude
    if cap.vram_free_mib is not None and cap.vram_free_mib < need:
        return StageResult(
            "qlora_7b",
            Status.SKIPPED,
            f"only {cap.vram_free_mib} MiB free of {T4_TOTAL_MIB}; need ~{need}. "
            "Unload Ollama models first (ollama stop) -- keep_alive holds ~8 GiB.",
            metrics={"vram_free_mib": cap.vram_free_mib},
        )
    if dry_run:
        return StageResult("qlora_7b", Status.SKIPPED, "dry-run")

    # Delegate to the step-by-step engine (ARTIFACT -> DATA -> FIT -> EVAL ->
    # GATE) rather than reimplementing the DATA/FIT logic here. One training
    # engine, not two that can drift apart.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from night_training_workflow import Outcome, Step, run_model

    journal = run_model("qwen_lora", smoke=False)
    reached = journal.last_ok
    if reached in (Step.FIT, Step.EVAL, Step.GATE):
        fit = next(
            (s.data for s in journal.steps if s.step is Step.FIT), {}
        )
        status = Status.TRAINED if fit.get("weights_written") else Status.FAILED
        return StageResult(
            "qlora_7b",
            status,
            f"reached {reached}; see journal for the full step record",
            metrics=fit,
            artifact=fit.get("adapter_dir"),
        )
    blocked = next(
        (s for s in journal.steps if s.outcome is Outcome.BLOCKED),
        journal.steps[-1] if journal.steps else None,
    )
    return StageResult(
        "qlora_7b",
        Status.SKIPPED,
        blocked.detail if blocked else "no steps recorded",
        metrics={"vram_free_mib": cap.vram_free_mib, "reached_step": reached},
    )


STAGES = (
    ("jepa", stage_jepa),
    ("energy_surrogate", stage_energy_surrogate),
    ("qlora_7b", stage_qlora),
)


# ---------------------------------------------------------------------- driver


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", help="run a single stage by name")
    parser.add_argument("--out", type=Path, default=RUNS)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
    )

    cap = probe_capability()
    logger.info(
        "capability: gpu=%s name=%s free=%s (%s)",
        cap.gpu,
        cap.gpu_name,
        cap.vram_free_mib,
        cap.detail,
    )

    results: list[StageResult] = []
    for name, fn in STAGES:
        if args.only and args.only != name:
            continue
        started = datetime.now(timezone.utc)
        logger.info("-> %s", name)
        try:
            result = fn(cap, args.dry_run)
        except Exception as exc:  # a stage must never take the night down
            logger.exception("   stage raised")
            result = StageResult(name, Status.FAILED, f"stage raised: {exc}")
        result.duration_s = (datetime.now(timezone.utc) - started).total_seconds()
        results.append(result)
        logger.info("   %s: %s", result.status, result.reason)

    trained = sum(1 for r in results if r.status is Status.TRAINED)
    skipped = sum(1 for r in results if r.status is Status.SKIPPED)
    failed = sum(1 for r in results if r.status is Status.FAILED)

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat().replace(":", "-")
    report = args.out / f"post_train_{stamp}.json"
    report.write_text(
        json.dumps(
            {
                "capability": asdict(cap),
                "counts": {
                    "trained": trained,
                    "skipped": skipped,
                    "failed": failed,
                },
                "stages": [asdict(r) for r in results],
                "note": (
                    "SKIPPED is a result, not a failure. Nothing here promotes a "
                    "model; promotion is gated by card P4-5/P4-8."
                ),
            },
            indent=2,
            default=str,
        )
        + "\n"
    )

    logger.info(
        "post-train complete: %d trained, %d skipped, %d failed -> %s",
        trained,
        skipped,
        failed,
        report,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
