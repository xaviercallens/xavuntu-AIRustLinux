#!/usr/bin/env python3
"""
Demonstration of ANSE Autonomous MCTS Theorem Prover.

Demonstrates:
1. MCTS tree expansion with Mathlib RAG premise selection.
2. Immediate fail-closed pruning (Q = -100.0) when an epistemic cheat is attempted.
3. Successful tree convergence on genuine mathematical invariants with zero sorry.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anse.symbolic.lean_mcts_prover import LeanMCTSProver

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DemoMCTSProver")


def run_demo():
    print("=" * 80)
    print("      ANSE AUTONOMOUS MCTS THEOREM PROVER WITH ZERO-TRUST RED TEAM")
    print("=" * 80)

    prover = LeanMCTSProver(work_dir="formal")

    # Case 1: Real inequality proof via MCTS tree search
    print("\n[Case 1] Proving Real Inequality with MCTS Tree Search...")
    thm_name = "mcts_order_sandwich"
    sig = "(x y z : ℝ) (hxy : x ≤ y) (hyz : y ≤ z) (hzx : z ≤ x) : x = z"
    imports = ["Mathlib.Data.Real.Basic", "Mathlib.Tactic.Linarith"]

    res = prover.search(
        theorem_name=thm_name,
        theorem_signature=sig,
        required_imports=imports,
        max_iterations=12,
        max_depth=3,
    )

    print(f"  Search Status        : {res['status']}")
    print(f"  Success              : {res['success']}")
    print(f"  Nodes Explored       : {res['nodes_explored']}")
    print(f"  Cheats Intercepted   : {res['cheats_intercepted']}")
    print(f"  Elapsed Latency (ms) : {res['elapsed_ms']}")
    print(f"  Terminal Q-Value     : {res['terminal_q']}")
    print("  Synthesized Lean 4 Code:")
    for line in res["lean_code"].splitlines():
        print(f"    {line}")

    # Case 2: Red Team Interception & Pruning Simulation
    print("\n[Case 2] Simulating Red Team Cheat Pruning on Monolithic Shortcuts...")
    cheat_tactics = ["sorry"]
    is_p, is_c, q_val, goals, msg = prover.evaluate_tactic_sequence(
        theorem_name="cheat_demonstration",
        theorem_signature=": 1 = 1",
        required_imports=["Mathlib.Data.Real.Basic"],
        tactic_sequence=cheat_tactics,
    )
    print(f"  Cheat Detected       : {is_c}")
    print(f"  Assigned Value       : {q_val} (Maximum Pain Pruning)")
    print(f"  Red Team Message     : {msg}")

    print("\n" + "=" * 80)
    print("  ZERO-TRUST ATTRIBUTION: UNCOMPROMISED MATHEMATICAL VERIFICATION")
    print("=" * 80)


if __name__ == "__main__":
    run_demo()
