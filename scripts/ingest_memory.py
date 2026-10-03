#!/usr/bin/env python3
"""Populate long-term memory: transcripts, literature review & papers, and benchmark results.

Three independent ingests, dual-persisted to Redis (durable recall) and Chroma (vector search):

  * **Transcripts** -> Redis (`anse:ltm:transcript:<session_id>:<turn>`) + Chroma (`claude_code_sessions`).
    Supports Claude Code (`~/.claude/projects`) and Antigravity (`~/.gemini/antigravity-cli/brain`).
    Every turn is scrubbed of credentials/paths and marked `trainable=False` (retrieval-only).

  * **Documents & Literature** -> Redis (`anse:ltm:doc:<sha256>`) + Chroma (`literature`, `own_papers`).
    Indexes papers (`papers/`), literature specs (`docs/`), foundational texts (`vendor/`),
    and generated dossiers (`results/*.pdf`).
    Every chunk carries `source_path`, `source_sha256` and `page` for mathematical provenance.

  * **Results & Telemetry** -> Redis (`anse:ltm:result:<slug>`) + Chroma (`benchmark_results`).
    Indexes comprehensive benchmark evaluations (`results/200_unified_eval_report.json`,
    `results/dpo_*.jsonl`, `results/nightly_training/`, `results/phase{1,2,3}_evolution/`).

Usage:
    .venv/bin/python scripts/ingest_memory.py --all
    .venv/bin/python scripts/ingest_memory.py --transcripts --limit-files 10
    .venv/bin/python scripts/ingest_memory.py --pdfs
    .venv/bin/python scripts/ingest_memory.py --results
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DISK2 = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI")

# Chroma default root: falls back to local data/chroma/ltm if disk2 is absent
DEFAULT_CHROMA_ROOT = (
    DISK2 / "datalake" / "chroma" / "ltm"
    if DISK2.exists()
    else REPO_ROOT / "data" / "chroma" / "ltm"
)

logger = logging.getLogger("ingest_memory")


def ingest_transcripts(
    chroma_root: Path,
    limit_files: int | None,
    redis_url: str | None,
    transcript_root: Path | None = None,
) -> dict[str, Any]:
    from anse.memory.transcript_ltm import import_all

    report = import_all(
        root=transcript_root,  # None defaults to searching both Claude and Antigravity
        redis_url=redis_url,
        chroma_directory=chroma_root / "transcripts",
        limit_files=limit_files,
    )
    if transcript_root is not None:
        report["transcript_root"] = str(transcript_root)
    scrubbed = report["scrub"]["total_replacements"]
    if report["turns_stored"] and scrubbed == 0:
        logger.warning(
            "stored %d turns but scrubbed nothing -- verify the scrub patterns",
            report["turns_stored"],
        )
    return report


def ingest_pdfs(chroma_root: Path, redis_url: str | None = None) -> dict[str, Any]:
    from anse.memory.document_store import ingest_project_corpora

    return ingest_project_corpora(
        persist_directory=chroma_root / "documents",
        papers_dir=REPO_ROOT / "papers",
        literature_dirs=[REPO_ROOT / "docs", REPO_ROOT / "vendor"],
        results_dir=REPO_ROOT / "results",
        redis_url=redis_url,
    )


def ingest_results(chroma_root: Path, redis_url: str | None = None) -> dict[str, Any]:
    from anse.memory.results_store import ResultsStore

    store = ResultsStore(
        persist_directory=chroma_root / "results",
        redis_url=redis_url,
    )
    return store.ingest_directory(REPO_ROOT / "results")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="transcripts, PDFs/docs, and benchmark results")
    parser.add_argument("--transcripts", action="store_true", help="Claude Code and Antigravity transcripts")
    parser.add_argument("--pdfs", "--documents", dest="pdfs", action="store_true", help="PDFs and literature docs")
    parser.add_argument("--results", action="store_true", help="Benchmark and evaluation reports under results/")
    parser.add_argument("--limit-files", type=int, default=None)
    parser.add_argument(
        "--transcript-root",
        type=Path,
        default=None,
        help="Optional specific directory of session JSONL to import. Defaults to both Claude and Antigravity.",
    )
    parser.add_argument("--chroma-root", type=Path, default=DEFAULT_CHROMA_ROOT)
    parser.add_argument("--redis-url", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not (args.all or args.transcripts or args.pdfs or args.results):
        parser.error("choose --all, --transcripts, --pdfs, and/or --results")

    logging.basicConfig(
        level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
    )
    args.chroma_root.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {"chroma_root": str(args.chroma_root)}
    failed = False

    if args.all or args.transcripts:
        logger.info("ingesting agent transcripts (Claude + Antigravity) -> Redis + Chroma")
        try:
            results["transcripts"] = ingest_transcripts(
                args.chroma_root,
                args.limit_files,
                args.redis_url,
                transcript_root=args.transcript_root,
            )
            t = results["transcripts"]
            logger.info(
                "  %d turns from %d files across %d sessions; %d secrets scrubbed",
                t["turns_stored"],
                t["files_read"],
                t["sessions"],
                t["scrub"]["total_replacements"],
            )
        except Exception as exc:
            logger.error("  transcript ingest FAILED: %s", exc)
            results["transcripts"] = {"error": str(exc)}
            failed = True

    if args.all or args.pdfs:
        logger.info("ingesting documents (papers, literature, vendor, results) -> Redis + Chroma")
        try:
            results["documents"] = ingest_pdfs(args.chroma_root, redis_url=args.redis_url)
            for name, report in results["documents"].items():
                logger.info(
                    "  %s: %d files, %d chunks, %d skipped (%d-d embeddings)",
                    name,
                    report["files_indexed"],
                    report["chunks_written"],
                    report["files_skipped"],
                    report["embedding_dimension"] or 0,
                )
        except Exception as exc:
            logger.error("  document ingest FAILED: %s", exc)
            results["documents"] = {"error": str(exc)}
            failed = True

    if args.all or args.results:
        logger.info("ingesting benchmark and evaluation results -> Redis + Chroma")
        try:
            results["results"] = ingest_results(args.chroma_root, redis_url=args.redis_url)
            r = results["results"]
            logger.info(
                "  %d result files indexed, %d skipped",
                r["indexed_count"],
                r["skipped_count"],
            )
        except Exception as exc:
            logger.error("  results ingest FAILED: %s", exc)
            results["results"] = {"error": str(exc)}
            failed = True

    if args.json:
        print(json.dumps(results, indent=2, default=str))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
