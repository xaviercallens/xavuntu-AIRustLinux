#!/usr/bin/env python3
"""
Autonomous Nightly Model Retraining Pipeline (Scheduled after 05:00 AM).

Orchestrates the complete overnight retraining of:
1. Nightly REM Dream Consolidation (Hippocampus Replay, Laya LoRA, Latent MCTS)
2. Redis Long-Term Memory (LTM) Sync from brain transcripts
3. Qwen2.5-0.5B LoRA Adapter fine-tuning on Redis LTM conversations
4. RL EnergyCriticPolicy multi-disciplinary DPO / reward retraining
5. System 1.5 EB-JEPA World Model continual physics training
6. Autonomous ANSE V2 Autopoietic Engine validation
7. Automated synchronization of updated checkpoints to SocrateAI GCP Data Lake & Cartography
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, "/mnt/disks/disk-socrateai-local-1/gpu_lease")

from gpu_lease import gpu_lease  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("NightlyRetrainer")

REPO_ROOT = Path(__file__).resolve().parent.parent
# One lease for the whole training block. gpu_lease re-enters only for the SAME holder
# string, so the child runners this script launches (nightly_dream_phase.py,
# execute_local_redis_ltm_lora.py) use this exact name: a different name would make them
# block behind their own parent until the timeout.
LEASE_HOLDER = "autoevolve-nightly"
LOG_DIR = REPO_ROOT / "results" / "nightly_training"
LOG_DIR.mkdir(parents=True, exist_ok=True)
RUN_LOG = LOG_DIR / "nightly_retrain_5am.log"


def log_both(msg: str) -> None:
    logger.info(msg)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().isoformat()} - {msg}\n")


def run_pipeline_step(name: str, cmd: list[str]) -> dict[str, Any]:
    """Execute a single pipeline command with logging and timing."""
    log_both(f"▶️ Starting step: {name}")
    log_both(f"   Command: {' '.join(cmd)}")
    start = time.time()
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)
    elapsed = time.time() - start

    if res.returncode == 0:
        log_both(f"✅ Step '{name}' completed successfully in {elapsed:.2f}s")
        success = True
    else:
        log_both(f"❌ Step '{name}' failed with code {res.returncode} in {elapsed:.2f}s")
        log_both(f"   Stderr: {res.stderr[-1000:] if res.stderr else 'None'}")
        success = False

    return {
        "step": name,
        "success": success,
        "returncode": res.returncode,
        "elapsed_sec": round(elapsed, 2),
        "stdout_tail": res.stdout[-500:] if res.stdout else "",
        "stderr_tail": res.stderr[-500:] if res.stderr else "",
    }


def wait_until_target_time(target_hour: int = 5, target_minute: int = 5) -> None:
    """Sleep until the next occurrence of target_hour:target_minute (default 05:05 AM)."""
    now = datetime.datetime.now()
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now:
        # If target has passed today, schedule for tomorrow morning
        target += datetime.timedelta(days=1)

    wait_seconds = (target - now).total_seconds()
    log_both(f"🕒 Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    log_both(f"🎯 Target retraining time: {target.strftime('%Y-%m-%d %H:%M:%S')}")
    log_both(f"⏳ Sleeping for {wait_seconds:.0f} seconds ({wait_seconds/3600:.2f} hours)...")

    # Sleep in chunks to allow responsive logging and health tracking
    while True:
        remaining = (target - datetime.datetime.now()).total_seconds()
        if remaining <= 0:
            break
        sleep_duration = min(remaining, 600)  # log countdown every 10 minutes
        time.sleep(sleep_duration)
        now_check = datetime.datetime.now()
        rem_hours = (target - now_check).total_seconds() / 3600
        if rem_hours > 0:
            log_both(f"⏳ Nightly countdown: {rem_hours:.2f} hours remaining until 05:05 AM retraining.")

    log_both("⏰ Target time reached! Commencing Nightly Model Retraining Pipeline...")


def execute_nightly_retraining(lora_steps: int = 10, skip_deploy: bool = False) -> dict[str, Any]:
    """Execute all phases of model retraining, database snapshotting, and cloud deployment."""
    pipeline_start = time.time()
    log_both("=" * 80)
    log_both("🌙 ANSE MASTER NIGHTLY RETRAINING & CONTINUAL LEARNING LOOP")
    log_both("=" * 80)

    results: list[dict[str, Any]] = []

    with gpu_lease(LEASE_HOLDER, "nightly retrain: dream + LTM LoRA + RL + JEPA + v2 validation", ttl_s=6 * 3600, timeout_s=3600):
        # 1. REM Sleep Dream Phase: Hippocampus Replay, Laya LoRA & Latent MCTS
        results.append(
            run_pipeline_step(
                "Nightly REM Dream Consolidation & Laya LoRA",
                ["uv", "run", "python", "scripts/nightly_dream_phase.py"],
            )
        )

        # 2. Sync brain transcripts to Redis LTM
        results.append(
            run_pipeline_step(
                "Redis Long-Term Memory Sync",
                ["uv", "run", "python", "scripts/sync_conversations_to_redis.py"],
            )
        )

        # 3. Retrain Qwen LoRA on Redis LTM conversations
        results.append(
            run_pipeline_step(
                "Qwen LoRA LTM Retraining",
                ["uv", "run", "python", "scripts/execute_local_redis_ltm_lora.py", "--steps", str(lora_steps), "--max-len", "160"],
            )
        )

        # 4. Retrain RL EnergyCriticPolicy & DPO on multi-domain cases
        results.append(
            run_pipeline_step(
                "Reinforcement Learning Critic Retraining",
                ["uv", "run", "python", "scripts/retrain_multidisciplinary_rl.py"],
            )
        )

        # 5. Retrain JEPA World Model on Physics Systems
        results.append(
            run_pipeline_step(
                "JEPA World Model Continual Learning",
                ["uv", "run", "python", "-m", "anse.physics.advanced_world_models"],
            )
        )

        # 6. Run Autopoietic V2 Validation
        results.append(
            run_pipeline_step(
                "ANSE V2 Autopoietic Engine Validation",
                ["uv", "run", "python", "scripts/run_v2_autopoiesis.py"],
            )
        )

    # 7. Kev SAAW Post-Retraining Decision Gate
    # Write intermediate telemetry of steps 1-6 so Kev evaluates fresh data
    interim_summary = {
        "status": "SUCCESS" if all(r["success"] for r in results) else "PARTIAL_FAILURE",
        "timestamp": datetime.datetime.now().isoformat(),
        "total_elapsed_sec": round(time.time() - pipeline_start, 2),
        "steps": results,
    }
    interim_report_path = LOG_DIR / "nightly_retrain_interim_report.json"
    interim_report_path.write_text(json.dumps(interim_summary, indent=2), encoding="utf-8")

    decision_step = run_pipeline_step(
        "Kev Post-Retrain Calibrated Decision Gate",
        [
            "uv", "run", "python", "scripts/kev_decision_gate.py",
            "--report", str(interim_report_path),
            "--gate",
        ],
    )
    results.append(decision_step)

    # Inspect Kev decision to decide deployment
    decision_file = LOG_DIR / "kev_retrain_decision.json"
    approved_for_deploy = False
    if decision_file.exists():
        try:
            d_data = json.loads(decision_file.read_text(encoding="utf-8"))
            approved_for_deploy = (
                d_data.get("status") == "APPROVED"
                and d_data.get("deployment_strategy") == "deploy_full_stack"
            )
            log_both(
                f"⚖️ Kev Post-Retrain Decision: Status={d_data.get('status')}, "
                f"Strategy={d_data.get('deployment_strategy')}, "
                f"P(Promote)={d_data.get('promote_probability')}, "
                f"Quality={d_data.get('retraining_quality_score')}/3.0"
            )
        except Exception as e:
            log_both(f"⚠️ Could not parse Kev decision: {e}")

    # 8. Deploy updated checkpoints & databases to GCP Data Lake (conditioned on Kev Decision)
    if not skip_deploy:
        if approved_for_deploy:
            results.append(
                run_pipeline_step(
                    "GCP Data Lake Synchronization & Cartography",
                    ["uv", "run", "python", "scripts/deploy_models_and_datalake.py"],
                )
            )
        else:
            log_both("🛑 Kev Decision Gate withheld deployment: Checkpoint not approved for cloud overwrite.")
            results.append({
                "step": "GCP Data Lake Synchronization & Cartography",
                "success": False,
                "returncode": 1,
                "elapsed_sec": 0.0,
                "stdout_tail": "",
                "stderr_tail": "Deployment aborted by Kev Decision Gate: Checkpoint not approved for cloud overwrite.",
            })

    total_elapsed = time.time() - pipeline_start
    all_success = all(r["success"] for r in results)

    summary = {
        "status": "SUCCESS" if all_success else "PARTIAL_FAILURE",
        "timestamp": datetime.datetime.now().isoformat(),
        "total_elapsed_sec": round(total_elapsed, 2),
        "steps": results,
    }

    report_path = LOG_DIR / "nightly_retrain_5am_report.json"
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log_both("=" * 80)
    log_both(f"🎉 NIGHTLY RETRAINING COMPLETE: Status={summary['status']} in {total_elapsed:.2f}s")
    log_both(f"📄 Report written to {report_path}")
    log_both("=" * 80)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Nightly Model Retraining Pipeline after 05:00 AM")
    parser.add_argument("--wait", action="store_true", help="Sleep until 05:05 AM before running")
    parser.add_argument("--now", action="store_true", help="Run immediately without waiting")
    parser.add_argument("--hour", type=int, default=5, help="Target hour (default 5)")
    parser.add_argument("--minute", type=int, default=5, help="Target minute (default 5)")
    parser.add_argument("--lora-steps", type=int, default=10, help="Number of LoRA steps for Qwen LTM on CPU (default 10)")
    parser.add_argument("--skip-deploy", action="store_true", help="Skip deployment to GCP Data Lake")
    args = parser.parse_args()

    if args.wait:
        wait_until_target_time(target_hour=args.hour, target_minute=args.minute)
    elif not args.now:
        # Default behavior: if currently before target hour (e.g. 23:00), wait until 05:05 AM
        now = datetime.datetime.now()
        if now.hour != args.hour:
            wait_until_target_time(target_hour=args.hour, target_minute=args.minute)

    summary = execute_nightly_retraining(lora_steps=args.lora_steps, skip_deploy=args.skip_deploy)
    return 0 if summary["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(main())
