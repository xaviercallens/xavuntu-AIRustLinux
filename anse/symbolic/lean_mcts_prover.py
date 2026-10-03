"""
ANSE Autonomous Neuro-Symbolic MCTS Theorem Prover.

Integrates:
1. Mathlib4 Premise Selection (ChromaDB Vector RAG)
2. LeanCompilerREPL (lake env lean step-by-step verification)
3. Red Team Semantic Radar (Fail-closed anti-cheat gate)
4. EnergyCriticPolicy (RL fine-tuned heuristic prior)
5. Monte Carlo Tree Search (UCB1 exploration & backtracking)

Refuses epistemic shortcuts: any branch that attempts trivialization (sorry, admit,
or scalar flattening of complex topology) is instantly pruned with Maximum Pain Q = -100.0.
"""

from __future__ import annotations

import logging
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple

import torch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anse.symbolic.lean_rag_dojo import LeanCompilerREPL, MathlibPremiseRetriever
from antigravity_harness.core.neuro_symbolic_harness import RedTeamSemanticRadar
from anse.guard.critic import EnergyCriticPolicy, tokenize_string

logger = logging.getLogger("ANSE.LeanMCTSProver")


@dataclass
class MCTSProofNode:
    """A node in the Lean 4 proof search tree."""

    tactic_sequence: List[str]
    parent: Optional[MCTSProofNode] = None
    children: List[MCTSProofNode] = field(default_factory=list)
    visits: int = 0
    total_value: float = 0.0
    unsolved_goals: List[str] = field(default_factory=list)
    compiler_message: str = ""
    is_terminal: bool = False
    is_proven: bool = False
    is_cheat: bool = False
    depth: int = 0

    @property
    def q_value(self) -> float:
        """Mean action-value Q(s)."""
        if self.visits == 0:
            return 0.0
        return self.total_value / self.visits

    def ucb1_score(self, c_puct: float = 1.414) -> float:
        """Upper Confidence Bound for Trees."""
        if not self.parent or self.parent.visits == 0:
            return self.q_value
        exploration = c_puct * math.sqrt(math.log(self.parent.visits + 1) / (1 + self.visits))
        return self.q_value + exploration


class LeanMCTSProver:
    """
    Autonomous MCTS Theorem Prover for Lean 4 with Mathlib premise selection
    and zero-trust Red Team attestation.
    """

    def __init__(
        self,
        retriever: Optional[MathlibPremiseRetriever] = None,
        repl: Optional[LeanCompilerREPL] = None,
        radar: Optional[RedTeamSemanticRadar] = None,
        critic_weights_path: Optional[str | Path] = None,
        work_dir: str = "formal",
    ) -> None:
        self.retriever = retriever or MathlibPremiseRetriever()
        self.repl = repl or LeanCompilerREPL(work_dir=work_dir)
        self.radar = radar or RedTeamSemanticRadar()
        self.device = torch.device("cpu")

        # Load RL Critic Policy if available
        self.critic: Optional[EnergyCriticPolicy] = None
        weights_file = Path(critic_weights_path or (REPO_ROOT / "results/rl_100_formal_critic.pt"))
        if weights_file.exists():
            try:
                self.critic = EnergyCriticPolicy(d_model=32, d_hidden=64).to(self.device)
                self.critic.load_state_dict(torch.load(weights_file, map_location=self.device, weights_only=True))
                self.critic.eval()
                logger.info(f"Loaded RL Critic Policy weights from {weights_file}")
            except Exception as e:
                logger.warning(f"Could not load critic weights: {e}")

    def generate_candidate_tactics(
        self,
        current_node: MCTSProofNode,
        theorem_signature: str,
        retrieved_premises: List[str],
    ) -> List[str]:
        """
        Generates tactical moves:
        1. Domain-specific closing tactics (linarith, positivity, ring, etc.)
        2. Exact premise application from Mathlib RAG
        3. Structural tactics (intro, intros, rfl, etc.)
        """
        candidates: List[str] = [
            "linarith",
            "ring",
            "positivity",
            "rfl",
            "simp",
            "dsimp",
            "intro",
            "intros",
            "assumption",
            "norm_num",
            "ext",
            "split_ifs",
        ]

        # 2. RAG-derived exact & apply candidates
        for prem in retrieved_premises:
            if prem.strip():
                prem_name = prem.split()[0].strip()
                if prem_name and len(prem_name) < 50:
                    candidates.append(f"exact {prem_name}")
                    candidates.append(f"apply {prem_name}")
                    candidates.append(f"rw [{prem_name}]")

        # De-duplicate while preserving order
        seen = set(current_node.tactic_sequence)
        unique_candidates = []
        for c in candidates:
            if c not in seen:
                unique_candidates.append(c)
        return unique_candidates[:12]

    def evaluate_tactic_sequence(
        self,
        theorem_name: str,
        theorem_signature: str,
        required_imports: List[str],
        tactic_sequence: List[str],
    ) -> Tuple[bool, bool, float, List[str], str]:
        """
        Evaluates a sequence of tactics.
        Returns: (is_proven, is_cheat, reward_value, unsolved_goals, compiler_message)
        """
        proof_body = "\n".join(f"  {tac}" for tac in tactic_sequence)
        full_code = f"theorem {theorem_name} {theorem_signature} := by\n{proof_body}\n"

        # 1. Red Team Anti-Cheat Gate (Fail-Closed)
        is_cheat, cheat_reason = self.radar.audit_code(full_code, title=theorem_name, domain="MCTS")
        if is_cheat:
            logger.warning(f"[FAIL-CLOSED] Red Team caught cheat: {cheat_reason}")
            return False, True, -100.0, [], f"REJECT: {cheat_reason}"

        # 2. Compiler REPL Verification
        success, message, goals = self.repl.run_proof_attempt(required_imports, full_code)

        if success and len(goals) == 0:
            # 0 unsolved goals: Complete formal proof
            reward = 10.0
            return True, False, reward, [], message

        # Intermediate node evaluation
        if "unsolved goals" in message or len(goals) > 0:
            reward = 1.0 - (0.5 * len(goals))
        elif "error" in message.lower():
            reward = -2.0
        else:
            reward = -0.5

        # 3. Add RL Critic Prior if loaded
        if self.critic is not None:
            try:
                p_t = tokenize_string(theorem_signature).unsqueeze(0).to(self.device)
                c_t = tokenize_string(proof_body).unsqueeze(0).to(self.device)
                with torch.no_grad():
                    critic_bonus = float(self.critic(p_t, c_t).item())
                reward += 0.2 * max(-5.0, min(5.0, critic_bonus))
            except Exception:
                pass

        return False, False, reward, goals, message

    def search(
        self,
        theorem_name: str,
        theorem_signature: str,
        required_imports: List[str],
        max_iterations: int = 15,
        max_depth: int = 4,
        c_puct: float = 1.414,
    ) -> dict[str, Any]:
        """
        Runs Monte Carlo Tree Search to synthesize and verify a sound Lean 4 proof.
        """
        start_time = time.time()
        logger.info(f"Initiating MCTS Proof Search for '{theorem_name}' (max_iter={max_iterations}, depth={max_depth})...")

        # 1. Retrieve premises via Vector RAG
        rag_context = self.retriever.retrieve_mathlib_premises(theorem_signature, top_k=5)
        retrieved_premises: List[str] = []
        for line in rag_context.splitlines():
            line = line.strip()
            if line and not line.startswith("USEFUL") and not line.startswith("import") and not line.startswith("--"):
                retrieved_premises.append(line)

        root = MCTSProofNode(tactic_sequence=[])
        proven_node: Optional[MCTSProofNode] = None
        cheats_intercepted = 0
        nodes_explored = 1

        for it in range(max_iterations):
            # 1. SELECTION
            curr = root
            while curr.children and not curr.is_terminal and curr.depth < max_depth:
                # Prefer unvisited children
                unvisited = [c for c in curr.children if c.visits == 0 and not c.is_cheat]
                if unvisited:
                    curr = unvisited[0]
                    break
                valid_children = [c for c in curr.children if not c.is_cheat]
                if not valid_children:
                    break
                curr = max(valid_children, key=lambda c: c.ucb1_score(c_puct))

            if curr.is_terminal:
                if curr.is_proven:
                    proven_node = curr
                    break
                continue

            # 2. EXPANSION (if needed)
            if not curr.children and curr.depth < max_depth and not curr.is_terminal:
                candidate_tactics = self.generate_candidate_tactics(
                    curr, theorem_signature, retrieved_premises
                )
                for tac in candidate_tactics:
                    new_seq = curr.tactic_sequence + [tac]
                    child = MCTSProofNode(
                        tactic_sequence=new_seq,
                        parent=curr,
                        depth=curr.depth + 1,
                    )
                    curr.children.append(child)
                    nodes_explored += 1
                if curr.children:
                    curr = curr.children[0]

            # 3. EVALUATION
            if not curr.is_terminal and curr.tactic_sequence:
                is_proven, is_cheat, value, goals, msg = self.evaluate_tactic_sequence(
                    theorem_name, theorem_signature, required_imports, curr.tactic_sequence
                )
                curr.is_proven = is_proven
                curr.is_cheat = is_cheat
                curr.is_terminal = is_proven or is_cheat
                curr.unsolved_goals = goals
                curr.compiler_message = msg

                if is_cheat:
                    cheats_intercepted += 1

                if is_proven:
                    proven_node = curr
                    b_node: Optional[MCTSProofNode] = curr
                    while b_node:
                        b_node.visits += 1
                        b_node.total_value += 10.0
                        b_node = b_node.parent
                    break

                # 4. BACKPROPAGATION
                b_node = curr
                while b_node:
                    b_node.visits += 1
                    b_node.total_value += value
                    b_node = b_node.parent
                b_node.total_value += value
                b_node = b_node.parent

        elapsed_ms = (time.time() - start_time) * 1000.0

        if proven_node:
            proof_code = f"theorem {theorem_name} {theorem_signature} := by\n" + "\n".join(f"  {tac}" for tac in proven_node.tactic_sequence) + "\n"
            return {
                "success": True,
                "status": "VERIFIED_SOUND",
                "theorem_name": theorem_name,
                "proof_tactics": proven_node.tactic_sequence,
                "lean_code": proof_code,
                "nodes_explored": nodes_explored,
                "cheats_intercepted": cheats_intercepted,
                "elapsed_ms": round(elapsed_ms, 2),
                "terminal_q": round(proven_node.q_value, 4),
            }

        # Failure / Deep exploration required
        return {
            "success": False,
            "status": "UNSOLVED_DEEP_MCTS_REQUIRED",
            "theorem_name": theorem_name,
            "proof_tactics": root.tactic_sequence,
            "lean_code": "",
            "nodes_explored": nodes_explored,
            "cheats_intercepted": cheats_intercepted,
            "elapsed_ms": round(elapsed_ms, 2),
            "terminal_q": 0.0,
        }
