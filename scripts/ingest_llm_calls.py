#!/usr/bin/env python3
"""Index logged LLM calls into the Chroma LTM so they are semantically searchable.

Sources, in order: every ``*.jsonl`` under the call-log directory (the durable
record written by ``APIExtractor._log_call`` and the experiment scripts).
Each call becomes one Chroma document keyed by the sha256 of its JSON line,
so re-runs are idempotent. Embeddings come from the same Ollama model as the
rest of the LTM (qwen3-embedding:0.6b, 1024-d).

Usage:
    .venv/bin/python scripts/ingest_llm_calls.py [--call-log-dir DIR] [--query "..."]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from anse.memory.ollama_embeddings import OllamaEmbeddingFunction

DEFAULT_LOG_DIR = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/call_logs")
DEFAULT_CHROMA = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/datalake/chroma/ltm/llm_calls")
BATCH = 32
DOC_CHARS = 6000  # embed window guard: qwen3-embedding truncates ~4096 tokens


def call_to_document(rec: dict) -> str:
    msgs = rec.get("input", {}).get("messages") or []
    prompt = " ".join(m.get("content", "") for m in msgs) or rec.get("input", {}).get("prompt", "")
    out = rec.get("output", {}).get("text", "")
    return (f"model={rec.get('model','?')} time={rec.get('timestamp','?')}\n"
            f"PROMPT: {prompt[:DOC_CHARS // 2]}\nRESPONSE: {out[:DOC_CHARS // 2]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--call-log-dir", type=Path, default=DEFAULT_LOG_DIR)
    ap.add_argument("--chroma-dir", type=Path, default=DEFAULT_CHROMA)
    ap.add_argument("--query", help="after ingest, run this retrieval sanity query")
    args = ap.parse_args()

    import chromadb

    args.chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(args.chroma_dir))
    coll = client.get_or_create_collection(
        "llm_calls", embedding_function=OllamaEmbeddingFunction(),
        metadata={"hnsw:space": "cosine"},
    )

    files = sorted(args.call_log_dir.glob("*.jsonl"))
    added = skipped = bad = 0
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []

    def flush() -> None:
        nonlocal added
        if ids:
            coll.upsert(ids=list(ids), documents=list(docs), metadatas=list(metas))
            added += len(ids)
            ids.clear()
            docs.clear()
            metas.clear()

    existing = set()
    got = coll.get(include=[])
    existing.update(got.get("ids") or [])

    for f in files:
        for line in f.open():
            line = line.strip()
            if not line:
                continue
            doc_id = hashlib.sha256(line.encode()).hexdigest()[:32]
            if doc_id in existing:
                skipped += 1
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            ids.append(doc_id)
            docs.append(call_to_document(rec))
            metas.append({"model": rec.get("model", "?"),
                          "timestamp": rec.get("timestamp", "?"),
                          "source_file": f.name})
            existing.add(doc_id)
            if len(ids) >= BATCH:
                flush()
    flush()

    print(f"files={len(files)} added={added} skipped_existing={skipped} bad_lines={bad} "
          f"total_in_collection={coll.count()}")

    if args.query:
        res = coll.query(query_texts=[args.query], n_results=3)
        for i, (doc, dist) in enumerate(zip(res["documents"][0], res["distances"][0]), 1):
            print(f"[hit {i}] dist={dist:.3f} :: {doc[:160]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
