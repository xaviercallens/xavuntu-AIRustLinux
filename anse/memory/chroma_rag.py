"""
ChromaDB Vector Store & RAG Engine for AutoevolveAI / ANSE.

Provides semantic retrieval over:
1. Long-Term Memory (Redis LTM traces, verified low-energy code, human patches).
2. Scientific Literature & Formal Requirements (arXiv papers, theorem proofs, Lean 4 specs).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from anse.config import MemoryConfig, get_config

logger = logging.getLogger(__name__)


class FastDeterministicEmbeddingFunction(EmbeddingFunction[Documents]):
    """
    Ultra-fast, zero-dependency, deterministic 384-dimensional embedding function.
    Projects n-gram frequency distributions onto a normalized hypersphere.
    Provides sub-millisecond offline embedding without downloading external models.
    """

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def __call__(self, input: Documents) -> Embeddings:
        embeddings: list[list[float]] = []
        for text in input:
            vec = [0.0] * self.dimension
            tokens = text.lower().split()
            for token in tokens:
                # Character n-grams for sub-word semantic density
                for i in range(max(1, len(token) - 2)):
                    ngram = token[i : i + 3]
                    h = int(hashlib.md5(ngram.encode("utf-8")).hexdigest(), 16)
                    idx = h % self.dimension
                    vec[idx] += 1.0

            # L2 normalization
            norm = sum(x * x for x in vec) ** 0.5
            if norm > 1e-9:
                vec = [x / norm for x in vec]
            embeddings.append(vec)
        return embeddings


class ChromaRAG:
    """
    Persistent ChromaDB Vector Store managing code solutions from Redis LTM
    and scientific research context for autonomous agent prompt augmentation.
    """

    def __init__(
        self,
        persist_directory: str | Path | None = None,
        config: MemoryConfig | None = None,
        use_fast_embeddings: bool = True,
    ) -> None:
        """
        Args:
            persist_directory: Explicit override for the ChromaDB store path.
                When omitted, resolves to `config.persist_directory` — the same
                store the Harvester writes to — so retrieval sees what the
                harvester captured.
            config: MemoryConfig to resolve the persist directory from when
                `persist_directory` is not given. Defaults to the global config.
        """
        if persist_directory is not None:
            self.persist_dir = Path(persist_directory)
        else:
            self.persist_dir = Path((config or get_config().memory).persist_directory)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.embedding_fn = (
            FastDeterministicEmbeddingFunction(384)
            if use_fast_embeddings
            else None
        )

        # Collection 1: Verified Code & Human Patches from Redis LTM
        self.code_collection = self.client.get_or_create_collection(
            name="ltm_code_solutions",
            embedding_function=self.embedding_fn,
        )

        # Collection 2: Scientific Literature & Formal Requirements
        self.literature_collection = self.client.get_or_create_collection(
            name="scientific_literature",
            embedding_function=self.embedding_fn,
        )

    def index_code_solution(
        self,
        doc_id: str,
        code_content: str,
        task_prompt: str,
        language: str = "python",
        energy: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Indexes a verified low-energy code solution into the vector store."""
        meta = metadata or {}
        meta.update({
            "language": language,
            "energy": energy,
            "task_prompt_preview": task_prompt[:150],
        })
        
        # Combine prompt and code for dense semantic retrieval
        document_text = f"Task: {task_prompt}\n\nSolution ({language}):\n{code_content}"
        
        self.code_collection.upsert(
            ids=[doc_id],
            documents=[document_text],
            metadatas=[meta],
        )

    def index_code_solutions_batch(
        self,
        items: list[dict[str, Any]],
    ) -> None:
        """Batch indexes multiple verified solutions for high-throughput ONNX/GPU encoding."""
        if not items:
            return
        batch_ids = []
        batch_docs = []
        batch_metas = []
        for it in items:
            doc_id = it["doc_id"]
            code_content = it.get("code_content", "")
            task_prompt = it.get("task_prompt", "")
            language = it.get("language", "python")
            energy = it.get("energy", 0.0)
            meta = it.get("metadata", {})
            meta.update({
                "language": language,
                "energy": energy,
                "task_prompt_preview": task_prompt[:150],
            })
            document_text = f"Task: {task_prompt}\n\nSolution ({language}):\n{code_content}"
            batch_ids.append(doc_id)
            batch_docs.append(document_text)
            batch_metas.append(meta)

        self.code_collection.upsert(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_metas,
        )

    def index_literature_document(
        self,
        doc_id: str,
        title: str,
        abstract_or_content: str,
        authors: str = "",
        year: str = "2026",
        arxiv_id: str = "",
        key_insights: str = "",
    ) -> None:
        """Indexes an academic paper or design document into the literature collection."""
        metadata = {
            "title": title,
            "authors": authors,
            "year": year,
            "arxiv_id": arxiv_id,
        }
        document_text = f"Title: {title}\nAuthors: {authors} ({year})\n\nContent:\n{abstract_or_content}\n\nKey Insights:\n{key_insights}"
        
        self.literature_collection.upsert(
            ids=[doc_id],
            documents=[document_text],
            metadatas=[metadata],
        )

    def query_code(self, problem_description: str, n_results: int = 3) -> list[dict[str, Any]]:
        """Queries the vector DB for the most relevant verified solutions from past LTM runs."""
        res = self.code_collection.query(
            query_texts=[problem_description],
            n_results=n_results,
        )
        hits = []
        if res and res.get("documents") and res["documents"][0]:
            for i, doc in enumerate(res["documents"][0]):
                meta = res["metadatas"][0][i] if res.get("metadatas") else {}
                hits.append({
                    "id": res["ids"][0][i],
                    "document": doc,
                    "metadata": meta,
                })
        return hits

    def query_literature(self, query: str, n_results: int = 3) -> list[dict[str, Any]]:
        """Queries the vector DB for academic grounding, theoretical axioms, or design patterns."""
        res = self.literature_collection.query(
            query_texts=[query],
            n_results=n_results,
        )
        hits = []
        if res and res.get("documents") and res["documents"][0]:
            for i, doc in enumerate(res["documents"][0]):
                meta = res["metadatas"][0][i] if res.get("metadatas") else {}
                hits.append({
                    "id": res["ids"][0][i],
                    "document": doc,
                    "metadata": meta,
                })
        return hits

    def sync_from_redis_ltm(self, r: Any = None) -> int:
        """
        Synchronizes verified subtasks, human patches, and low-energy traces
        from Redis LTM into ChromaDB.
        """
        if r is None:
            import redis
            r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", 6379)), decode_responses=False)

        subtasks = r.smembers("antigravity:subtasks:completed")
        subtask_ids = [s.decode("utf-8") if isinstance(s, bytes) else str(s) for s in subtasks]

        count = 0
        batch_ids = []
        batch_docs = []
        batch_meta = []

        for sid in subtask_ids:
            human_patch = r.get(f"antigravity:subtask:{sid}:human_patch")
            traces = r.lrange(f"antigravity:subtask:{sid}:traces", 0, 1)
            
            code_text = human_patch.decode("utf-8") if human_patch else ""
            prompt_text = ""
            energy = 0.0

            if traces:
                t_str = traces[0].decode("utf-8") if isinstance(traces[0], bytes) else str(traces[0])
                t_raw = r.get(f"antigravity:trace:{t_str}")
                if t_raw:
                    try:
                        t_data = json.loads(t_raw)
                        energy = float(t_data.get("energy", 0.0))
                        contents = t_data.get("request_json", {}).get("contents", [])
                        for turn in contents:
                            for part in turn.get("parts", []):
                                if "text" in part:
                                    prompt_text = part["text"]
                        if not code_text:
                            candidates = t_data.get("response_json", {}).get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                code_text = "\n".join(p.get("text", "") for p in parts if "text" in p)
                    except Exception:
                        pass

            if code_text and prompt_text:
                doc = f"Task: {prompt_text[:300]}\n\nCode:\n{code_text}"
                batch_ids.append(f"ltm_{sid}")
                batch_docs.append(doc)
                batch_meta.append({"subtask_id": sid, "energy": energy, "source": "redis_ltm"})
                count += 1

                if len(batch_ids) >= 100:
                    self.code_collection.upsert(ids=batch_ids, documents=batch_docs, metadatas=batch_meta)
                    batch_ids, batch_docs, batch_meta = [], [], []

        if batch_ids:
            self.code_collection.upsert(ids=batch_ids, documents=batch_docs, metadatas=batch_meta)

        logger.info("Synchronized %d solutions from Redis LTM to ChromaDB.", count)
        return count
