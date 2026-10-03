from __future__ import annotations

import math
import random
import subprocess
from dataclasses import dataclass

from anse.formal.lean_runner import LeanKernelVerifier

# Environnement formel cible
THEOREM_NAME = "modus_tollens"

BASE_LEAN = """
theorem modus_tollens {p q : Prop} (h1 : p → q) (h2 : ¬q) : ¬p := by
    {tactics}

#print axioms modus_tollens
"""

# Espace d'actions du LLM (Tactiques Lean 4 générées par le modèle)
ACTIONS = [
    "intro hp",
    "apply h2",
    "apply h1",
    "exact hp",
    "simp",
    "rfl",
    "linarith"
]


class MCTSNode:
    def __init__(self, state_tactics: list[str], parent: "MCTSNode | None" = None) -> None:
        self.state = state_tactics
        self.parent = parent
        self.children: list[MCTSNode] = []
        self.visits = 0
        self.wins = 0.0

    def add_child(self, tactic: str) -> "MCTSNode":
        child = MCTSNode(self.state + [tactic], parent=self)
        self.children.append(child)
        return child

    def ucb1(self, exploration_weight: float = 1.41) -> float:
        if self.visits == 0:
            return float('inf')
        # UCB1 Formula : Exploitation + Exploration
        exploitation = self.wins / self.visits
        exploration = exploration_weight * math.sqrt(math.log(self.parent.visits) / self.visits)
        return exploitation + exploration


@dataclass
class LeanGateResult:
    """Outcome of a single `lake env lean` proof-gate check."""
    score: float
    output: str


def evaluate_lean_state(tactics: list[str], verifier: LeanKernelVerifier | None = None) -> LeanGateResult:
    """Compiles a candidate proof via `lake env lean` (cwd=formal) and audits its axioms.

    Reuses the contract from anse/formal/lean_runner.py: a non-zero exit code is a
    failure regardless of stdout/stderr content, and `sorryAx` appearing anywhere in
    the output disqualifies an otherwise-successful compile. Score is binary: 1.0
    only when both checks pass, 0.0 otherwise, with the compiler output attached.
    """
    verifier = verifier or LeanKernelVerifier()
    tactic_str = "\n  ".join(tactics)
    if not tactic_str.strip():
        tactic_str = "sorry"

    lean_source = BASE_LEAN.replace("{tactics}", tactic_str)
    lean_file = verifier.formal_dir / ".tmp_mcts_target.lean"

    try:
        lean_file.write_text(lean_source, encoding="utf-8")
        # `lake env lean` (not bare `lean`) so imports resolve against the Mathlib
        # dependency declared in formal/lakefile.toml.
        res = subprocess.run(
            ["lake", "env", "lean", lean_file.name],
            cwd=str(verifier.formal_dir),
            capture_output=True,
            text=True,
        )
    finally:
        if lean_file.exists():
            lean_file.unlink()

    raw_output = (res.stdout + "\n" + res.stderr).strip()

    if res.returncode != 0:
        return LeanGateResult(score=0.0, output=raw_output)

    if "sorryAx" in raw_output:
        return LeanGateResult(score=0.0, output=raw_output)

    return LeanGateResult(score=1.0, output=raw_output)


def mcts_search(iterations: int = 50, max_depth: int = 4) -> list[str] | None:
    root = MCTSNode([])
    print("=== ANSE v7 : Démarrage du Solveur MCTS (Monte Carlo Tree Search) ===")
    print("Objectif : Prouver 'modus_tollens' via Lean 4 LSP\n")

    for i in range(iterations):
        # 1. Sélection (Descente de l'arbre via UCB1)
        node = root
        while len(node.children) == len(ACTIONS) and all(c.visits > 0 for c in node.children):
            node = max(node.children, key=lambda c: c.ucb1())
            if len(node.state) >= max_depth:
                break

        # 2. Expansion (Ajout d'une nouvelle tactique)
        if len(node.state) < max_depth:
            untried = [a for a in ACTIONS if a not in [c.state[-1] for c in node.children if c.state]]
            if untried:
                action = random.choice(untried)
                node = node.add_child(action)

        # 3. Simulation (Évaluation Lean 4 via l'Orchestrateur)
        result = evaluate_lean_state(node.state)
        reward = result.score

        # 4. Rétropropagation (Backpropagation)
        curr: MCTSNode | None = node
        while curr is not None:
            curr.visits += 1
            curr.wins += reward
            curr = curr.parent

        # Log de l'itération
        tactics_str = " -> ".join(node.state)
        print(f"[Iter {i:02d}] Éval: [{tactics_str}] | Récompense (Énergie): {reward}")

        if reward == 1.0:
            print("\n" + "="*50)
            print("🏆 [VICTOIRE MCTS] Preuve formelle trouvée et validée par Lean 4 !")
            print("Chemin de la preuve :")
            for t in node.state:
                print(f"  - {t}")
            print("="*50)
            return node.state

    print("\nRecherche terminée. L'arbre MCTS n'a pas convergé vers une preuve complète.")
    return None


if __name__ == "__main__":
    random.seed(42)  # Fix seed for deterministic demonstration
    mcts_search(iterations=100)
