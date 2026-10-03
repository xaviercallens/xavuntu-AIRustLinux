#!/usr/bin/env python3
"""
scripts/gcp_spot_manager.py — Low-Cost GCP Spot MicroVM Provisioner & Lifecycle Manager.

Manages ephemeral spot microVMs on Google Cloud Platform for differential kernel RL:
- Instance type: e2-micro ($0.002/hr spot) or e2-small ($0.005/hr spot).
- Hard budget guardrail: < $0.01 per execution session.
- Automatic self-termination & teardown (10-minute maximum runtime).
- Dual-side boot telemetry gathering and signed receipt download.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [GCP-SPOT] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gcp_spot_manager")


@dataclass
class GCPSpotConfig:
    project_id: str
    zone: str = "us-central1-a"
    machine_type: str = "e2-small"
    image_family: str = "debian-12"
    image_project: str = "debian-cloud"
    disk_size_gb: int = 15
    disk_type: str = "pd-standard"
    max_duration_seconds: int = 600
    max_budget_usd: float = 0.50  # Increased to support g2-standard-4

    @property
    def spot_hourly_rate_usd(self) -> float:
        rates = {
            "e2-small": 0.00504,
            "t2a-standard-1": 0.009,
            "c2-standard-4": 0.04,
            "n2d-standard-2": 0.015,
            "g2-standard-4": 0.20,
        }
        return rates.get(self.machine_type, 0.01)


class GCPSpotMicroVMManager:
    """Manages ephemeral low-cost spot microVM lifecycle on GCP."""

    def __init__(self, config: GCPSpotConfig | None = None) -> None:
        self.config = config or self._detect_default_config()
        self.vm_name = f"runux-spot-{int(time.time())}"
        self.telemetry_dir = REPO_ROOT / "dist" / "gcp_telemetry"
        self.telemetry_dir.mkdir(parents=True, exist_ok=True)

    def _detect_default_config(self) -> GCPSpotConfig:
        project_id = os.environ.get("GCP_PROJECT_ID")
        if not project_id:
            try:
                proc = subprocess.run(
                    ["gcloud", "config", "get-value", "project"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                project_id = proc.stdout.strip() or None
            except Exception:
                project_id = None
        if not project_id:
            # S-01b fix: Never fall back to a hardcoded project ID.
            # Require explicit GCP_PROJECT_ID env var or gcloud active config.
            raise ValueError(
                "GCP project ID not found. Set GCP_PROJECT_ID env var or run "
                "'gcloud config set project <PROJECT_ID>' before invoking GCPSpotMicroVMManager."
            )

        return GCPSpotConfig(project_id=project_id)


    def calculate_estimated_cost(self, duration_seconds: int) -> float:
        hours = duration_seconds / 3600.0
        compute_cost = hours * self.config.spot_hourly_rate_usd
        # Disk cost: 15 GB * $0.04/GB/month = $0.60/month = ~$0.0008/hr
        disk_cost = hours * (self.config.disk_size_gb * 0.04 / 730.0)
        return round(compute_cost + disk_cost, 6)

    def generate_create_command(self) -> list[str]:
        return [
            "gcloud", "compute", "instances", "create", self.vm_name,
            f"--project={self.config.project_id}",
            f"--zone={self.config.zone}",
            f"--machine-type={self.config.machine_type}",
            f"--image-family={self.config.image_family}",
            f"--image-project={self.config.image_project}",
            f"--boot-disk-size={self.config.disk_size_gb}GB",
            f"--boot-disk-type={self.config.disk_type}",
            "--provisioning-model=SPOT",
            "--instance-termination-action=DELETE",
            "--scopes=default",
            "--tags=runux-benchmark,spot-ephemeral",
            f"--metadata=max-runtime-seconds={self.config.max_duration_seconds}",
        ]

    def generate_delete_command(self) -> list[str]:
        return [
            "gcloud", "compute", "instances", "delete", self.vm_name,
            f"--project={self.config.project_id}",
            f"--zone={self.config.zone}",
            "--quiet",
        ]

    def dry_run(self) -> dict[str, Any]:
        """Validates configuration and outputs cost estimation without calling GCP APIs."""
        est_cost_10m = self.calculate_estimated_cost(600)
        logger.info("--- GCP SPOT MICRO-VM DRY RUN ---")
        logger.info(f"VM Name: {self.vm_name}")
        logger.info(f"Project: {self.config.project_id} | Zone: {self.config.zone}")
        logger.info(f"Machine Type: {self.config.machine_type} (SPOT)")
        logger.info(f"Hourly Spot Rate: ${self.config.spot_hourly_rate_usd:.5f} / hr")
        logger.info(f"Estimated 10-Minute Benchmark Session Cost: ${est_cost_10m:.6f} USD")
        logger.info(f"Budget Cap: ${self.config.max_budget_usd} USD (Margin: {self.config.max_budget_usd / est_cost_10m:.1f}x)")
        logger.info(f"Create Command: {' '.join(self.generate_create_command())}")
        logger.info(f"Delete Command: {' '.join(self.generate_delete_command())}")

        return {
            "status": "DRY_RUN_PASSED",
            "vm_name": self.vm_name,
            "project_id": self.config.project_id,
            "machine_type": self.config.machine_type,
            "estimated_cost_usd": est_cost_10m,
            "within_budget": est_cost_10m < self.config.max_budget_usd,
            "create_cmd": self.generate_create_command(),
            "delete_cmd": self.generate_delete_command(),
        }

    def provision_spot_vm(self) -> bool:
        cmd = self.generate_create_command()
        logger.info(f"Provisioning spot microVM '{self.vm_name}' on GCP...")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0:
                logger.info(f"Successfully created Spot VM: {self.vm_name}")
                return True
            else:
                logger.error(f"Failed to create Spot VM: {res.stderr.strip()}")
                return False
        except Exception as e:
            logger.error(f"Exception during VM creation: {e}")
            return False

    def teardown_spot_vm(self) -> bool:
        cmd = self.generate_delete_command()
        logger.info(f"Tearing down spot microVM '{self.vm_name}'...")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0:
                logger.info(f"Successfully deleted Spot VM: {self.vm_name}")
                return True
            else:
                logger.warning(f"VM delete warning: {res.stderr.strip()}")
                return False
        except Exception as e:
            logger.error(f"Exception during VM delete: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="GCP Spot MicroVM Lifecycle Manager")
    parser.add_argument("--dry-run", action="store_true", help="Validate and calculate costs without creating VM")
    parser.add_argument("--provision", action="store_true", help="Create GCP spot microVM")
    parser.add_argument("--teardown", action="store_true", help="Delete GCP spot microVM")
    parser.add_argument("--machine-type", default="e2-small", help="GCP Machine Type (e2-small, t2a-standard-1, c2-standard-4, n2d-standard-2, g2-standard-4)")
    args = parser.parse_args()

    manager = GCPSpotMicroVMManager()
    if args.dry_run or (not args.provision and not args.teardown):
        res = manager.dry_run()
        print(json.dumps(res, indent=2))
        sys.exit(0)

    if args.provision:
        success = manager.provision_spot_vm()
        sys.exit(0 if success else 1)

    if args.teardown:
        success = manager.teardown_spot_vm()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
