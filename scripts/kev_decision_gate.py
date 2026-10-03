#!/usr/bin/env python3
"""
Kev Calibrated Decision Gate for SAAW (SocrateAI Autonomous Agent Workflow).

Evaluates the results of nightly model retraining runs using Kev
(Open-Source Jev / TypeSafe System One architecture) to determine:
- promote_checkpoint (Noul: Yes/No probability)
- deployment_strategy (Choice: deploy_full_stack, local_staging_only, rollback, quarantine)
- retraining_quality_score (Score: expected quality tier [0..3])
- next_cycle_adaptation (Choice: adaptive parameter adjustment)

Usage:
  uv run python scripts/kev_decision_gate.py
  uv run python scripts/kev_decision_gate.py --report results/nightly_training/nightly_retrain_5am_report.json --gate
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from anse.decision.kev_engine import KevDecisionEngine, evaluate_retraining_decision

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("KevDecisionGate")


def _resolve_default_report_path() -> Path | None:
    """Find the freshest report among interim and final nightly reports."""
    interim = REPO_ROOT / "results" / "nightly_training" / "nightly_retrain_interim_report.json"
    final_rep = REPO_ROOT / "results" / "nightly_training" / "nightly_retrain_5am_report.json"

    candidates = [p for p in (interim, final_rep) if p.exists()]
    if not candidates:
        return None
    # Pick the newest by modification time
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kev SAAW Retrain Decision Gate")
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Path to nightly retraining report JSON",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output path for decision JSON (default: results/nightly_training/kev_retrain_decision.json)",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Enforce gate: exit code 0 if APPROVED, code 1 if REJECTED or QUARANTINED",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Optional remote Kev / TypeSafe System One URL (e.g. http://localhost:8009)",
    )
    parser.add_argument(
        "--temp",
        type=float,
        default=1.0,
        help="Calibration temperature for Kev decision engine",
    )
    args = parser.parse_args()

    report_path = Path(args.report) if args.report else _resolve_default_report_path()
    out_path = Path(args.out) if args.out else None

    logger.info("================================================================================")
    logger.info("⚖️  KEV SAAW POST-RETRAIN CALIBRATED DECISION GATE")
    logger.info("================================================================================")

    if not report_path or not report_path.exists():
        logger.error("No retraining report found (checked --report, interim, and final paths)")
        return 2

    logger.info("Evaluating telemetry report : %s", report_path)
    engine = KevDecisionEngine(base_url=args.url, temperature=args.temp)
    telemetry = json.loads(report_path.read_text(encoding="utf-8"))

    decision = engine.evaluate_saaw_retraining(telemetry)
    saved_path = engine.save_decision(decision, output_path=out_path)

    # Print formatted decision briefing
    logger.info("Profile ID                  : %s", decision.profile_id)
    logger.info("Status                      : %s", decision.status)
    logger.info("Promote Checkpoint (Noul)   : %s (P = %.4f)", decision.promote_checkpoint, decision.promote_probability)
    logger.info("Deployment Strategy (Choice): %s (Conf = %.4f)", decision.deployment_strategy, decision.deployment_confidence)
    logger.info("Quality Score (Score)       : %.2f / 3.00 (Conf = %.4f)", decision.retraining_quality_score, decision.retraining_quality_confidence)
    logger.info("Next Cycle Adaptation       : %s (Conf = %.4f)", decision.next_cycle_adaptation, decision.adaptation_confidence)
    if decision.failed_steps:
        logger.info("Failed Steps                : %s", decision.failed_steps)
    logger.info("Summary Reasoning           : %s", decision.summary_reasoning)
    logger.info("Report Saved To             : %s", saved_path)
    logger.info("================================================================================")

    if args.gate and decision.status != "APPROVED":
        logger.warning("❌ Gate failed: Post-retraining decision status is %s (not APPROVED)", decision.status)
        return 1

    logger.info("✅ Gate passed: Retraining run approved for deployment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
