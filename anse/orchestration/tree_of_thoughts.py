"""
Tree of Thoughts (ToT) Deliberate Problem-Solving Engine for ANSE.
Direct implementation and extension of Yao et al. (NeurIPS 2023, arXiv:2305.10601).
Augments LLM inference with deliberate search algorithms (BFS and DFS with backtracking)
governed by physical energy functions and zero-stub compiler oracles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from anse.orchestration.dichotomic_decomposer import (
    DichotomicTaskNode,
    DichotomyAxis,
    DichotomyEngine,
    TaskStatus,
    ZeroStubAudit,
)


@dataclass
class ThoughtState:
    """
    A state node in the Tree of Thoughts: s = [x, z_1, ..., z_i].
    Represents an intermediate reasoning step or partial solution toward problem x.
    """
    state_id: str
    problem_input: str
    thought_history: List[str] = field(default_factory=list)
    current_thought: str = ""
    depth: int = 0
    value: float = 0.0  # Heuristic value V(s) in [0.0, 1.0]
    energy_score: float = 0.0  # Physical energy E(s)
    is_terminal: bool = False
    is_verified: bool = False
    proof_token: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None
    children: List[ThoughtState] = field(default_factory=list)

    @property
    def path_str(self) -> str:
        return " -> ".join(self.thought_history + ([self.current_thought] if self.current_thought else []))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_id": self.state_id,
            "problem_input": self.problem_input,
            "current_thought": self.current_thought,
            "depth": self.depth,
            "value": round(self.value, 4),
            "energy_score": round(self.energy_score, 4),
            "is_terminal": self.is_terminal,
            "is_verified": self.is_verified,
            "proof_token": self.proof_token,
            "parent_id": self.parent_id,
            "num_children": len(self.children),
        }


class TreeOfThoughtsEngine:
    """
    Orchestrates deliberate problem-solving over trees of intermediate thoughts.
    Implements:
    - Algorithm 1: ToT-BFS (Breadth-First Search with beam pruning)
    - Algorithm 2: ToT-DFS (Depth-First Search with backtracking and dead-end pruning)
    Grounds state evaluation V(s) in physical compiler oracles and zero-stub audits.
    """

    def __init__(self, dichotomy_engine: Optional[DichotomyEngine] = None):
        self.dichotomy_engine = dichotomy_engine or DichotomyEngine()
        self.search_history: List[Dict[str, Any]] = []

    # ── Thought Generation G(p_theta, s, k) ──────────────────────────────────

    def generate_dichotomic_proposals(
        self,
        state: ThoughtState,
        k: int = 2,
    ) -> List[ThoughtState]:
        """
        Thought generator G(s, k): Proposes k structured candidate continuations
        by applying orthogonal dichotomy bifurcation (Yao et al. Section 3, question 2).
        """
        depth = state.depth
        goal = state.current_thought or state.problem_input
        axis, left, right, lot = self.dichotomy_engine._plan_dichotomy(goal, depth)

        candidates = []
        # Candidate 1: Left orthogonal branch
        s_left = ThoughtState(
            state_id=f"{state.state_id}.1",
            problem_input=state.problem_input,
            thought_history=state.thought_history + ([state.current_thought] if state.current_thought else []),
            current_thought=left,
            depth=depth + 1,
            parent_id=state.state_id,
            metadata={"axis": axis.value, "lot": lot, "branch": "left"},
        )
        candidates.append(s_left)

        # Candidate 2: Right orthogonal branch
        s_right = ThoughtState(
            state_id=f"{state.state_id}.2",
            problem_input=state.problem_input,
            thought_history=state.thought_history + ([state.current_thought] if state.current_thought else []),
            current_thought=right,
            depth=depth + 1,
            parent_id=state.state_id,
            metadata={"axis": axis.value, "lot": lot, "branch": "right"},
        )
        candidates.append(s_right)

        state.children = candidates
        return candidates[:k]

    # ── State Evaluation V(p_theta, S) ──────────────────────────────────────

    def evaluate_state_hardness(
        self,
        state: ThoughtState,
        source_code: Optional[str] = None,
        custom_verifier: Optional[Callable[[ThoughtState], Tuple[bool, float, Dict[str, Any]]]] = None,
    ) -> float:
        """
        Physical State Evaluator V(s): Evaluates progress and viability of state s.
        Maps objective computational physics (compiler exit codes, zero stubs, latency)
        to a bounded valuation heuristic V(s) in [0.0, 1.0].
        
        Law of Maximum Pain: If a stub is detected or compiler fails, E = 10^6 and V(s) = 0.0.
        """
        # 1. Custom verifier if provided
        if custom_verifier:
            passed, energy, details = custom_verifier(state)
            state.energy_score = energy
            state.is_verified = passed
            if passed and energy < 1e5:
                state.value = float(math.exp(-energy / 10.0))
                token_payload = f"{state.state_id}:{state.current_thought}:{energy}"
                state.proof_token = hashlib.sha256(token_payload.encode("utf-8")).hexdigest()
            else:
                state.value = 0.0
            return state.value

        # 2. Zero-Stub AST Audit
        if source_code:
            if "lean" in state.current_thought.lower():
                audit = ZeroStubAudit.audit_lean_code(source_code)
            else:
                audit = ZeroStubAudit.audit_python_code(source_code)

            if not audit.is_clean:
                state.energy_score = 1e6
                state.value = 0.0
                state.is_verified = False
                state.metadata["rejection_reason"] = "STUB_DETECTED"
                state.metadata["violations"] = audit.violations
                return 0.0

        # 3. Deterministic Acceptance Command Evaluation
        cmd = self.dichotomy_engine._derive_leaf_acceptance_command(state.current_thought)
        axis = state.metadata.get("axis", DichotomyAxis.SPEC_VS_KERNEL)
        if isinstance(axis, str):
            try:
                axis = DichotomyAxis(axis)
            except ValueError:
                axis = DichotomyAxis.SPEC_VS_KERNEL
        lot = state.metadata.get("lot", "Tree of Thoughts deliberate reasoning step")

        node = DichotomicTaskNode(
            task_id=state.state_id,
            goal=state.current_thought,
            line_of_thought=lot,
            dichotomy_axis=axis,
            acceptance_command=cmd,
        )

        self.dichotomy_engine.execute_leaf(node, source_code=source_code)
        state.energy_score = node.energy_score
        state.is_verified = (node.status == TaskStatus.VERIFIED)
        state.proof_token = node.proof_token

        if state.is_verified and state.energy_score < 1e5:
            # High reward for physically confirmed low-energy solutions
            state.value = float(math.exp(-state.energy_score / 10.0))
        else:
            state.value = 0.0

        return state.value

    # ── Search Algorithm 1: ToT-BFS (Breadth-First Search) ───────────────────

    def search_bfs(
        self,
        problem_input: str,
        step_limit: int = 2,
        breadth_limit: int = 2,
        candidate_k: int = 2,
        code_generator: Optional[Callable[[ThoughtState], str]] = None,
    ) -> Tuple[Optional[ThoughtState], List[List[ThoughtState]]]:
        """
        Algorithm 1: ToT-BFS(x, p_theta, G, k, V, T, b) from Yao et al. (2023).
        Maintains a set S_t of the b most promising states per step level.
        Prunes suboptimal branches based on physical evaluator V(s).
        """
        root = ThoughtState(
            state_id="root",
            problem_input=problem_input,
            current_thought=problem_input,
            depth=0,
        )
        self.evaluate_state_hardness(root)

        current_frontier: List[ThoughtState] = [root]
        tree_history: List[List[ThoughtState]] = [[root]]

        for t in range(1, step_limit + 1):
            candidates_t: List[ThoughtState] = []

            # Generate k candidates for each state in current frontier
            for state in current_frontier:
                proposals = self.generate_dichotomic_proposals(state, k=candidate_k)
                candidates_t.extend(proposals)

            if not candidates_t:
                break

            # Evaluate each proposed state
            for cand in candidates_t:
                code = code_generator(cand) if code_generator else None
                self.evaluate_state_hardness(cand, source_code=code)

            # Sort candidates by heuristic valuation V(s) descending.
            # Tiebreaker: non-stub candidates rank above stub-detected ones (STUB_DETECTED
            # is the rejection reason when a 'pass' / '...' stub is found by ZeroStubAudit).
            # This ensures deterministic pruning: a clean-code candidate always beats a stub
            # even when both receive value=0.0 (e.g., acceptance command unavailable).
            def _sort_key(s: ThoughtState):
                is_stub = s.metadata.get("rejection_reason") == "STUB_DETECTED"
                return (s.value, not is_stub)  # (primary: value DESC, secondary: non-stub first)

            candidates_t.sort(key=_sort_key, reverse=True)

            # Prune to breadth limit b (beam width)
            current_frontier = candidates_t[:breadth_limit]
            tree_history.append(current_frontier)

            # Log search step
            self.search_history.append({
                "algorithm": "ToT-BFS",
                "step": t,
                "total_candidates": len(candidates_t),
                "selected_frontier": [s.to_dict() for s in current_frontier],
            })

        best_state = current_frontier[0] if current_frontier else None
        return best_state, tree_history

    # ── Search Algorithm 2: ToT-DFS (Depth-First with Backtracking) ──────────

    def search_dfs(
        self,
        problem_input: str,
        step_limit: int = 2,
        value_threshold: float = 0.05,
        candidate_k: int = 2,
        code_generator: Optional[Callable[[ThoughtState], str]] = None,
    ) -> Tuple[Optional[ThoughtState], List[ThoughtState]]:
        """
        Algorithm 2: ToT-DFS(s, t, p_theta, G, k, V, T, v_th) from Yao et al. (2023).
        Explores the most promising thoughts depth-first.
        Backtracks immediately when state evaluator V(s) <= v_th (e.g. stub violation E=10^6).
        """
        root = ThoughtState(
            state_id="root",
            problem_input=problem_input,
            current_thought=problem_input,
            depth=0,
        )
        self.evaluate_state_hardness(root)

        visited_states: List[ThoughtState] = []
        verified_leaves: List[ThoughtState] = []

        def _dfs(state: ThoughtState, t: int) -> Optional[ThoughtState]:
            visited_states.append(state)

            # Terminal condition: reached step limit
            if t >= step_limit:
                state.is_terminal = True
                if state.is_verified and state.value > value_threshold:
                    verified_leaves.append(state)
                    return state
                return None

            # Generate candidate thoughts
            candidates = self.generate_dichotomic_proposals(state, k=candidate_k)

            # Evaluate candidates
            valid_candidates: List[ThoughtState] = []
            for cand in candidates:
                code = code_generator(cand) if code_generator else None
                val = self.evaluate_state_hardness(cand, source_code=code)
                if val <= value_threshold:
                    self.search_history.append({
                        "algorithm": "ToT-DFS",
                        "action": "PRUNED_AND_BACKTRACK",
                        "state_id": cand.state_id,
                        "value": cand.value,
                        "energy": cand.energy_score,
                    })
                else:
                    valid_candidates.append(cand)

            # Sort valid candidates by valuation descending
            valid_candidates.sort(key=lambda s: s.value, reverse=True)

            for cand in valid_candidates:
                # Recurse down the branch
                result = _dfs(cand, t + 1)
                if result is not None:
                    return result

            # Backtracking: no successful path found down this subtree
            return None

        solution = _dfs(root, 0)
        return solution, visited_states

