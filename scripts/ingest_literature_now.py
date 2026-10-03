#!/usr/bin/env python3
"""One-shot: ingest BSD review + existing docs markdown into the `literature`
Chroma collection, then run a retrieval sanity query."""

from pathlib import Path

from anse.memory.document_store import DocumentStore

ROOT = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/datalake/chroma/ltm/documents")
WT = Path(__file__).resolve().parent.parent


def main() -> int:
    store = DocumentStore(ROOT, "literature")
    targets = [WT / "docs/literature/BSD_LITERATURE_REVIEW_2026.md", WT / "LL.md"]
    for name in ["LITERATURE_REVIEW_RAG.md", "EBM_JEPA_Foundations.md", "LeCun2006_EBM_Summary.md"]:
        p = WT / "docs" / name
        if p.exists():
            targets.append(p)
    for p in targets:
        if not p.exists():
            continue
        n = store.ingest_text_file(p, extra_metadata={"topic": "bsd" if "BSD" in p.name else "ml"})
        print(f"{p.name}: {n} chunks")
    for pdf in sorted((WT / "vendor").glob("*.pdf")):
        n = store.ingest_pdf(pdf, extra_metadata={"topic": "ml"})
        print(f"{pdf.name}: {n} chunks")
    print("literature collection count:", store.count())
    hits = store.query("How does Kolyvagin's Euler system bound the Tate-Shafarevich group?", n_results=3)
    for h in hits:
        print(f"[dist={h['distance']:.3f}] {h['document'][:110]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
