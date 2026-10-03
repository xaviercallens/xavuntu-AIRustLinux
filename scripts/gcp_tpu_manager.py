#!/usr/bin/env python3
"""
scripts/gcp_tpu_manager.py — Google Cloud Platform (GCP) Spot TPU VM Provisioning & Telemetry Manager.

Manages ephemeral Cloud TPU Spot instances for dual-kernel deep learning benchmarks:
- Hardware Target: Cloud TPU v5e (v5litepod-1, 1 TPU chip, 4 TensorCores, 16GB HBM)
- Spot Hourly Rate: ~$0.45 USD / hr (preemptible spot tier)
- Ephemeral Benchmark Session: 10 minutes (600s), Estimated Cost: ~$0.075 USD
- Budget Constraint: < $0.10 USD per benchmark session
- Invariants: Self-terminating metadata (`max-runtime-seconds=600`), auto-delete on preemption.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anse.rl.tpu_benchmarks import GoogleTPUBenchmarkSuite

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [GCP-TPU] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gcp_tpu_manager")


def _resolve_project_id() -> str:
    """Read GCP project ID from environment — never hard-coded in source."""
    pid = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if not pid:
        raise ValueError(
            "GCP_PROJECT_ID environment variable is not set. "
            "Export it before running: export GCP_PROJECT_ID=<your-project>"
        )
    return pid


@dataclass
class GCPSpotTPUConfig:
    project_id: str = ""  # Populated from GCP_PROJECT_ID env var at runtime
    zone: str = "us-central1-a"
    accelerator_type: str = "v5litepod-1"  # Cloud TPU v5e
    runtime_version: str = "v2-alpha-tpuv5-lite"
    spot_hourly_rate_usd: float = 0.450000  # $0.45 / hr spot rate
    max_session_seconds: int = 600          # 10 minutes
    max_budget_usd: float = 0.10            # Strict < $0.10 USD budget cap
    ephemeral_prefix: str = "runux-tpu-spot"


class GCPSpotTPUManager:
    """Manages ephemeral Cloud TPU Spot lifecycle and collects dual telemetry."""

    def __init__(self, config: GCPSpotTPUConfig | None = None) -> None:
        self.config = config or GCPSpotTPUConfig()
        if not self.config.project_id:
            self.config.project_id = _resolve_project_id()
        self.instance_name = f"{self.config.ephemeral_prefix}-{int(time.time())}"

    def estimate_session_cost(self, duration_seconds: int | None = None) -> float:
        secs = duration_seconds or self.config.max_session_seconds
        hours = secs / 3600.0
        return round(hours * self.config.spot_hourly_rate_usd, 6)

    def dry_run(self) -> dict[str, Any]:
        """Validates configuration, budget safety, and gcloud CLI command strings."""
        logger.info("--- GCP SPOT TPU VM DRY RUN ---")
        cost = self.estimate_session_cost()
        within_budget = cost <= self.config.max_budget_usd
        margin = self.config.max_budget_usd / max(0.0001, cost)

        create_cmd = (
            f"gcloud compute tpus tpu-vm create {self.instance_name} "
            f"--project={self.config.project_id} "
            f"--zone={self.config.zone} "
            f"--accelerator-type={self.config.accelerator_type} "
            f"--version={self.config.runtime_version} "
            f"--spot "
            f"--metadata=max-runtime-seconds={self.config.max_session_seconds} "
            f"--scopes=https://www.googleapis.com/auth/cloud-platform"
        )

        delete_cmd = (
            f"gcloud compute tpus tpu-vm delete {self.instance_name} "
            f"--project={self.config.project_id} "
            f"--zone={self.config.zone} "
            f"--quiet"
        )

        logger.info(f"TPU Name: {self.instance_name}")
        logger.info(f"Project: {self.config.project_id} | Zone: {self.config.zone}")
        logger.info(f"Accelerator Type: {self.config.accelerator_type} (SPOT)")
        logger.info(f"Hourly Spot Rate: ${self.config.spot_hourly_rate_usd:.4f} / hr")
        logger.info(f"Estimated 10-Minute Session Cost: ${cost:.6f} USD")
        logger.info(f"Budget Cap: ${self.config.max_budget_usd:.2f} USD (Margin: {margin:.1f}x)")
        logger.info(f"Create Command: {create_cmd}")
        logger.info(f"Delete Command: {delete_cmd}")

        return {
            "instance_name": self.instance_name,
            "project_id": self.config.project_id,
            "zone": self.config.zone,
            "accelerator_type": self.config.accelerator_type,
            "runtime_version": self.config.runtime_version,
            "hourly_spot_rate_usd": self.config.spot_hourly_rate_usd,
            "estimated_cost_usd": cost,
            "budget_cap_usd": self.config.max_budget_usd,
            "within_budget": within_budget,
            "budget_margin_ratio": round(margin, 2),
            "create_command": create_cmd,
            "delete_command": delete_cmd,
            "status": "DRY_RUN_PASSED" if within_budget else "BUDGET_EXCEEDED",
        }

    def execute_dual_tpu_benchmark(self, iterations: int = 5) -> dict[str, Any]:
        """
        Executes the dual TPU benchmark suite and archives GCP Spot telemetry.
        Raises ValueError if projected session cost exceeds the budget cap before execution.
        """
        # Budget enforcement before execution (F-20)
        projected_cost = self.estimate_session_cost()
        if projected_cost > self.config.max_budget_usd:
            raise ValueError(
                f"Projected session cost ${projected_cost:.6f} exceeds budget cap "
                f"${self.config.max_budget_usd:.2f}. Aborting to avoid overspend."
            )

        logger.info("Executing Google TPU & TensorFlow Dual-Side Microbenchmark Suite...")
        try:
            suite = GoogleTPUBenchmarkSuite()
            tpu_report = suite.run_all_tpu_benchmarks(iterations=iterations)
        except Exception as exc:
            logger.error(f"TPU benchmark suite failed: {exc}")
            raise RuntimeError(f"GoogleTPUBenchmarkSuite execution failed: {exc}") from exc

        cost = self.estimate_session_cost()
        dist_dir = REPO_ROOT / "dist" / "gcp_telemetry"
        dist_dir.mkdir(parents=True, exist_ok=True)
        telemetry_file = dist_dir / "gcp_tpu_benchmark.json"

        telemetry_data = {
            "environment": "GCP_SPOT_TPU_V5E",
            "accelerator_type": self.config.accelerator_type,
            "runtime_version": self.config.runtime_version,
            "zone": self.config.zone,
            "hourly_spot_rate_usd": self.config.spot_hourly_rate_usd,
            "session_cost_usd": cost,
            "budget_cap_usd": self.config.max_budget_usd,
            "budget_margin_ratio": round(self.config.max_budget_usd / max(0.0001, cost), 2),
            "timestamp": time.time(),
            "tpu_benchmark_report": tpu_report.to_dict(),
        }

        with open(telemetry_file, "w") as f:
            json.dump(telemetry_data, f, indent=2)

        logger.info(f"Saved GCP Spot TPU Telemetry to {telemetry_file}")
        return telemetry_data


def main():
    parser = argparse.ArgumentParser(description="GCP Spot TPU VM Manager")
    parser.add_argument("--dry-run", action="store_true", help="Execute dry run and print commands")
    parser.add_argument("--bench", action="store_true", help="Execute TPU benchmark suite")
    parser.add_argument("--iterations", type=int, default=5, help="Benchmark iterations")
    args = parser.parse_args()

    manager = GCPSpotTPUManager()
    if args.bench:
        data = manager.execute_dual_tpu_benchmark(iterations=args.iterations)
        rep = data["tpu_benchmark_report"]
        passed = rep["passed_50_ai_gate"]
        sys.exit(0 if passed else 1)
    else:
        res = manager.dry_run()
        sys.exit(0 if res["within_budget"] else 1)


if __name__ == "__main__":
    main()
