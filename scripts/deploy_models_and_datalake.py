#!/usr/bin/env python3
"""
Comprehensive Deployment Script for AutoevolveAI / ANSE Models & Data Lake Cartography.

Target GCP Project: gen-lang-client-0625573011 (SocrateAI)
Target GCS Data Lake: gs://socrateai-datalake-gen-lang-client-0625573011/
Model Mirror Bucket: gs://symbrain-v2-models/anse/

Deploys:
1. Model Serializations:
   - JEPA / JEDA world models (jepa_best.pt, jepa_world_model_unified_200.pt, architectures)
   - Qwen / Gwen LoRA & merged weights (results/qwen_lora_ltm_local/merged_quick_restart/model.safetensors, adapter)
   - DeepSeek Lean Solver (Cloud Run configs, MCTS prover code, benchmarks, formal specs)
   - RL models (unified energy models, formal critics, surrogate predictors, nightly checkpoints, Laya agent)
   - 57 Evolution adapter checkpoints
2. Databases:
   - Live Redis database snapshot (dump.rdb) + conversation sync datasets & reports
   - Chroma vector databases (mathlib_rag_db, chroma_db, fast_db, dense_db, benchmark_db, test_db)
3. Open Source Stack & GCP VM Deployment Artifacts:
   - anse_open_source_core.tar.gz
   - deploy/gcp_vm_bootstrap.sh (turnkey startup script for GCP Compute Engine VMs)
   - systemd service unit definitions
4. Full Cartography:
   - Multi-prefix deep inspection of gs://socrateai-datalake-gen-lang-client-0625573011/ and gs://symbrain-v2-models/
   - Interactive DATA_LAKE_CARTOGRAPHY.md and machine-readable data_lake_cartography.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("datalake_deployer")

REPO_ROOT = Path(__file__).resolve().parent.parent
STAGING_DIR = REPO_ROOT / "datalake_staging"
PROJECT_ID = "gen-lang-client-0625573011"
PRIMARY_DATALAKE_BUCKET = "gs://socrateai-datalake-gen-lang-client-0625573011"
MODELS_MIRROR_BUCKET = "gs://symbrain-v2-models/anse"
DATALAKE_PREFIX = "autoevolve_anse_datalake"


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Execute a system command and log output."""
    logger.info("Executing: %s", " ".join(cmd))
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0 and check:
        logger.error("Command failed: %s\nStderr: %s", " ".join(cmd), res.stderr)
        raise RuntimeError(f"Command failed ({res.returncode}): {res.stderr}")
    return res


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with filepath.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def make_tar_gz(source_dir: Path, output_tar: Path) -> Path:
    """Archive directory into .tar.gz format."""
    output_tar.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Archiving %s -> %s", source_dir, output_tar)
    with tarfile.open(output_tar, "w:gz") as tar:
        tar.add(source_dir, arcname=source_dir.name)
    return output_tar


def prepare_redis_export(stage_dir: Path) -> dict[str, Any]:
    """Capture live Redis snapshot and metadata."""
    redis_stage = stage_dir / "database_exports" / "redis"
    redis_stage.mkdir(parents=True, exist_ok=True)

    # 1. Trigger BGSAVE via Python if redis server is accessible
    try:
        import redis  # type: ignore

        r = redis.Redis(host="localhost", port=6379, db=0)
        if r.ping():
            r.save()
            logger.info("Triggered synchronous Redis SAVE. Total keys: %d", r.dbsize())
    except Exception as e:
        logger.warning("Could not ping live redis via redis-py: %s", e)

    # 2. Locate dump.rdb
    candidates = [
        Path("/tmp/dump.rdb"),
        Path("/proc/556706/cwd/dump.rdb"),
        REPO_ROOT / "dump.rdb",
    ]
    dump_source = None
    for cand in candidates:
        if cand.exists() and cand.stat().st_size > 0:
            dump_source = cand
            break

    metadata: dict[str, Any] = {"status": "EXPORTED", "files": []}
    if dump_source:
        dest_rdb = redis_stage / "dump.rdb"
        shutil.copy2(dump_source, dest_rdb)
        sha = compute_sha256(dest_rdb)
        size_bytes = dest_rdb.stat().st_size
        logger.info("Copied Redis dump: %s (%d bytes, SHA: %s)", dest_rdb, size_bytes, sha[:10])
        metadata["files"].append({
            "name": "dump.rdb",
            "size_bytes": size_bytes,
            "sha256": sha,
            "description": "Full Redis DB memory snapshot containing conversations, thoughts, tool traces, LTM",
        })
    else:
        logger.warning("No dump.rdb found in candidate locations.")

    # 3. Add LTM dataset & sync reports
    for rep_file in [
        REPO_ROOT / "results" / "redis_ltm_lora_dataset.jsonl",
        REPO_ROOT / "results" / "redis_memory_sync_report.json",
        REPO_ROOT / "results" / "redis_lora_execution_report.json",
    ]:
        if rep_file.exists():
            dest = redis_stage / rep_file.name
            shutil.copy2(rep_file, dest)
            metadata["files"].append({
                "name": rep_file.name,
                "size_bytes": dest.stat().st_size,
                "sha256": compute_sha256(dest),
                "description": f"Redis LTM report/dataset: {rep_file.name}",
            })

    return metadata


def prepare_chroma_export(stage_dir: Path) -> dict[str, Any]:
    """Package Chroma vector databases into .tar.gz archives."""
    chroma_stage = stage_dir / "database_exports" / "chroma"
    chroma_stage.mkdir(parents=True, exist_ok=True)

    dbs = [
        (REPO_ROOT / "mathlib_rag_db", "chroma_mathlib_rag_db.tar.gz", "Mathlib4 Lean Prover RAG Vector Database"),
        (REPO_ROOT / "data" / "chroma_db", "chroma_main_db.tar.gz", "ANSE Main Knowledge Vector Database"),
        (REPO_ROOT / "data" / "chroma_fast_db", "chroma_fast_db.tar.gz", "Fast In-Memory/Disk HNSW Index"),
        (REPO_ROOT / "data" / "chroma_dense_db", "chroma_dense_db.tar.gz", "Dense Semantic Code/Physics Embeddings"),
        (REPO_ROOT / "data" / "chroma_benchmark_db", "chroma_benchmark_db.tar.gz", "PhD Benchmark Problem Vector DB"),
        (REPO_ROOT / "data" / "chroma_test", "chroma_test_db.tar.gz", "Test Suite Validation Chroma Store"),
    ]

    metadata: dict[str, Any] = {"status": "EXPORTED", "archives": []}
    for db_path, arc_name, desc in dbs:
        if db_path.exists():
            dest_tar = chroma_stage / arc_name
            make_tar_gz(db_path, dest_tar)
            sha = compute_sha256(dest_tar)
            size_b = dest_tar.stat().st_size
            logger.info("Chroma DB packaged: %s (%d bytes)", arc_name, size_b)
            metadata["archives"].append({
                "archive_name": arc_name,
                "source_dir": str(db_path.relative_to(REPO_ROOT)),
                "size_bytes": size_b,
                "sha256": sha,
                "description": desc,
            })
    return metadata


def prepare_model_serializations(stage_dir: Path) -> dict[str, Any]:
    """Stage all models: JEPA, Qwen LoRA, DeepSeek Solver, RL models, adapters."""
    models_stage = stage_dir / "models"
    metadata: dict[str, Any] = {}

    # 1. JEPA / JEDA models
    jepa_stage = models_stage / "jepa"
    jepa_stage.mkdir(parents=True, exist_ok=True)
    jepa_files = []
    for j_path, desc in [
        (REPO_ROOT / "checkpoints" / "jepa_best.pt", "Best trained JEPA World Model checkpoint (PyTorch)"),
        (REPO_ROOT / "results" / "jepa_world_model_unified_200.pt", "JEPA World Model 200-problem unified checkpoint"),
    ]:
        if j_path.exists():
            dest = jepa_stage / j_path.name
            shutil.copy2(j_path, dest)
            jepa_files.append({
                "name": j_path.name,
                "size_bytes": dest.stat().st_size,
                "sha256": compute_sha256(dest),
                "description": desc,
            })
    metadata["jepa"] = jepa_files

    # 2. Qwen / Gwen LoRA & Merged Safetensors
    qwen_stage = models_stage / "qwen_lora_ltm"
    qwen_stage.mkdir(parents=True, exist_ok=True)
    merged_src = REPO_ROOT / "results" / "qwen_lora_ltm_local" / "merged_quick_restart"
    qwen_files = []
    if merged_src.exists():
        merged_dest = qwen_stage / "merged_quick_restart"
        merged_dest.mkdir(parents=True, exist_ok=True)
        for item in merged_src.iterdir():
            if item.is_file():
                dest_file = merged_dest / item.name
                shutil.copy2(item, dest_file)
                qwen_files.append({
                    "name": f"merged_quick_restart/{item.name}",
                    "size_bytes": dest_file.stat().st_size,
                    "sha256": compute_sha256(dest_file) if item.stat().st_size < 100 * 1024 * 1024 else "SKIPPED_LARGE",
                    "description": f"Qwen merged model file: {item.name}",
                })

    # Adapter folder
    adapter_src = REPO_ROOT / "results" / "qwen_lora_ltm_local"
    if adapter_src.exists():
        adapter_dest = qwen_stage / "adapter"
        adapter_dest.mkdir(parents=True, exist_ok=True)
        for item in adapter_src.iterdir():
            if item.is_file():
                dest_file = adapter_dest / item.name
                shutil.copy2(item, dest_file)
                qwen_files.append({
                    "name": f"adapter/{item.name}",
                    "size_bytes": dest_file.stat().st_size,
                    "sha256": compute_sha256(dest_file),
                    "description": f"Qwen LoRA adapter file: {item.name}",
                })
    metadata["qwen_lora_ltm"] = qwen_files

    # 3. DeepSeek Lean Solver Assets
    ds_stage = models_stage / "deepseek_lean_solver"
    ds_stage.mkdir(parents=True, exist_ok=True)
    ds_files = []
    for d_path, desc in [
        (REPO_ROOT / "deploy" / "gcp_cloudrun_deepseek.yaml", "Cloud Run Knative specification for DeepSeek-R1-Distill-Qwen"),
        (REPO_ROOT / "config" / "deepseek_prover_v2_cloudrun.yaml", "Cloud Run active production spec for DeepSeek-Prover-V2-7B"),
        (REPO_ROOT / "anse" / "symbolic" / "lean_mcts_prover.py", "Lean MCTS Prover symbolic engine"),
        (REPO_ROOT / "anse" / "core" / "mcts_lean_solver.py", "MCTS Lean solver core orchestration"),
        (REPO_ROOT / "results" / "dspy_deepseek_10_problems_generation.json", "DSPy DeepSeek proof generation trace"),
    ]:
        if d_path.exists():
            dest = ds_stage / d_path.name
            shutil.copy2(d_path, dest)
            ds_files.append({
                "name": d_path.name,
                "size_bytes": dest.stat().st_size,
                "sha256": compute_sha256(dest),
                "description": desc,
            })
    metadata["deepseek_lean_solver"] = ds_files

    # 4. RL Models & Critics
    rl_stage = models_stage / "rl_models"
    rl_stage.mkdir(parents=True, exist_ok=True)
    rl_files = []
    for r_path, desc in [
        (REPO_ROOT / "results" / "rl_energy_model_unified_200.pt", "RL Energy Model Unified 200 Problems"),
        (REPO_ROOT / "results" / "rl_energy_model_unified.pt", "RL Energy Model Unified Base"),
        (REPO_ROOT / "results" / "rl_100_formal_critic.pt", "RL 100 Formal Verification Critic"),
        (REPO_ROOT / "results" / "rl_multidisciplinary_critic.pt", "RL Multidisciplinary Physics & Math Critic"),
        (REPO_ROOT / "results" / "surrogate_energy_predictor_v2.pt", "Surrogate Energy Predictor v2"),
    ]:
        if r_path.exists():
            dest = rl_stage / r_path.name
            shutil.copy2(r_path, dest)
            rl_files.append({
                "name": r_path.name,
                "size_bytes": dest.stat().st_size,
                "sha256": compute_sha256(dest),
                "description": desc,
            })

    # Nightly RL checkpoints tarball
    nightly_dir = REPO_ROOT / "results" / "rl_nightly" / "checkpoints"
    if nightly_dir.exists():
        nightly_tar = rl_stage / "rl_nightly_epochs_1_to_100.tar.gz"
        make_tar_gz(nightly_dir, nightly_tar)
        rl_files.append({
            "name": nightly_tar.name,
            "size_bytes": nightly_tar.stat().st_size,
            "sha256": compute_sha256(nightly_tar),
            "description": "Archive of 45+ RL nightly epoch checkpoints (epochs 1-100)",
        })

    # Laya RL agent
    laya_dir = REPO_ROOT / "checkpoints" / "laya"
    if laya_dir.exists():
        laya_stage = rl_stage / "laya"
        laya_stage.mkdir(parents=True, exist_ok=True)
        for item in laya_dir.iterdir():
            if item.is_file():
                dest = laya_stage / item.name
                shutil.copy2(item, dest)
                rl_files.append({
                    "name": f"laya/{item.name}",
                    "size_bytes": dest.stat().st_size,
                    "sha256": compute_sha256(dest) if item.stat().st_size < 100 * 1024 * 1024 else "SKIPPED_LARGE",
                    "description": f"Laya RL agent file: {item.name}",
                })
    metadata["rl_models"] = rl_files

    # 5. Adapters
    adapters_dir = REPO_ROOT / "adapters"
    if adapters_dir.exists():
        adapters_tar = models_stage / "evolution_adapters_57_checkpoints.tar.gz"
        make_tar_gz(adapters_dir, adapters_tar)
        metadata["adapters"] = [{
            "name": adapters_tar.name,
            "size_bytes": adapters_tar.stat().st_size,
            "sha256": compute_sha256(adapters_tar),
            "description": "Complete bundle of 57 evolution adapters across training epochs",
        }]

    return metadata


def prepare_open_source_vm_deployment_stack(stage_dir: Path) -> dict[str, Any]:
    """Package open source JEL/ANSE core and generate GCP VM bootstrap scripts."""
    vm_stage = stage_dir / "open_source_packages"
    vm_stage.mkdir(parents=True, exist_ok=True)

    # 1. Archive core source code
    core_tar = vm_stage / "anse_core_open_source.tar.gz"
    logger.info("Creating open-source package archive: %s", core_tar)
    with tarfile.open(core_tar, "w:gz") as tar:
        for folder in ["anse", "scripts", "config", "deploy"]:
            p = REPO_ROOT / folder
            if p.exists():
                tar.add(p, arcname=folder)
        for root_file in ["pyproject.toml", "README.md", "results_all_phases.json"]:
            rf = REPO_ROOT / root_file
            if rf.exists():
                tar.add(rf, arcname=root_file)

    # 2. Write GCP VM bootstrap shell script
    bootstrap_sh = vm_stage / "gcp_vm_bootstrap.sh"
    bootstrap_content = """#!/usr/bin/env bash
# ==============================================================================
# SocrateAI / ANSE AutoevolveAI Turn-Key VM Bootstrap Script
# Target Platform: GCP Compute Engine (Ubuntu 22.04 / 24.04 LTS or Debian 12)
# Recommended Machine: g2-standard-4 (1x NVIDIA L4) or n1-standard-8 (CPU/T4)
# ==============================================================================

set -euo pipefail

echo "================================================================="
echo "  🚀 INITIALIZING SOCRATEAI / ANSE ENVIRONMENT ON GCP VM"
echo "================================================================="

export DEBIAN_FRONTEND=noninteractive
export DATALAKE_BUCKET="gs://socrateai-datalake-gen-lang-client-0625573011/autoevolve_anse_datalake"
export WORKDIR="/opt/socrateai/anse"

# 1. Install System Dependencies & Redis
echo "[1/6] Installing system packages and Redis Server..."
sudo apt-get update -y
sudo apt-get install -y redis-server redis-tools curl wget git build-essential ca-certificates python3 python3-pip python3-venv

# 2. Create Workspace Directory Structure
echo "[2/6] Setting up directory hierarchy at ${WORKDIR}..."
sudo mkdir -p "${WORKDIR}"
sudo chown -R "${USER}:${USER}" "${WORKDIR}"
cd "${WORKDIR}"

# 3. Pull Core Code & Extract
echo "[3/6] Downloading ANSE Open Source Core and Packages from GCS Data Lake..."
gcloud storage cp "${DATALAKE_BUCKET}/open_source_packages/anse_core_open_source.tar.gz" ./
tar -xzf anse_core_open_source.tar.gz
rm anse_core_open_source.tar.gz

# 4. Pull and Restore Redis Long-Term Memory
echo "[4/6] Restoring Redis Long-Term Memory snapshot..."
sudo systemctl stop redis-server || true
mkdir -p ./data/redis
gcloud storage cp "${DATALAKE_BUCKET}/database_exports/redis/dump.rdb" ./data/redis/dump.rdb
sudo cp ./data/redis/dump.rdb /var/lib/redis/dump.rdb
sudo chown redis:redis /var/lib/redis/dump.rdb
sudo chmod 660 /var/lib/redis/dump.rdb
sudo systemctl start redis-server
sleep 2
redis-cli ping && echo "✅ Redis LTM online with $(redis-cli dbsize) keys!"

# 5. Pull and Restore Chroma Vector Databases
echo "[5/6] Restoring Chroma Vector RAG Databases..."
mkdir -p ./data
gcloud storage cp "${DATALAKE_BUCKET}/database_exports/chroma/*.tar.gz" ./data/
for archive in ./data/*.tar.gz; do
    echo "  Extracting ${archive}..."
    tar -xzf "${archive}" -C ./data/
    rm "${archive}"
done
[ -d "./data/mathlib_rag_db" ] && mv ./data/mathlib_rag_db ./mathlib_rag_db || true
echo "✅ Chroma Vector Stores deployed!"

# 6. Download Model Weights for In-VM Deployment
echo "[6/6] Synchronizing Model Checkpoints (JEPA, Qwen, RL, DeepSeek)..."
mkdir -p ./checkpoints ./results/qwen_lora_ltm_local
gcloud storage cp -r "${DATALAKE_BUCKET}/models/jepa/*" ./checkpoints/
gcloud storage cp -r "${DATALAKE_BUCKET}/models/qwen_lora_ltm/*" ./results/qwen_lora_ltm_local/
gcloud storage cp -r "${DATALAKE_BUCKET}/models/rl_models/*" ./results/

# 7. Setup Python Virtual Environment
echo "Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install redis chromadb fastapi uvicorn safetensors transformers pydantic

echo "================================================================="
echo "  🎉 DEPLOYMENT COMPLETE! All models & databases ready."
echo "  - Redis LTM: redis-cli on port 6379"
echo "  - Qwen Merged Model: ${WORKDIR}/results/qwen_lora_ltm_local/merged_quick_restart/"
echo "  - JEPA World Model: ${WORKDIR}/checkpoints/jepa_best.pt"
echo "  - Run Gateway: python3 -m anse.gateway.serverless_lora_endpoint"
echo "================================================================="
"""
    bootstrap_sh.write_text(bootstrap_content)
    bootstrap_sh.chmod(0o755)

    # 3. Write systemd unit for Qwen / ANSE Gateway
    systemd_file = vm_stage / "anse-gateway.service"
    systemd_content = """[Unit]
Description=SocrateAI ANSE Gateway & Qwen LTM Server
After=network.target redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/socrateai/anse
ExecStart=/opt/socrateai/anse/.venv/bin/python3 -m anse.gateway.serverless_lora_endpoint
Restart=always
RestartSec=5
Environment=PORT=8000
Environment=REDIS_HOST=127.0.0.1
Environment=REDIS_PORT=6379

[Install]
WantedBy=multi-user.target
"""
    systemd_file.write_text(systemd_content)

    return {
        "status": "PREPARED",
        "core_archive": core_tar.name,
        "bootstrap_script": bootstrap_sh.name,
        "systemd_service": systemd_file.name,
    }


def upload_to_gcs() -> None:
    """Upload staged artifacts to primary data lake and mirror bucket."""
    logger.info("Uploading staged artifacts to %s/%s/...", PRIMARY_DATALAKE_BUCKET, DATALAKE_PREFIX)
    # Using gcloud storage rsync with parallel processing
    target_uri = f"{PRIMARY_DATALAKE_BUCKET}/{DATALAKE_PREFIX}/"
    run_cmd(["gcloud", "storage", "rsync", "--recursive", str(STAGING_DIR), target_uri])

    # Mirror core models to gs://symbrain-v2-models/anse/
    logger.info("Mirroring key models to %s/...", MODELS_MIRROR_BUCKET)
    models_stage = STAGING_DIR / "models"
    if models_stage.exists():
        run_cmd(["gcloud", "storage", "rsync", "--recursive", str(models_stage), f"{MODELS_MIRROR_BUCKET}/"])


def scan_data_lake_cartography() -> dict[str, Any]:
    """Scan and index all buckets and prefixes across the SocrateAI data lake."""
    logger.info("Building Cartography of the Google Cloud Data Lake...")

    buckets_to_survey = [
        PRIMARY_DATALAKE_BUCKET,
        "gs://symbrain-v2-models",
        "gs://socrateai-runux-math-kernel-checkpoints",
        "gs://socrateai-alien-math-ip",
        "gs://socrateai-alien-math-archive",
    ]

    cartography: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gcp_project": PROJECT_ID,
        "project_name": "SocrateAI",
        "buckets": {},
    }

    for bucket in buckets_to_survey:
        logger.info("Surveying %s ...", bucket)
        res = run_cmd(["gcloud", "storage", "ls", "--long", f"{bucket}/**"], check=False)
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]

        total_bytes = 0
        total_objects = 0
        prefixes: dict[str, dict[str, Any]] = {}

        for line in lines:
            parts = line.split()
            if len(parts) >= 3 and parts[0].isdigit():
                size = int(parts[0])
                uri = parts[2]
                total_bytes += size
                total_objects += 1

                # Determine top-level prefix
                rel_path = uri.replace(f"{bucket}/", "")
                top_prefix = rel_path.split("/")[0] if "/" in rel_path else "root"
                if top_prefix not in prefixes:
                    prefixes[top_prefix] = {"objects": 0, "bytes": 0, "sample_files": []}
                prefixes[top_prefix]["objects"] += 1
                prefixes[top_prefix]["bytes"] += size
                if len(prefixes[top_prefix]["sample_files"]) < 5:
                    prefixes[top_prefix]["sample_files"].append(uri)

        cartography["buckets"][bucket] = {
            "total_objects": total_objects,
            "total_bytes": total_bytes,
            "total_gigabytes": round(total_bytes / (1024**3), 3),
            "prefixes": prefixes,
        }

    return cartography


def generate_cartography_markdown(cartography: dict[str, Any], output_md: Path) -> str:
    """Format cartography data into a GitHub Markdown atlas."""
    lines = [
        "# 🗺️ SocrateAI / ANSE Google Cloud Data Lake Cartography",
        "",
        f"**GCP Project:** `{cartography['gcp_project']}` (`{cartography['project_name']}`)",
        f"**Generated At:** `{cartography['timestamp']}`",
        "",
        "---",
        "",
        "## 🧭 Executive Summary & Architecture",
        "",
        "The **SocrateAI Data Lake** is an enterprise scientific and neuro-symbolic repository hosted on Google Cloud Storage.",
        "It integrates physical simulation traces, formal Lean 4 verification graphs, cosmological datasets (DESI DR1, Euclid Q1/Q2, Planck 2018),",
        "and the newly deployed **AutoevolveAI / ANSE Model Serialization Suite**, Redis Long-Term Memory snapshots, and Chroma vector stores.",
        "",
        "```",
        "gs://socrateai-datalake-gen-lang-client-0625573011/",
        "│",
        "├── autoevolve_anse_datalake/          <-- [NEW] ANSE Neuro-Symbolic Model Suite & DBs",
        "│   ├── models/                       <-- Model serializations",
        "│   │   ├── jepa/                     <-- EB-JEPA World Models (jepa_best.pt, unified_200.pt)",
        "│   │   ├── qwen_lora_ltm/            <-- Qwen2.5-0.5B-Instruct + Redis LTM LoRA (safetensors)",
        "│   │   ├── deepseek_lean_solver/     <-- Cloud Run specs, MCTS prover, benchmark traces",
        "│   │   ├── rl_models/                <-- RL Critics, Energy models, Surrogate, Laya Safetensors",
        "│   │   └── adapters/                 <-- 57 Evolution adapter checkpoints bundle",
        "│   ├── database_exports/             <-- Databases exported for VM replication",
        "│   │   ├── redis/                    <-- Live Redis DB (dump.rdb) & LTM conversation dataset",
        "│   │   └── chroma/                   <-- Mathlib4, Main, Fast, Dense, Benchmark Chroma DBs",
        "│   └── open_source_packages/         <-- Turn-key GCP VM deployment stack",
        "│       ├── anse_core_open_source.tar.gz",
        "│       ├── gcp_vm_bootstrap.sh       <-- Automated bootstrap bash script for Compute Engine",
        "│       └── anse-gateway.service      <-- Systemd daemon unit file",
        "│",
        "├── checkpoints/                      <-- Pre-existing evolutionary checkpoints (gens 001-300)",
        "├── formal_verification/              <-- Lean 4 formal mathlib proofs & AST certificates",
        "├── stream2_cy4_ml/                   <-- Calabi-Yau 4-fold neural geometry stream",
        "├── stream3_desi_dr1/                 <-- DESI DR1 cosmological spectroscopic data",
        "├── stream3_euclid_q2/                <-- Euclid Space Telescope Q2 observation cubes",
        "├── stream4_bridge/                   <-- Multi-messenger physics cross-correlation bridge",
        "├── dark_matter/                      <-- Dark matter simulation halos & density profiles",
        "├── nanograv_15yr/                    <-- NANOGrav 15-year gravitational wave stochastic background",
        "├── planck_2018/                      <-- Planck CMB angular power spectra & likelihoods",
        "└── publications/                     <-- Scientific publication LaTeX & PDF compendiums",
        "```",
        "",
        "---",
        "",
        "## 📦 Bucket Inventory & Topology",
        "",
    ]

    for bucket_name, binfo in cartography["buckets"].items():
        lines.append(f"### 🪣 `{bucket_name}`")
        lines.append(f"- **Total Objects:** `{binfo['total_objects']:,}`")
        lines.append(f"- **Total Volume:** `{binfo['total_gigabytes']} GB` ({binfo['total_bytes']:,} bytes)")
        lines.append("")
        lines.append("| Prefix / Subdirectory | Objects | Size (MB) | Purpose & Key Artifacts |")
        lines.append("| :--- | :--- | :--- | :--- |")

        for pfx, pinfo in sorted(binfo["prefixes"].items()):
            mb = round(pinfo["bytes"] / (1024**2), 2)
            desc = _get_prefix_description(pfx)
            lines.append(f"| `{pfx}/` | `{pinfo['objects']:,}` | `{mb:,} MB` | {desc} |")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 🚀 GCP VM Turn-Key Deployment Guide",
        "",
        "Any engineer or automated CI/CD pipeline can deploy the complete ANSE environment onto a GCP VM in under 3 minutes:",
        "",
        "### 1. Provision GCP VM (Compute Engine)",
        "```bash",
        "gcloud compute instances create anse-neurosymbolic-vm \\",
        "    --project=gen-lang-client-0625573011 \\",
        "    --zone=us-central1-a \\",
        "    --machine-type=g2-standard-4 \\",
        "    --accelerator=type=nvidia-l4,count=1 \\",
        "    --image-family=ubuntu-2204-lts \\",
        "    --image-project=ubuntu-os-cloud \\",
        "    --boot-disk-size=100GB \\",
        "    --scopes=cloud-platform",
        "```",
        "",
        "### 2. Run Automated Bootstrap Script on the VM",
        "```bash",
        "# SSH into instance",
        "gcloud compute ssh anse-neurosymbolic-vm --project=gen-lang-client-0625573011 --zone=us-central1-a",
        "",
        "# Fetch and run bootstrap directly from data lake",
        "gcloud storage cp gs://socrateai-datalake-gen-lang-client-0625573011/autoevolve_anse_datalake/open_source_packages/gcp_vm_bootstrap.sh ./",
        "chmod +x gcp_vm_bootstrap.sh",
        "./gcp_vm_bootstrap.sh",
        "```",
        "",
        "### 3. Verify Live Services on the VM",
        "```bash",
        "# Verify Redis LTM restore",
        "redis-cli ping",
        "redis-cli info keyspace",
        "",
        "# Verify Chroma DBs",
        "ls -la /opt/socrateai/anse/data/chroma_db",
        "ls -la /opt/socrateai/anse/mathlib_rag_db",
        "",
        "# Launch Qwen LoRA Serverless Endpoint",
        "python3 -m anse.gateway.serverless_lora_endpoint",
        "```",
        "",
        "---",
        "",
        "## 🐍 Python SDK Data Lake Access Recipe",
        "",
        "```python",
        "from google.cloud import storage",
        "import torch",
        "",
        "client = storage.Client(project='gen-lang-client-0625573011')",
        "bucket = client.bucket('socrateai-datalake-gen-lang-client-0625573011')",
        "",
        "# Download JEPA best checkpoint",
        "blob = bucket.blob('autoevolve_anse_datalake/models/jepa/jepa_best.pt')",
        "blob.download_to_filename('jepa_best.pt')",
        "weights = torch.load('jepa_best.pt', map_location='cpu')",
        "print('Loaded JEPA state dict keys:', len(weights.keys()))",
        "```",
        "",
    ])

    md_content = "\n".join(lines)
    output_md.write_text(md_content, encoding="utf-8")
    return md_content


def _get_prefix_description(prefix: str) -> str:
    descriptions = {
        "autoevolve_anse_datalake": "Complete ANSE Neuro-Symbolic Suite, JEPA, Qwen, RL, Redis LTM, Chroma, and VM bootstrap",
        "checkpoints": "Historical evolutionary checkpoints from 300+ scientific simulations",
        "formal_verification": "Lean 4 theorem formalizations, AST proofs, and proof invariants",
        "stream2_cy4_ml": "Calabi-Yau 4-fold neural geometry and topological Hodge diamond tensors",
        "stream3_desi_dr1": "DESI DR1 cosmological data, baryon acoustic oscillations, and redshift surveys",
        "stream3_euclid_q2": "Euclid Space Telescope Q2 gravitational lensing and galaxy cluster catalogs",
        "stream4_bridge": "Multi-messenger cross-correlation tensors uniting cosmological datasets",
        "dark_matter": "N-body dark matter simulation halos and velocity dispersion profiles",
        "nanograv_15yr": "NANOGrav 15-year stochastic gravitational wave background timing residuals",
        "planck_2018": "Planck 2018 CMB temperature and polarization power spectra",
        "publications": "Scientific whitepapers, formal dossiers, and publication PDFs",
        "mcmc_chains": "Monte Carlo Markov Chain parameter exploration traces",
        "mcmc_posteriors": "Posterior distributions for cosmological and thermodynamic parameters",
        "audit": "Quality gate audits, verification receipts, and security reviews",
        "anse": "Core ANSE model mirror on symbrain-v2-models",
        "symbrain-v2": "Legacy Symbrain v2 model checkpoints",
        "symbrain-v5": "Symbrain v5 neural architectures",
        "training_code": "PyTorch training scripts and execution harnesses",
    }
    return descriptions.get(prefix, "Scientific and neural model artifacts")


def main() -> int:
    start_time = time.time()
    logger.info("=== STARTING SOCRATEAI DATA LAKE DEPLOYMENT & CARTOGRAPHY ===")

    # 1. Clean Staging Area
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Stage Components
    logger.info("[1/5] Exporting live Redis Long-Term Memory...")
    redis_meta = prepare_redis_export(STAGING_DIR)

    logger.info("[2/5] Packaging Chroma Vector RAG Databases...")
    chroma_meta = prepare_chroma_export(STAGING_DIR)

    logger.info("[3/5] Staging Model Serializations (JEPA, Qwen, DeepSeek, RL, Adapters)...")
    models_meta = prepare_model_serializations(STAGING_DIR)

    logger.info("[4/5] Preparing JEL/ANSE Open-Source VM Deployment Stack...")
    vm_meta = prepare_open_source_vm_deployment_stack(STAGING_DIR)

    # Save staging manifest
    manifest_path = STAGING_DIR / "manifest.json"
    manifest_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "project_id": PROJECT_ID,
        "redis": redis_meta,
        "chroma": chroma_meta,
        "models": models_meta,
        "vm_stack": vm_meta,
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2))

    # 3. Upload to GCS
    logger.info("[5/5] Uploading Staged Artifacts to Google Cloud Storage...")
    upload_to_gcs()

    # 4. Scan Data Lake and Generate Cartography
    logger.info("Surveying Data Lake across all buckets...")
    cartography = scan_data_lake_cartography()

    # Write local and staging cartography
    cartography_json_path = REPO_ROOT / "data_lake_cartography.json"
    cartography_json_path.write_text(json.dumps(cartography, indent=2))

    cartography_md_path = REPO_ROOT / "DATA_LAKE_CARTOGRAPHY.md"
    generate_cartography_markdown(cartography, cartography_md_path)

    # Upload Cartography directly to GCS
    logger.info("Uploading Cartography files to %s/ ...", PRIMARY_DATALAKE_BUCKET)
    run_cmd(["gcloud", "storage", "cp", str(cartography_md_path), f"{PRIMARY_DATALAKE_BUCKET}/DATA_LAKE_CARTOGRAPHY.md"])
    run_cmd(["gcloud", "storage", "cp", str(cartography_json_path), f"{PRIMARY_DATALAKE_BUCKET}/data_lake_cartography.json"])
    run_cmd(["gcloud", "storage", "cp", str(cartography_md_path), f"{PRIMARY_DATALAKE_BUCKET}/{DATALAKE_PREFIX}/DATA_LAKE_CARTOGRAPHY.md"])
    run_cmd(["gcloud", "storage", "cp", str(cartography_json_path), f"{PRIMARY_DATALAKE_BUCKET}/{DATALAKE_PREFIX}/data_lake_cartography.json"])

    elapsed = time.time() - start_time
    logger.info("=== DEPLOYMENT AND CARTOGRAPHY COMPLETED SUCCESSFULLY IN %.2f SECONDS ===", elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
