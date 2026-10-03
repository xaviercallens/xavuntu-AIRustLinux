#!/usr/bin/env python3
"""
Record peer review v2 (second Strong Reject) into LTM and vector store.
Updates the peer_reviews.json and stores embedding-ready critique vectors.
"""
from __future__ import annotations
import json
import hashlib
import datetime
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REVIEW_DIR = REPO_ROOT / "results" / "phd_k3_pipeline" / "review"
REVIEW_DIR.mkdir(parents=True, exist_ok=True)

PEER_REVIEW_V2_TEXT = """
# Peer Review Report — Second Submission (v13.8.0 revision)

**Recommendation:** Strong Reject (second consecutive)

## Critical Remaining Issues

### A. Lean 4 "Bait-and-Switch" (STILL PRESENT)
- second_chern_class (c2: Z) := c2 = 24 proves 24=24, not bundle topology
- flux_sq + n_m2 = 24 proves 20+4=24, not M-theory tadpoles
- Eguchi-Hanson self-duality reduced to true=true via decide
- Wronskian non-degeneracy reduced to 1/16 ≠ 0
- Banach contraction proves 3.5 < 20, pure arithmetic

### B. Categorical Physics Errors (STILL PRESENT)
- Second Chern class and G-flux tadpoles are topological invariants, not continuous energies
- Picard-Fuchs is a linear PDE over moduli space, Yoshida symplectic integration doesn't apply
- Rademacher expansion is analytic number theory, not a dynamical system
- Summing 'energy' across dimensionally disjoint domains is mathematically meaningless

### C. Pseudoscientific Terminology (STILL PRESENT)
- 'Autopoietic Banach Moduli Self-Stabilization' — no established connection to Banach theory

### D. Missing Mathematical Foundations (STILL PRESENT)
- No explicit definition of 'Physical Energy E'
- No PDEs, Hamiltonians, Lagrangians, or metrics

## Required Actions for Next Revision
1. Replace ALL arithmetic tautologies with genuine Lean 4 theorems (lake build must pass)
2. Implement proper domain decomposition: E for continuous, C for discrete
3. Add explicit Hamiltonians, PDEs for each continuous problem
4. Ground or remove 'autopoietic' terminology
5. Reproduce all 10 papers with corrections
"""

CRITICISMS_V2 = {
    "review_id": "peer_review_v2_strong_reject",
    "date": datetime.datetime.now().isoformat(),
    "version_reviewed": "v13.8.0",
    "verdict": "Strong Reject",
    "sha256": hashlib.sha256(PEER_REVIEW_V2_TEXT.encode()).hexdigest(),
    "criticisms": {
        "A_lean4_bait_switch": {
            "severity": "FATAL",
            "description": "Lean proofs are arithmetic tautologies disguised as physics theorems",
            "examples": [
                "second_chern_class := c2 = 24 proves 24=24",
                "flux_sq + n_m2 = 24 proves 20+4=24",
                "self-duality proves true=true via decide",
                "Wronskian proves 1/16 ≠ 0",
                "Banach contraction proves 3.5 < 20"
            ],
            "fix_v13_9": "Genuine Lean theorems with Mathlib4 content (linear_combination, div_le_iff, etc.)"
        },
        "B_categorical_physics": {
            "severity": "FATAL",
            "description": "Topological invariants treated as continuous energies",
            "examples": [
                "c2(E) ∈ Z cannot be minimized as continuous energy",
                "Picard-Fuchs is linear PDE, not Hamiltonian system",
                "Rademacher is analytic number theory, not dynamical system",
                "Summing dimensionally disjoint scalars is meaningless"
            ],
            "fix_v13_9": "Domain decomposition: continuous E vs discrete C, never summed"
        },
        "C_pseudoscience": {
            "severity": "MAJOR",
            "description": "Autopoietic terminology has no mathematical grounding",
            "fix_v13_9": "Replace with 'self-stabilizing', cite Banach fixed-point theorem explicitly"
        },
        "D_missing_math": {
            "severity": "FATAL",
            "description": "No explicit PDEs, Hamiltonians, Lagrangians, or energy definitions",
            "fix_v13_9": "Add mathematical specification section with explicit governing equations"
        }
    },
    "required_actions": [
        "Genuine Lean 4 theorems: wronskian_implies_independence via linear_combination",
        "Domain decomposition: E(continuous)=physical energy, C(discrete)=computational cost",
        "Explicit Hamiltonians for K3-01 (attractor), K3-09 (Kerr)",
        "Remove 'autopoietic' from physics context",
        "External numerical pipeline: zero LLM hallucination",
        "All 10 papers: Lean snippet must show genuine theorem (not arithmetic)",
        "Scope disclaimer: what is formally verified vs numerically estimated"
    ],
    "full_text": PEER_REVIEW_V2_TEXT
}

# Save the review
reviews_file = REVIEW_DIR / "peer_reviews_v2.json"
with open(reviews_file, "w", encoding="utf-8") as f:
    json.dump(CRITICISMS_V2, f, indent=2)
print(f"Saved: {reviews_file}")

# Also save the markdown
md_file = REVIEW_DIR / "peer_review_v2_strong_reject.md"
with open(md_file, "w", encoding="utf-8") as f:
    f.write(PEER_REVIEW_V2_TEXT)
print(f"Saved: {md_file}")

# Try to store in ChromaDB if available
try:
    sys.path.insert(0, str(REPO_ROOT))
    from anse.memory.results_store import ResultsStore
    store = ResultsStore(
        persist_directory=str(REPO_ROOT / ".chroma_db"),
        enable_chroma=True, enable_redis=False
    )
    store.store_result(
        collection="peer_reviews",
        doc_id="peer_review_v2_strong_reject",
        text=PEER_REVIEW_V2_TEXT,
        metadata={
            "version": "v13.8.0",
            "verdict": "Strong_Reject",
            "round": 2,
            "sha256": CRITICISMS_V2["sha256"]
        }
    )
    print("Stored in ChromaDB vector store")
except Exception as e:
    print(f"ChromaDB storage skipped: {e}")

print("\nPeer review v2 recorded successfully.")
print(f"SHA256: {CRITICISMS_V2['sha256'][:16]}...")
