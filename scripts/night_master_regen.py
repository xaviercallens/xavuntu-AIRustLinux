#!/usr/bin/env python3
"""
Night Master Regeneration Pipeline

Orchestrates:
1. Generate solutions for 20 master-level math problems with LLM call logging
2. Harvest verified episodes from solutions
3. Run night training workflow to retrain models on new data
4. Report results and gate status

Runs end-to-end on T4 with Ollama, no GPU needed for training (will use CPU fallback).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("night_master_regen")

REPO = Path(__file__).parent.parent.absolute()
DISK2 = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI")
CALL_LOGS = DISK2 / "call_logs"
RESULTS = DISK2 / "night_regen_results"


def run_master_math_generation() -> dict[str, Any]:
    """Run 20 master math problems with LLM call logging."""
    logger.info("=== Phase 1: Regenerate solutions for 20 master math problems ===")
    CALL_LOGS.mkdir(parents=True, exist_ok=True)

    call_log_file = CALL_LOGS / f"master_math_{datetime.now(timezone.utc).isoformat()}.jsonl"

    start = time.time()
    try:
        env = os.environ.copy()
        env.update({
            "PYTHONPATH": str(REPO),
            "ANSE_CALL_LOG": str(call_log_file),
            "AUTOEVOLVE_GPU_HINT": "t4",
        })

        result = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts" / "regenerate_10_math_problems_dspy.py"),
                "20",  # 20 master problems
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour max
            env=env,
        )
        elapsed = time.time() - start

        logger.info(f"Master math generation completed in {elapsed:.1f}s")
        logger.info(f"stdout: {result.stdout[-500:]}")  # Last 500 chars
        if result.stderr:
            logger.warning(f"stderr: {result.stderr[-500:]}")

        return {
            "step": "master_math_generation",
            "status": "completed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "elapsed_s": elapsed,
            "call_log": str(call_log_file),
            "call_log_exists": call_log_file.exists(),
            "call_count": count_jsonl_lines(call_log_file) if call_log_file.exists() else 0,
        }
    except subprocess.TimeoutExpired:
        logger.error("Master math generation timed out after 3600s")
        return {
            "step": "master_math_generation",
            "status": "timeout",
            "exit_code": -1,
            "elapsed_s": 3600.0,
        }
    except Exception as e:
        logger.error(f"Master math generation failed: {e}")
        return {
            "step": "master_math_generation",
            "status": "error",
            "error": str(e),
        }


def harvest_episodes() -> dict[str, Any]:
    """Harvest verified episodes from generated solutions."""
    logger.info("=== Phase 2: Harvest verified episodes ===")

    start = time.time()
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts" / "harvest_episodes.py"),
                "--tasks",
                "20",
                "--samples",
                "1",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes
        )
        elapsed = time.time() - start

        logger.info(f"Episode harvest completed in {elapsed:.1f}s")
        if result.returncode == 0:
            # Parse output for statistics
            lines = result.stdout.split("\n")
            logger.info(f"Harvest output (last 10 lines): {lines[-10:]}")

        return {
            "step": "harvest_episodes",
            "status": "completed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "elapsed_s": elapsed,
        }
    except subprocess.TimeoutExpired:
        logger.error("Episode harvest timed out after 600s")
        return {"step": "harvest_episodes", "status": "timeout", "elapsed_s": 600.0}
    except Exception as e:
        logger.error(f"Episode harvest failed: {e}")
        return {"step": "harvest_episodes", "status": "error", "error": str(e)}


def run_night_training() -> dict[str, Any]:
    """Run the night training workflow to retrain models."""
    logger.info("=== Phase 3: Retrain models on harvested episodes ===")

    start = time.time()
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts" / "night_training_workflow.py"),
                "--smoke",  # Use quick smoke test for now
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=1200,  # 20 minutes for smoke test
        )
        elapsed = time.time() - start

        logger.info(f"Night training completed in {elapsed:.1f}s")
        logger.info(f"Training output (last 1000 chars): {result.stdout[-1000:]}")

        return {
            "step": "night_training",
            "status": "completed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "elapsed_s": elapsed,
        }
    except subprocess.TimeoutExpired:
        logger.error("Night training timed out after 1200s")
        return {"step": "night_training", "status": "timeout", "elapsed_s": 1200.0}
    except Exception as e:
        logger.error(f"Night training failed: {e}")
        return {"step": "night_training", "status": "error", "error": str(e)}


def count_jsonl_lines(path: Path) -> int:
    """Count lines in a JSONL file."""
    if not path.exists():
        return 0
    try:
        with open(path) as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def main() -> int:
    """Run the full pipeline and report results."""
    logger.info(f"Starting night master regeneration pipeline at {datetime.now(timezone.utc)}")

    RESULTS.mkdir(parents=True, exist_ok=True)

    results = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "phases": [],
    }

    # Phase 1: Generate
    phase1 = run_master_math_generation()
    results["phases"].append(phase1)
    if phase1.get("status") != "completed":
        logger.error("Phase 1 (master math generation) failed; stopping pipeline")
        results["outcome"] = "BLOCKED_AT_GENERATION"
        save_results(results)
        return 1

    # Phase 2: Harvest
    phase2 = harvest_episodes()
    results["phases"].append(phase2)
    if phase2.get("status") != "completed":
        logger.warning("Phase 2 (harvest) failed; attempting training anyway")

    # Phase 3: Train
    phase3 = run_night_training()
    results["phases"].append(phase3)

    results["completed_at"] = datetime.now(timezone.utc).isoformat()
    results["outcome"] = (
        "SUCCESS"
        if all(p.get("status") == "completed" for p in results["phases"])
        else "PARTIAL_SUCCESS"
    )

    save_results(results)
    logger.info(f"Pipeline outcome: {results['outcome']}")
    return 0 if results["outcome"] == "SUCCESS" else 1


def save_results(results: dict[str, Any]) -> None:
    """Save results to disk for review."""
    results_file = RESULTS / f"night_regen_{datetime.now(timezone.utc).isoformat()}.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved to {results_file}")


if __name__ == "__main__":
    sys.exit(main())
