#!/usr/bin/env python3
"""
Vector Search Simulation & Semantic Retrieval Benchmark.

Indexes authentic existing data (Python & Rust use cases from LTM/DPO datasets
and academic literature), simulates diverse 'nearby / paraphrased' user prompts,
and benchmarks ChromaDB retrieval accuracy, similarity scores, and search latency.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from anse.memory.chroma_rag import ChromaRAG

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_dataset_samples(file_path: Path, max_samples: int = 50) -> list[dict[str, Any]]:
    """Loads a slice of verified records from a DPO JSONL dataset."""
    samples: list[dict[str, Any]] = []
    if not file_path.exists():
        return samples
    with open(file_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= max_samples:
                break
            stripped = line.strip()
            if stripped:
                try:
                    samples.append(json.loads(stripped))
                except json.JSONDecodeError:
                    continue
    return samples


def extract_user_prompt(messages: list[dict[str, str]]) -> str:
    """Extracts user prompt string from message turns."""
    for m in messages:
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def run_single_engine_benchmark(engine_name: str, use_fast: bool, py_samples: list[dict], rust_samples: list[dict], test_queries: list[dict]) -> dict[str, Any]:
    print(f"\n--- Benchmarking: {engine_name} ---")
    db_dir = PROJECT_ROOT / "data" / f"chroma_{'fast' if use_fast else 'dense'}_db"
    rag = ChromaRAG(persist_directory=db_dir, use_fast_embeddings=use_fast)

    # Index Python & Rust
    for idx, sample in enumerate(py_samples, start=1):
        prompt = extract_user_prompt(sample.get("prompt", []))
        rag.index_code_solution(
            doc_id=f"py_case_{idx:03d}",
            code_content=sample.get("chosen", ""),
            task_prompt=prompt,
            language="python",
            energy=12.1,
        )

    for idx, sample in enumerate(rust_samples, start=1):
        prompt = extract_user_prompt(sample.get("prompt", []))
        rag.index_code_solution(
            doc_id=f"rust_case_{idx:03d}",
            code_content=sample.get("chosen", ""),
            task_prompt=prompt,
            language="rust",
            energy=11.2,
        )

    # Index Literature
    rag.index_literature_document(
        doc_id="paper_proofevolve",
        title="ProofEvolve: Neuro-Symbolic Theorem Proving with Formal Lean 4 Kernel Feedback",
        abstract_or_content="Evolving proof DAGs where the Lean 4 kernel acts as a symbolic binary ground truth filter.",
        authors="Chen et al. (2026)",
        year="2026",
    )
    rag.index_literature_document(
        doc_id="paper_afterburner",
        title="Afterburner: Iterative Code Optimization via Reinforcement Learning and Execution Feedback",
        abstract_or_content="Iterative compilation and execution feedback used as non-differentiable reward in GRPO to optimize runtime.",
        authors="Gu et al. (2025)",
        year="2025",
    )

    top1_hits = 0
    top3_hits = 0
    total_latency_ms = 0.0
    queries_run = 0

    for test in test_queries:
        exp_id = test["expected_id"]
        is_lit = test.get("is_literature", False)

        for q_type, query_str in test["simulated_queries"]:
            queries_run += 1
            t0 = time.perf_counter()
            if is_lit:
                hits = rag.query_literature(query_str, n_results=3)
            else:
                hits = rag.query_code(query_str, n_results=3)
            lat = (time.perf_counter() - t0) * 1000.0
            total_latency_ms += lat

            retrieved_ids = [h["id"] for h in hits]
            is_top1 = len(retrieved_ids) > 0 and retrieved_ids[0] == exp_id
            is_top3 = exp_id in retrieved_ids

            if is_top1: top1_hits += 1
            if is_top3: top3_hits += 1

    return {
        "engine": engine_name,
        "queries_tested": queries_run,
        "top1_pct": round((top1_hits / queries_run) * 100.0, 1),
        "top3_pct": round((top3_hits / queries_run) * 100.0, 1),
        "avg_latency_ms": round(total_latency_ms / queries_run, 2),
    }


def run_simulation_benchmark() -> dict[str, Any]:
    print("\n" + "=" * 80)
    print("🚀 VECTOR SEARCH BENCHMARK: SIMULATING NEARBY PROMPTS ON EXISTING DATA")
    print("=" * 80)

    py_dataset = PROJECT_ROOT / "results" / "dpo_2000_cases_eda_dataset.jsonl"
    py_samples = load_dataset_samples(py_dataset, max_samples=40)

    rust_dataset = PROJECT_ROOT / "results" / "dpo_1000_cases_rust_dataset.jsonl"
    rust_samples = load_dataset_samples(rust_dataset, max_samples=40)

    test_queries = [
        {
            "category": "Rust Anagram Verification",
            "expected_id": "rust_case_001",
            "original_prompt": "Create a function in Rust that takes two strings and returns true if they are anagrams.",
            "simulated_queries": [
                ("Paraphrase / Rephrasing", "Check if two words contain the exact same letters in Rust"),
                ("Conceptual / Technical", "Rust string permutation frequency counter algorithm"),
                ("Cross-Lingual (French)", "Écrire une fonction qui vérifie si deux chaînes sont des anagrammes en Rust"),
                ("Keyword / Dense Query", "rust anagram checker"),
            ],
        },
        {
            "category": "Rust Binary Search Tree LCA",
            "expected_id": "rust_case_002",
            "original_prompt": "Write a Rust program to find the lowest common ancestor in a binary search tree",
            "simulated_queries": [
                ("Paraphrase / Rephrasing", "Find the shared parent node of two values in a BST with Rust"),
                ("Conceptual / Technical", "Binary search tree lowest common ancestor recursive traversal"),
                ("Cross-Lingual (French)", "Plus proche ancêtre commun dans un arbre binaire de recherche en Rust"),
            ],
        },
        {
            "category": "Python Matrix Distinct States",
            "expected_id": "py_case_001",
            "original_prompt": "Write a function to find the number of distinct states in a given matrix.",
            "simulated_queries": [
                ("Paraphrase / Rephrasing", "Count how many unique rows exist in a 2D grid in Python"),
                ("Conceptual / Technical", "Matrix unique state deduplication using hash sets"),
                ("Cross-Lingual (French)", "Calculer le nombre d'états distincts dans une matrice en Python"),
            ],
        },
        {
            "category": "Python Prime Numbers Sum",
            "expected_id": "py_case_002",
            "original_prompt": "Write code to find the sum of all prime numbers between 1 million and 2 million, excluding prime numbers that contain 7",
            "simulated_queries": [
                ("Paraphrase / Rephrasing", "Sum of primes in range 1000000 to 2000000 skipping digit 7"),
                ("Conceptual / Technical", "Prime sieve summation with digit filter in Python"),
                ("Cross-Lingual (French)", "Somme des nombres premiers sans le chiffre 7 en Python"),
            ],
        },
        {
            "category": "Scientific Literature (Lean 4)",
            "expected_id": "paper_proofevolve",
            "original_prompt": "ProofEvolve: Neuro-Symbolic Theorem Proving with Formal Lean 4 Kernel Feedback",
            "is_literature": True,
            "simulated_queries": [
                ("Paraphrase / Rephrasing", "How to ground neural coding agents in the Lean 4 proof assistant"),
                ("Conceptual / Technical", "Interactive theorem proving kernel verification for neuro-symbolic search"),
                ("Cross-Lingual (French)", "Vérification formelle de théorèmes avec le noyau Lean 4"),
            ],
        },
    ]

    res_fast = run_single_engine_benchmark("Chroma Fast N-Gram Embedding", True, py_samples, rust_samples, test_queries)
    res_dense = run_single_engine_benchmark("Chroma Dense Neural Transformer (all-MiniLM-L6-v2)", False, py_samples, rust_samples, test_queries)

    print("\n" + "=" * 80)
    print("📈 DUAL-ENGINE COMPARATIVE BENCHMARK TELEMETRY")
    print("=" * 80)
    print(f"{'Embedding Engine':<45} | {'Top-1 Recall':<12} | {'Top-3 Recall':<12} | {'Latency':<10}")
    print("-" * 88)
    for r in [res_fast, res_dense]:
        print(f"{r['engine']:<45} | {r['top1_pct']:>10}% | {r['top3_pct']:>10}% | {r['avg_latency_ms']:>6.2f} ms")
    print("=" * 80)

    final_report = {
        "benchmark": "Dual_Embedding_Vector_Search_Simulation",
        "fast_engine": res_fast,
        "dense_engine": res_dense,
    }
    out_file = PROJECT_ROOT / "results" / "vector_search_simulation_report.json"
    out_file.write_text(json.dumps(final_report, indent=2), encoding="utf-8")
    print(f"📁 Summary Report Saved to: {out_file}\n")
    return final_report


if __name__ == "__main__":
    run_simulation_benchmark()
