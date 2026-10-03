#!/usr/bin/env python3
"""
Kick-start the local environment from the SocrateAI GCS data lake.

The lake holds artifacts this checkout does not have, and several of them
retire work the remediation card set had planned from scratch:

  * rl_common.py / rl_agent_api.py -- the two modules the audit reported as
    hallucinated imports. They are real; they were simply never vendored.
    Fetching them repairs dream_lora_trainer.py and laya_system_one.py.
  * dump.rdb (516 keys), the Chroma stores, redis_ltm_lora_dataset.jsonl --
    real memory and training data, versus the 1-line fixtures on disk.
  * JEPA / RL / Qwen checkpoints -- real weights, versus zero .safetensors
    anywhere in the repo.

WHAT THIS DOES NOT DO: it does not put any fetched model into service. The
lake's flagship Qwen artifact (merged_quick_restart, 1.84 GiB) is the output
of an 8-step run whose loss ROSE 3.532 -> 3.692 and which labelled itself
"status": "SUCCESS" -- its own report is in the lake next to it. Weights are
assets; a SUCCESS label on them is not evidence. Everything lands under
candidates/ or reference/ and reaches `active` only through the eval gate in
card P4-5.

Every download is verified against the size the bucket reports. A fetch that
cannot be verified raises; nothing here returns success for work it skipped.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("bootstrap")

BUCKET = "gs://socrateai-datalake-gen-lang-client-0625573011"
LAKE = f"{BUCKET}/autoevolve_anse_datalake"

# Default staging root lives on the second disk: 203 GB free there versus
# 81 GB on /, and the merged checkpoint alone is 1.84 GiB.
DEFAULT_STAGE = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/datalake")


@dataclass(frozen=True)
class Artifact:
    """One object to fetch. `size_bytes` is what the bucket reported on
    2026-09-25; a mismatch means the lake changed and must be re-checked."""

    remote: str
    local: str
    size_bytes: int
    purpose: str


# Vendored code: fixes imports that are currently dead in this checkout.
CODE_ARTIFACTS: tuple[Artifact, ...] = (
    Artifact(
        f"{LAKE}/models/rl_models/laya/rl_common.py",
        "vendor/laya/rl_common.py",
        19139,
        "repairs `from rl_common import` in anse/autopoiesis/dream_lora_trainer.py:27",
    ),
    Artifact(
        f"{LAKE}/models/rl_models/laya/rl_agent_api.py",
        "vendor/laya/rl_agent_api.py",
        4732,
        "repairs the rl_agent_api import in anse/v5/laya_system_one.py:47",
    ),
)

# Data: memory and training corpora. Safe to restore; not model weights.
DATA_ARTIFACTS: tuple[Artifact, ...] = (
    Artifact(
        f"{LAKE}/database_exports/redis/dump.rdb",
        "data/redis/dump.rdb",
        19961138,
        "516-key Redis LTM snapshot (restore is a human step; see --print-redis-restore)",
    ),
    Artifact(
        f"{LAKE}/database_exports/redis/redis_ltm_lora_dataset.jsonl",
        "data/redis/redis_ltm_lora_dataset.jsonl",
        0,  # 0 = size unknown; verified as non-empty instead
        "extracted conversation training set -- must still pass the P4-2 verified-data gate",
    ),
    Artifact(
        f"{LAKE}/database_exports/chroma/chroma_mathlib_rag_db.tar.gz",
        "data/chroma/chroma_mathlib_rag_db.tar.gz",
        0,
        "Lean 4 Mathlib vector store",
    ),
    Artifact(
        f"{LAKE}/database_exports/chroma/chroma_main_db.tar.gz",
        "data/chroma/chroma_main_db.tar.gz",
        0,
        "main ANSE memory store",
    ),
)

# Model weights: candidates only. Never activated by this script.
MODEL_ARTIFACTS: tuple[Artifact, ...] = (
    Artifact(
        f"{LAKE}/models/jepa/jepa_best.pt",
        "candidates/jepa/jepa_best.pt",
        23435277,
        "JEPA world model -- real weights for a trainer that has never had data",
    ),
    Artifact(
        f"{LAKE}/models/rl_models/surrogate_energy_predictor_v2.pt",
        "candidates/rl/surrogate_energy_predictor_v2.pt",
        0,
        "energy surrogate -- shadow-mode only until AUROC >= 0.80 per the roadmap",
    ),
    Artifact(
        f"{LAKE}/models/qwen_lora_ltm/adapter/adapter_model.safetensors",
        "reference/qwen_0_5b_lora/adapter_model.safetensors",
        2175168,
        "0.5B LoRA adapter -- REFERENCE/REGRESSION FIXTURE ONLY (its run regressed)",
    ),
)


def gcloud_size(remote: str) -> int:
    """Ask the bucket how big an object is. Raises if it cannot be read."""
    proc = subprocess.run(
        ["gcloud", "storage", "ls", "-l", remote],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"cannot stat {remote}: {proc.stderr.strip()}")
    for token in proc.stdout.split():
        if token.isdigit():
            return int(token)
    raise RuntimeError(f"no size in `gcloud storage ls -l` output for {remote}")


def fetch(artifact: Artifact, stage: Path, force: bool) -> Path:
    """Download one artifact and verify it. Raises on any mismatch."""
    dest = stage / artifact.local
    dest.parent.mkdir(parents=True, exist_ok=True)

    expected = artifact.size_bytes or gcloud_size(artifact.remote)

    if dest.exists() and not force:
        actual = dest.stat().st_size
        if actual == expected:
            logger.info("  = %s (already present, %d bytes)", artifact.local, actual)
            return dest
        logger.warning(
            "  ! %s exists with wrong size (%d != %d); refetching",
            artifact.local,
            actual,
            expected,
        )

    logger.info("  > %s (%d bytes)", artifact.local, expected)
    proc = subprocess.run(
        ["gcloud", "storage", "cp", artifact.remote, str(dest)],
        capture_output=True,
        text=True,
        timeout=3600,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"download failed for {artifact.remote}: {proc.stderr.strip()}")

    if not dest.exists():
        raise RuntimeError(f"{artifact.remote} reported success but {dest} does not exist")
    actual = dest.stat().st_size
    if actual != expected:
        raise RuntimeError(
            f"{artifact.local}: size mismatch after download "
            f"(got {actual}, bucket says {expected})"
        )
    if actual == 0:
        raise RuntimeError(f"{artifact.local} downloaded as an empty file")
    return dest


def unpack_chroma(stage: Path) -> list[Path]:
    """Extract the Chroma tarballs next to themselves. Returns what was made."""
    made: list[Path] = []
    for tar_path in sorted((stage / "data/chroma").glob("*.tar.gz")):
        target = tar_path.with_suffix("").with_suffix("")
        if target.exists():
            logger.info("  = %s already unpacked", target.name)
            made.append(target)
            continue
        logger.info("  > unpacking %s", tar_path.name)
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tar_path) as tf:
            # filter="data" refuses absolute paths and traversal outside target.
            tf.extractall(target, filter="data")
        made.append(target)
    return made


def redis_restore_instructions(stage: Path) -> str:
    """Print, do not run. This writes into /var/lib/redis and owns a service."""
    rdb = stage / "data/redis/dump.rdb"
    return "\n".join(
        [
            "Redis restore is a human step (it stops a service and writes to /var/lib/redis).",
            "It also overlaps card P0-5. Run these yourself once Redis is installed:",
            "",
            "  sudo systemctl stop redis-server",
            f"  sudo cp {rdb} /var/lib/redis/dump.rdb",
            "  sudo chown redis:redis /var/lib/redis/dump.rdb",
            "  sudo systemctl start redis-server",
            "  redis-cli DBSIZE      # expect 516",
            "",
            "Do not point a running Redis at this file without stopping it first:",
            "a live server rewrites dump.rdb on shutdown and will discard it.",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, default=DEFAULT_STAGE)
    parser.add_argument(
        "--only",
        choices=["code", "data", "models", "all"],
        default="all",
        help="which artifact group to fetch",
    )
    parser.add_argument("--force", action="store_true", help="refetch even if present")
    parser.add_argument(
        "--dry-run", action="store_true", help="list what would be fetched, fetch nothing"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if shutil.which("gcloud") is None:
        logger.error("gcloud is not on PATH; cannot reach the data lake")
        return 1

    groups: list[tuple[str, tuple[Artifact, ...]]] = []
    if args.only in ("code", "all"):
        groups.append(("code (repairs dead imports)", CODE_ARTIFACTS))
    if args.only in ("data", "all"):
        groups.append(("data (memory + corpora)", DATA_ARTIFACTS))
    if args.only in ("models", "all"):
        groups.append(("models (candidates only, never activated)", MODEL_ARTIFACTS))

    if args.dry_run:
        for label, artifacts in groups:
            print(f"\n{label}:")
            for a in artifacts:
                print(f"  {a.remote}")
                print(f"    -> {args.stage / a.local}")
                print(f"    {a.purpose}")
        print(f"\nStage root: {args.stage}")
        return 0

    args.stage.mkdir(parents=True, exist_ok=True)
    fetched: list[str] = []
    failures: list[str] = []

    for label, artifacts in groups:
        logger.info("\n%s", label)
        for artifact in artifacts:
            try:
                fetch(artifact, args.stage, args.force)
                fetched.append(artifact.local)
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                logger.error("  x %s: %s", artifact.local, exc)
                failures.append(f"{artifact.local}: {exc}")

    if args.only in ("data", "all") and not failures:
        logger.info("\nchroma")
        try:
            unpack_chroma(args.stage)
        except (tarfile.TarError, OSError) as exc:
            failures.append(f"chroma unpack: {exc}")
            logger.error("  x unpack failed: %s", exc)

    manifest = args.stage / "bootstrap_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "stage": str(args.stage),
                "fetched": fetched,
                "failures": failures,
                "note": (
                    "Models are candidates. Nothing here is active. Promotion is "
                    "gated by the eval in card P4-5."
                ),
            },
            indent=2,
        )
        + "\n"
    )

    print()
    print(f"fetched {len(fetched)} artifact(s); {len(failures)} failure(s)")
    print(f"manifest: {manifest}")
    if args.only in ("data", "all"):
        print()
        print(redis_restore_instructions(args.stage))

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
