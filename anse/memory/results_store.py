"""Long-Term Memory store for benchmark, evaluation, and evolution results.

Persists structured results across both storage tiers:
  * Redis (`anse:ltm:result:<slug>`): durable, structured metric recall and indexing.
  * Chroma (`benchmark_results` collection): semantic vector search across benchmark
    outcomes, physics validations, formal proofs, and autopoietic evolution runs.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from anse.memory.ollama_embeddings import OllamaEmbeddingFunction

logger = logging.getLogger(__name__)

REDIS_RESULT_PREFIX = "anse:ltm:result"
CHROMA_RESULT_COLLECTION = "benchmark_results"


def sha256_of_file(path: Path) -> str:
    """Calculate SHA256 content hash of a file for provenance anchoring."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class ResultSummary:
    """Structured extraction of a benchmark/eval run."""

    slug: str
    source_path: str
    source_sha256: str
    title: str
    description: str
    metrics: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    indexed_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _summarize_json_payload(slug: str, data: Any, path: Path) -> tuple[str, dict[str, Any]]:
    """Extract a rich text description and top-level numeric metrics from JSON data."""
    metrics: dict[str, Any] = {}
    lines: list[str] = [f"# Benchmark / Evaluation Report: {slug}", f"Source: {path}"]

    if isinstance(data, dict):
        # Extract executive summary if available
        if "executive_summary" in data and isinstance(data["executive_summary"], dict):
            lines.append("\n## Executive Summary")
            for k, v in data["executive_summary"].items():
                lines.append(f"- **{k}**: {v}")
                if isinstance(v, (int, float, bool, str)):
                    metrics[k] = v

        # Extract metadata
        if "metadata" in data and isinstance(data["metadata"], dict):
            lines.append("\n## Metadata")
            for k, v in data["metadata"].items():
                lines.append(f"- {k}: {v}")

        # Extract top-level scalar keys
        scalars = {
            k: v
            for k, v in data.items()
            if isinstance(v, (int, float, str, bool))
            and k not in ("raw_code", "raw_output")
        }
        if scalars:
            lines.append("\n## Key Metrics")
            for k, v in scalars.items():
                lines.append(f"- **{k}**: {v}")
                metrics[k] = v

        # Extract common benchmark sections
        for section in (
            "energy_model_learning",
            "jepa_world_model_learning",
            "latent_dreamer_telemetry",
            "domain_statistics",
            "results",
            "summary",
        ):
            if section in data and isinstance(data[section], dict):
                lines.append(f"\n## {section.replace('_', ' ').title()}")
                for k, v in data[section].items():
                    if isinstance(v, (int, float, str, bool)):
                        lines.append(f"- {k}: {v}")
                        metrics[f"{section}.{k}"] = v

    elif isinstance(data, list):
        lines.append(f"\nArray Dataset: {len(data)} entries")
        metrics["item_count"] = len(data)
        if data and isinstance(data[0], dict):
            sample_keys = list(data[0].keys())[:10]
            lines.append(f"Sample Entry Keys: {', '.join(sample_keys)}")

    description = "\n".join(lines)
    return description, metrics


class ResultsStore:
    """Dual-store for benchmark and evaluation telemetry in Redis and Chroma."""

    def __init__(
        self,
        persist_directory: Path | str,
        collection: str = CHROMA_RESULT_COLLECTION,
        redis_url: str | None = None,
        embedding_function: OllamaEmbeddingFunction | None = None,
        enable_chroma: bool = True,
        enable_redis: bool = True,
    ) -> None:
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection
        self.redis_url = redis_url or os.environ.get(
            "ANSE_REDIS_URL", "redis://localhost:6379/0"
        )
        self.embedding_function = embedding_function or OllamaEmbeddingFunction()

        self._redis = None
        if enable_redis:
            try:
                import redis

                self._redis = redis.Redis.from_url(
                    self.redis_url, decode_responses=True
                )
                self._redis.ping()
            except Exception as exc:
                logger.warning("Redis connection failed for ResultsStore: %s", exc)
                self._redis = None

        self._collection = None
        if enable_chroma:
            try:
                import chromadb

                self.persist_directory.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(path=str(self.persist_directory))
                self._collection = self._client.get_or_create_collection(
                    name=collection,
                    embedding_function=self.embedding_function,
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as exc:
                logger.warning("Chroma initialization failed for ResultsStore: %s", exc)
                self._collection = None

    def ingest_result_file(self, path: Path) -> ResultSummary:
        """Ingest one benchmark result file into Redis and Chroma."""
        digest = sha256_of_file(path)
        slug = path.stem
        # If file is nested e.g. results/nightly_training/nightly_dream_report.json
        if path.parent.name != "results":
            slug = f"{path.parent.name}_{path.stem}"

        try:
            with path.open("r", encoding="utf-8") as f:
                if path.suffix == ".jsonl":
                    # Read sample from jsonl
                    rows = [json.loads(line) for i, line in enumerate(f) if i < 1000]
                    data = rows
                else:
                    data = json.load(f)
        except Exception as exc:
            raise ValueError(f"Failed to parse {path.name}: {exc}") from exc

        description, metrics = _summarize_json_payload(slug, data, path)

        mtime = datetime.datetime.fromtimestamp(
            path.stat().st_mtime, tz=datetime.UTC
        ).isoformat()
        now = datetime.datetime.now(datetime.UTC).isoformat()

        summary = ResultSummary(
            slug=slug,
            source_path=str(path),
            source_sha256=digest,
            title=slug.replace("_", " ").title(),
            description=description,
            metrics=metrics,
            timestamp=mtime,
            indexed_at=now,
        )

        # 1. Store in Redis
        if self._redis is not None:
            key = f"{REDIS_RESULT_PREFIX}:{slug}"
            self._redis.hset(
                key,
                mapping={
                    "slug": slug,
                    "source_path": str(path),
                    "source_sha256": digest,
                    "title": summary.title,
                    "timestamp": mtime,
                    "indexed_at": now,
                    "metrics_json": json.dumps(metrics),
                    "summary_text": description[:4000],
                },
            )
            self._redis.sadd(f"{REDIS_RESULT_PREFIX}:slugs", slug)

        # 2. Store in Chroma
        if self._collection is not None:
            # Chunk description if long
            from anse.memory.transcript_ltm import _chunk_for_embedding

            chunks = _chunk_for_embedding(description)
            ids = [f"result:{slug}:{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "slug": slug,
                    "source_path": str(path),
                    "source_sha256": digest,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                }
                for i in range(len(chunks))
            ]
            self._collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)

        return summary

    def ingest_directory(
        self,
        directory: Path | str,
        pattern: str = "*.json",
    ) -> dict[str, Any]:
        """Ingest all matching results from directory."""
        directory = Path(directory)
        indexed: list[str] = []
        skipped: list[dict[str, str]] = []

        files = sorted(directory.rglob(pattern))
        for path in files:
            # Skip non-report large raw dumps or mission dbs
            if path.name.endswith(".sqlite3") or path.name.endswith(".db"):
                continue
            try:
                summary = self.ingest_result_file(path)
                indexed.append(summary.slug)
            except Exception as exc:
                skipped.append({"path": str(path), "reason": str(exc)})
                logger.warning("Skipped result %s: %s", path.name, exc)

        return {
            "indexed_count": len(indexed),
            "skipped_count": len(skipped),
            "indexed": indexed,
            "skipped": skipped,
        }

    def get_result(self, slug: str) -> dict[str, Any] | None:
        """Fetch result metadata from Redis."""
        if self._redis is None:
            return None
        data = self._redis.hgetall(f"{REDIS_RESULT_PREFIX}:{slug}")
        if not data:
            return None
        if "metrics_json" in data:
            try:
                data["metrics"] = json.loads(data["metrics_json"])
            except Exception:
                pass
        return data

    def query(self, question: str, n_results: int = 5) -> list[dict[str, Any]]:
        """Semantic search over benchmark and evaluation results."""
        if self._collection is None:
            return []
        res = self._collection.query(query_texts=[question], n_results=n_results)
        hits: list[dict[str, Any]] = []
        ids = res.get("ids") or [[]]
        if not ids[0]:
            return hits
        for i in range(len(ids[0])):
            hits.append(
                {
                    "id": ids[0][i],
                    "document": res["documents"][0][i],
                    "metadata": res["metadatas"][0][i],
                    "distance": res["distances"][0][i],
                }
            )
        return hits
