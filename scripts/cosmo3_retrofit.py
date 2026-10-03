#!/usr/bin/env python3
"""Retrofit the three cosmology runs (2026-09-27) into long-term memory and JEPA training.

1. Literature: ingest each run's literature review and paper source into the Chroma
   `literature` collection (real qwen3-embedding vectors, under the shared GPU lease).
2. Episodes: convert every verdict-bearing step the runs recorded in
   results/<run>/episodes.jsonl (passes AND failures, each pointing at on-disk evidence)
   into JEPA dataset rows: hidden_state = 1024-d embedding of the step, energy = the
   verifier's verdict (0 pass / 1 fail), metadata.tests_total = 1.
3. Learning: train the JEPA world model on those rows (CPU) and, as a negative control,
   on the same rows with energies permuted across rows. Both are reported as measured.

Usage:
    .venv/bin/python scripts/cosmo3_retrofit.py
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, "/mnt/disks/disk-socrateai-local-1/gpu_lease")

from gpu_lease import gpu_lease  # noqa: E402

from anse.config import JEPAConfig  # noqa: E402
from anse.jepa.dataset import JEPADataset  # noqa: E402
from anse.jepa.trainer import JEPATrainer  # noqa: E402
from anse.jepa.world_model import JEPAWorldModel  # noqa: E402
from anse.memory.document_store import DocumentStore  # noqa: E402
from anse.memory.ollama_embeddings import OllamaEmbeddingFunction  # noqa: E402

RUNS = ["desi_dr2_bao", "bao_bbn_h0", "eboss_vs_desi"]
LIT = {
    "desi_dr2_bao": "DESI_DR2_BAO",
    "bao_bbn_h0": "BAO_BBN_H0",
    "eboss_vs_desi": "EBOSS_VS_DESI",
}
CHROMA_ROOT = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/datalake/chroma/ltm/documents")
EPISODES_OUT = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/datalake/episodes/cosmo3_2026-09-27.jsonl")
SUMMARY_OUT = REPO / "results" / "cosmo3_learning" / "retrofit_summary.json"
LEASE_HOLDER = "autoevolve-cosmo3-retrofit"


def load_episodes() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in RUNS:
        for line in (REPO / "results" / run / "episodes.jsonl").read_text().splitlines():
            if line.strip():
                ep = json.loads(line)
                ep["run"] = run
                rows.append(ep)
    return rows


def task_of(ep: dict[str, Any]) -> str:
    """Repeated attempts at the same executable form one task run."""
    cmd = str(ep.get("command") or "")
    script = next((tok for tok in cmd.split() if tok.endswith((".py", ".lean", ".tex"))), "")
    return f"{ep['run']}:{Path(script).name or ep.get('step', 'step')}"


def episode_text(ep: dict[str, Any]) -> str:
    return f"[{ep['run']}] step={ep.get('step')} input={ep.get('input_summary')} command={ep.get('command')}"


def ingest_literature() -> dict[str, int]:
    store = DocumentStore(CHROMA_ROOT, "literature")
    counts: dict[str, int] = {}
    for run in RUNS:
        for path in [
            REPO / "docs" / "literature" / f"{LIT[run]}_LITERATURE_REVIEW_2026.md",
            REPO / "papers" / run / f"{run}.tex",
        ]:
            if path.exists():
                counts[str(path.relative_to(REPO))] = store.ingest_text_file(
                    path, extra_metadata={"topic": "cosmology", "run": run}
                )
    counts["_collection_total"] = store.count()
    return counts


def build_rows(episodes: list[dict[str, Any]], emb: OllamaEmbeddingFunction) -> list[dict[str, Any]]:
    vectors = emb([episode_text(ep) for ep in episodes])
    iteration: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for ep, vec in zip(episodes, vectors, strict=True):
        task = task_of(ep)
        it = iteration.get(task, 0)
        iteration[task] = it + 1
        passed = ep.get("verdict") == "pass"
        rows.append({
            "task": task,
            "iteration": it,
            "hidden_state": list(map(float, vec)),
            "energy": 0.0 if passed else 1.0,
            "converged": passed,
            "metadata": {
                "tests_total": 1,
                "tests_passed": 1 if passed else 0,
                "verifier": "cosmo3 pipeline step with on-disk evidence",
                "evidence_path": ep.get("evidence_path"),
                "step": ep.get("step"),
                "source": "cosmo3 2026-09-27",
            },
        })
    return rows


def train(rows: list[dict[str, Any]], dim: int, seed: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rows.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        ds = JEPADataset(path, hidden_dim=dim)
        model = JEPAWorldModel(dim, 128, 16)
        trainer = JEPATrainer(
            model=model,
            config=JEPAConfig(latent_dim=16, hidden_dim=128),
            lr=1e-3,
            device="cpu",
            checkpoint_dir=Path(tmp) / "ckpt",
        )
        s = trainer.train(ds, epochs=60, batch_size=16, seed=seed)
        return {
            "items": len(ds),
            "skipped": dict(ds.skipped),
            "final_train_loss": s.final_train_loss,
            "final_val_loss": s.final_val_loss,
            "best_val_energy_accuracy": max(h.get("energy_accuracy", 0.0) for h in s.history),
            "final_val_energy_accuracy": s.history[-1].get("energy_accuracy"),
        }


def main() -> int:
    episodes = load_episodes()
    emb = OllamaEmbeddingFunction()
    with gpu_lease(LEASE_HOLDER, "cosmo3 retrofit: embed literature + episodes", ttl_s=1800, timeout_s=3600):
        lit = ingest_literature()
        rows = build_rows(episodes, emb)
    dim = len(rows[0]["hidden_state"])
    EPISODES_OUT.parent.mkdir(parents=True, exist_ok=True)
    EPISODES_OUT.write_text("".join(json.dumps(r) + "\n" for r in rows))

    real = train(rows, dim, seed=42)
    energies = [r["energy"] for r in rows]
    random.Random(7).shuffle(energies)
    shuffled = [dict(r, energy=e) for r, e in zip(rows, energies, strict=True)]
    control = train(shuffled, dim, seed=42)

    summary = {
        "episodes": len(rows),
        "passes": sum(1 for r in rows if r["energy"] == 0.0),
        "fails": sum(1 for r in rows if r["energy"] == 1.0),
        "distinct_tasks": len({r["task"] for r in rows}),
        "embedding_model": emb.model,
        "embedding_dim": dim,
        "episodes_file": str(EPISODES_OUT),
        "literature_ingest": lit,
        "jepa_real": real,
        "jepa_shuffled_energy_control": control,
    }
    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
