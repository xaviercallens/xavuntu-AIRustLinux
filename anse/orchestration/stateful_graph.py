"""
LangGraph-inspired stateful, cyclical graph execution engine for ANSE Dichotomy.
Orchestrates state flow down the tree to worker agents and aggregates
verified cryptographic proof tokens back up with checkpointing and retry cycles.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from anse.orchestration.dichotomic_decomposer import (
    DichotomicTaskNode,
    DichotomyEngine,
    TaskStatus,
)
from anse.orchestration.repo_map import RepoMapGenerator


@dataclass
class DichotomyGraphState:
    """Stateful context flowing through the LangGraph-style workflow."""
    root_goal: str
    token_budget: int = 16000
    max_depth: int = 2
    repo_map: str = ""
    nodes_map: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    leaf_queue: List[str] = field(default_factory=list)
    current_leaf_id: Optional[str] = None
    verified_proofs: Dict[str, str] = field(default_factory=dict)
    retry_counts: Dict[str, int] = field(default_factory=dict)
    energy_ledger: Dict[str, float] = field(default_factory=dict)
    is_finished: bool = False
    step_history: List[str] = field(default_factory=list)
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)


class StatefulDichotomyGraph:
    """
    Executes the dichotomic decomposition and leaf verification as a stateful
    cyclical Directed Acyclic Graph (DAG) with immutable checkpointing.
    """

    def __init__(
        self,
        engine: Optional[DichotomyEngine] = None,
        repo_mapper: Optional[RepoMapGenerator] = None,
        max_retries: int = 3,
    ):
        self.engine = engine or DichotomyEngine()
        self.repo_mapper = repo_mapper or RepoMapGenerator()
        self.max_retries = max_retries
        self.checkpoints: List[DichotomyGraphState] = []

    def checkpoint(self, state: DichotomyGraphState, step_name: str) -> None:
        """Saves an immutable snapshot of graph state."""
        ts = time.time()
        state.step_history.append(f"{step_name} @ {ts:.2f}")
        state.checkpoints.append({
            "step": step_name,
            "timestamp": ts,
            "verified_count": len(state.verified_proofs),
            "remaining_leaves": len(state.leaf_queue),
            "finished": state.is_finished,
        })
        self.checkpoints.append(copy.deepcopy(state))

    # ── Node Implementations ────────────────────────────────────────────────

    def node_repo_map(self, state: DichotomyGraphState) -> DichotomyGraphState:
        """Node 1: Extract compact repository structural tags."""
        state.repo_map = self.repo_mapper.generate_repo_map(query=state.root_goal, max_tokens=800)
        self.checkpoint(state, "node_repo_map")
        return state

    def node_decompose(self, state: DichotomyGraphState) -> Tuple[DichotomyGraphState, DichotomicTaskNode]:
        """Node 2: Bifurcate problem into binary subtask tree."""
        root = self.engine.decompose(
            goal=state.root_goal,
            context={"interfaces": {"repo_map": state.repo_map}},
            total_budget=state.token_budget,
            max_depth=state.max_depth,
        )

        all_nodes = root.get_all_nodes()
        state.nodes_map = {n.task_id: n.to_dict() for n in all_nodes}
        state.leaf_queue = [l.task_id for l in root.get_all_leaves()]
        self.checkpoint(state, "node_decompose")
        return state, root

    def node_exec_leaf(
        self,
        state: DichotomyGraphState,
        root: DichotomicTaskNode,
        leaf_sources: Optional[Dict[str, str]] = None,
    ) -> DichotomyGraphState:
        """Node 3: Execute and audit current leaf task."""
        if not state.leaf_queue:
            state.is_finished = True
            return state

        leaf_id = state.leaf_queue[0]
        state.current_leaf_id = leaf_id
        leaf_sources = leaf_sources or {}

        # Locate leaf object in tree
        leaves = {l.task_id: l for l in root.get_all_leaves()}
        target_leaf = leaves.get(leaf_id)
        if not target_leaf:
            state.leaf_queue.pop(0)
            return state

        src = leaf_sources.get(leaf_id)
        self.engine.execute_leaf(target_leaf, source_code=src)

        # Update state with leaf receipt
        state.nodes_map[leaf_id] = target_leaf.to_dict()
        state.energy_ledger[leaf_id] = target_leaf.energy_score

        if target_leaf.status == TaskStatus.VERIFIED:
            state.verified_proofs[leaf_id] = target_leaf.proof_token or ""
            state.leaf_queue.pop(0)  # Advance queue
            self.checkpoint(state, f"leaf_verified_{leaf_id}")
        else:
            # Increment retry count
            state.retry_counts[leaf_id] = state.retry_counts.get(leaf_id, 0) + 1
            if state.retry_counts[leaf_id] >= self.max_retries:
                # Max retries exceeded; mark permanently rejected
                state.leaf_queue.pop(0)
                self.checkpoint(state, f"leaf_failed_max_retries_{leaf_id}")
            else:
                self.checkpoint(state, f"leaf_retry_{leaf_id}_attempt_{state.retry_counts[leaf_id]}")

        return state

    def node_synthesize(
        self,
        state: DichotomyGraphState,
        root: DichotomicTaskNode,
    ) -> DichotomyGraphState:
        """Node 4: Synthesize parent nodes bottom-up once leaves verify."""
        def _synth(n: DichotomicTaskNode):
            if n.is_leaf:
                return
            if n.left_child:
                _synth(n.left_child)
            if n.right_child:
                _synth(n.right_child)
            self.engine.synthesize_node(n)
            state.nodes_map[n.task_id] = n.to_dict()
            if n.status == TaskStatus.VERIFIED and n.proof_token:
                state.verified_proofs[n.task_id] = n.proof_token

        _synth(root)
        state.is_finished = True
        self.checkpoint(state, "node_synthesize")
        return state

    def run(
        self,
        goal: str,
        total_budget: int = 16000,
        max_depth: int = 2,
        leaf_sources: Optional[Dict[str, str]] = None,
    ) -> DichotomyGraphState:
        """
        Runs the stateful cyclical graph to completion.
        """
        state = DichotomyGraphState(
            root_goal=goal,
            token_budget=total_budget,
            max_depth=max_depth,
        )

        state = self.node_repo_map(state)
        state, root = self.node_decompose(state)

        # Cyclical loop over leaves
        while state.leaf_queue:
            state = self.node_exec_leaf(state, root, leaf_sources=leaf_sources)

        state = self.node_synthesize(state, root)
        return state
