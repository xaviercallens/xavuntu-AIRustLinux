#!/usr/bin/env python3
"""Index Lean theorem signatures (FLT / Navier-Stokes corpora) into Chroma
for premise retrieval during proving (RAG for the prover loop).

Signature JSONLs are produced by grep extraction from the vendored corpora at
LeanMaster/lean4basesource (see datalake/flt_signatures.jsonl and
navierstokes_signatures.jsonl). Embedding 82k signatures takes hours on the
shared Ollama instance, so --limit exists for sliced runs; the indexer is
idempotent (ids are content hashes) and can be resumed any time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from anse.memory.ollama_embeddings import OllamaEmbeddingFunction

LAKE = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/datalake")
CHROMA_DIR = LAKE / "chroma" / "lean_premises"
SOURCES = {
    "flt": LAKE / "flt_signatures.jsonl",
    "navierstokes": LAKE / "navierstokes_signatures.jsonl",
}
BATCH = 64


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500, help="max signatures per corpus this run")
    ap.add_argument("--query", help="retrieval sanity query to run after indexing")
    args = ap.parse_args()

    import chromadb

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    coll = client.get_or_create_collection(
        "lean_premises", embedding_function=OllamaEmbeddingFunction(),
        metadata={"hnsw:space": "cosine"},
    )
    existing = set((coll.get(include=[]) or {}).get("ids") or [])

    total_added = 0
    for corpus, path in SOURCES.items():
        if not path.exists():
            print(f"{corpus}: {path} missing, skipped")
            continue
        ids, docs, metas = [], [], []
        added = 0
        for line in path.open():
            if added >= args.limit:
                break
            rec = json.loads(line)
            doc_id = hashlib.sha256((corpus + rec["signature"]).encode()).hexdigest()[:32]
            if doc_id in existing:
                continue
            ids.append(doc_id)
            docs.append(rec["signature"])
            metas.append({"corpus": corpus, "file": rec["file"], "line": rec["line"]})
            existing.add(doc_id)
            added += 1
            if len(ids) >= BATCH:
                coll.upsert(ids=ids, documents=docs, metadatas=metas)
                ids, docs, metas = [], [], []
        if ids:
            coll.upsert(ids=ids, documents=docs, metadatas=metas)
        total_added += added
        print(f"{corpus}: +{added} signatures")

    print(f"collection lean_premises total: {coll.count()}")
    if args.query:
        res = coll.query(query_texts=[args.query], n_results=5)
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            print(f"[{meta['corpus']} d={dist:.3f}] {doc[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
