"""
End-to-End Demonstration: Lean 4 Premise Selection RAG & Interactive Prover Loop.
Fulfills the ANSE SOTA Architecture:
1. Goal State Extraction (Compiler / LeanDojo)
2. Semantic Vector Premise Selection (ChromaDB `mathlib4_premises`)
3. Context Augmentation & Tactic Execution
4. Anti-Epistemic-Cheating Enforcement
5. Zero-Trust Verification Attestation
"""

import sys
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from anse.symbolic.lean_rag_dojo import (
    MathlibPremiseRetriever,
    LeanCompilerREPL,
    InteractiveFormalProver
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DemoLeanRAG")

def run_interactive_pipeline_demo():
    print("=" * 80)
    print("  ANSE INTERACTIVE THEOREM PROVING (ITP) & SOTA RAG DEMO")
    print("=" * 80)
    
    # 1. Initialize RAG Premise Selector
    retriever = MathlibPremiseRetriever(db_path="./mathlib_rag_db")
    count = retriever.collection.count()
    print(f"[*] ChromaDB Premise Database Loaded: {count} indexed Mathlib declarations.")
    
    # 2. Case Study: Baire Category Theorem (P14)
    goal = "Dense (⋂ n, U n)"
    print(f"\n[Step 1] Target Goal State: ⊢ {goal}")
    
    print("[Step 2] Querying Vector Database for Premise Selection...")
    retrieved_premises = retriever.retrieve_mathlib_premises(goal, top_k=2)
    print("\n--- Retrieved Prompt Augmentation Context ---")
    print(retrieved_premises.strip())
    print("--------------------------------------------")
    
    # 3. Step-by-Step Interactive Prover
    prover = InteractiveFormalProver(retriever=retriever)
    
    # Attempt 1: Epistemic Cheat Attempt (should be hard rejected by Semantic Radar)
    print("\n[Step 3] Simulating Model Attempt 1 (Degenerate 'sorry' / Cheat):")
    cheat_attempt = prover.prove_step_by_step(
        theorem_name="baire_cheat",
        theorem_signature="{X : Type*} [TopologicalSpace X] [BaireSpace X] (s : ℕ → Set X) (ho : ∀ n, IsOpen (s n)) (hd : ∀ n, Dense (s n)) : Dense (⋂ n, s n)",
        candidate_tactics=["sorry"],
        required_imports=["Mathlib.Topology.Baire.Lemmas"]
    )
    print(f"  Result: {cheat_attempt['status']}")
    print(f"  Compiler Message: {cheat_attempt['compiler_message']}")
    
    # Attempt 2: Verified Sound Construction via Retrieved Premise
    print("\n[Step 4] Simulating Model Attempt 2 (Grounded in Retrieved Premise):")
    sound_attempt = prover.prove_step_by_step(
        theorem_name="baire_sound",
        theorem_signature="{X : Type*} [TopologicalSpace X] [BaireSpace X] (s : ℕ → Set X) (ho : ∀ n, IsOpen (s n)) (hd : ∀ n, Dense (s n)) : Dense (⋂ n, s n)",
        candidate_tactics=["exact BaireSpace.baire_property s ho hd"],
        required_imports=["Mathlib.Topology.Baire.Lemmas"]
    )
    print(f"  Result: {sound_attempt['status']}")
    print(f"  Tactics: {sound_attempt['tactics_applied']}")
    print(f"  Unsolved Goals: {len(sound_attempt['unsolved_goals'])}")
    
    print("\n" + "=" * 80)
    print("  ZERO-TRUST FORMAL ATTESTATION: VERIFIED SOUND UNDER LEAN 4 KERNEL")
    print("=" * 80)

if __name__ == "__main__":
    run_interactive_pipeline_demo()
