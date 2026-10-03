"""
High-density indexing script for Mathlib4 core premises.
Indexes foundational theorems into ChromaDB for rapid Premise Selection.
"""

import sys
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from anse.symbolic.lean_rag_dojo import MathlibPremiseRetriever

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IndexMathlib")

def main():
    logger.info("Initializing Mathlib4 Vector Database Indexing (High-Density Subset)...")
    retriever = MathlibPremiseRetriever(db_path="./mathlib_rag_db")
    
    mathlib_root = Path("formal/.lake/packages/mathlib/Mathlib")
    
    # Specific high-value theorem files
    target_files = [
        mathlib_root / "Topology/Baire/Lemmas.lean",
        mathlib_root / "Topology/Order/IntermediateValue.lean",
        mathlib_root / "Topology/MetricSpace/Bounded.lean",
        mathlib_root / "Topology/MetricSpace/Defs.lean",
        mathlib_root / "GroupTheory/Sylow.lean",
        mathlib_root / "Analysis/InnerProductSpace/Spectrum.lean",
        mathlib_root / "Analysis/InnerProductSpace/Basic.lean",
        mathlib_root / "Analysis/Real/Sqrt.lean",
        mathlib_root / "Analysis/ODE/ExistUnique.lean",
        mathlib_root / "Analysis/BoxIntegral/DivergenceTheorem.lean",
        mathlib_root / "LinearAlgebra/Matrix/Charpoly/Basic.lean",
        mathlib_root / "Order/Zorn.lean",
        mathlib_root / "Data/Nat/Prime/Infinite.lean",
        mathlib_root / "Data/Nat/Prime/Basic.lean",
        mathlib_root / "NumberTheory/Real/Irrational.lean",
    ]
    
    existing_files = [f for f in target_files if f.exists()]
    logger.info(f"Extracting declarations from {len(existing_files)} key Mathlib files...")
    
    all_premises = []
    for f in existing_files:
        all_premises.extend(retriever.extract_premises_from_file(f))
        
    logger.info(f"Extracted {len(all_premises)} key premises. Upserting into ChromaDB...")
    
    # Upsert in small batches
    batch_size = 50
    for i in range(0, len(all_premises), batch_size):
        batch = all_premises[i:i + batch_size]
        retriever.collection.upsert(
            ids=[p["id"] for p in batch],
            documents=[p["search_text"] for p in batch],
            metadatas=[{
                "name": p["name"],
                "signature": p["signature"][:500],
                "import_module": p["module"],
                "docstring": p["docstring"][:300]
            } for p in batch]
        )
        
    count = retriever.collection.count()
    logger.info(f"ChromaDB Mathlib4 collection count: {count} premises indexed.")
    
    # Test queries
    test_queries = [
        "Dense (⋂ n, U n)",
        "ContinuousOn f (Set.Icc a b)",
        "Real.sqrt (x * y) ≤ (x + y) / 2",
        "p ^ n ∣ Nat.card G",
        "IsCompact s ↔ IsClosed s ∧ IsBounded s",
        "HasDerivWithinAt α (f t (α t))"
    ]
    
    print("\n" + "=" * 80)
    print("  VERIFYING PREMISE SELECTION RETRIEVAL FROM CHROMADB")
    print("=" * 80)
    for q in test_queries:
        print(f"\nQuery Goal: {q}")
        premise_context = retriever.retrieve_mathlib_premises(q, top_k=2)
        print(premise_context.strip())
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
