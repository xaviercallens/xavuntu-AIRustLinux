"""
Stanford DSPy-inspired programmatic pipeline for ANSE Dichotomic Hardness.
Replaces unstructured prompting with typed signatures:
  SplitProblem -> GenerateCode -> Compile -> IfFail(Retry)
optimizing prompts against the objective physical energy functional.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from anse.orchestration.dichotomic_decomposer import (
    DichotomicTaskNode,
    DichotomyAxis,
    DichotomyEngine,
    TaskStatus,
    ZeroStubAudit,
)
from anse.orchestration.repo_map import RepoMapGenerator, apply_unified_diff


@dataclass
class DSPySignature:
    """Represents a typed input/output contract inspired by dspy.Signature."""
    name: str
    description: str
    inputs: Dict[str, str]
    outputs: Dict[str, str]


# ── Canonical Typed Signatures ──────────────────────────────────────────────

DichotomySplitSignature = DSPySignature(
    name="DichotomySplit",
    description="Recursively bifurcates a complex goal into mutually exclusive sub-goals.",
    inputs={"goal": "str", "repo_map": "str", "token_budget": "int"},
    outputs={"axis": "DichotomyAxis", "line_of_thought": "str", "left_goal": "str", "right_goal": "str"},
)

CodeGenerationSignature = DSPySignature(
    name="CodeGeneration",
    description="Generates an atomic, zero-stub code patch and acceptance test.",
    inputs={"subtask_goal": "str", "repo_map_slice": "str", "leaf_budget": "int"},
    outputs={"code_diff": "str", "test_command": "str"},
)

VerificationSignature = DSPySignature(
    name="Verification",
    description="Evaluates physical energy invariants and compiles formal proofs.",
    inputs={"code": "str", "stdout": "str", "stderr": "str", "returncode": "int"},
    outputs={"is_verified": "bool", "proof_token": "str", "energy": "float"},
)


# ── Metric: Physical Energy Reward ──────────────────────────────────────────

def physical_hardness_metric(prediction: Dict[str, Any]) -> float:
    """
    Computes DSPy optimization reward based on the Physical Energy functional:
    Reward in [0.0, 1.0], where E = 10^6 (stubs/crash) yields 0.0 reward.
    """
    if not prediction.get("passed", False):
        return 0.0
    energy = prediction.get("energy_score", 1e6)
    if energy >= 1e6:
        return 0.0
    # Higher reward for lower energy (faster execution, less memory, 0 stubs)
    return round(1.0 / (1.0 + 0.1 * energy), 4)


# ── DSPy Programmatic Pipeline Module ────────────────────────────────────────

class DichotomyPipelineModule:
    """
    DSPy-style programmatic module executing:
      SplitProblem -> GenerateCode -> Compile/Verify -> IfFail(Retry)
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

    def forward(
        self,
        goal: str,
        total_budget: int = 16000,
        max_depth: int = 2,
        leaf_code_generator: Optional[Callable[[DichotomicTaskNode, str], str]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the full programmatic pipeline with self-correcting retry cycles.
        """
        # 1. Generate Compact Repo Map (< 800 tokens)
        repo_map = self.repo_mapper.generate_repo_map(query=goal, max_tokens=800)

        # 2. Split Problem by Dichotomy
        root_node = self.engine.decompose(
            goal=goal,
            context={"interfaces": {"repo_map": repo_map}},
            total_budget=total_budget,
            max_depth=max_depth,
        )

        leaves = root_node.get_all_leaves()
        execution_trace: List[Dict[str, Any]] = []

        # 3. Leaf Execution with Zero-Stub Hardness & Retry Loops
        for leaf in leaves:
            attempt = 0
            verified = False
            last_receipt: Dict[str, Any] = {}

            while attempt < self.max_retries and not verified:
                attempt += 1
                code = None
                if leaf_code_generator:
                    code = leaf_code_generator(leaf, repo_map)

                # Execute and audit leaf
                self.engine.execute_leaf(leaf, source_code=code)

                reward = physical_hardness_metric({
                    "passed": leaf.status == TaskStatus.VERIFIED,
                    "energy_score": leaf.energy_score,
                })

                last_receipt = {
                    "task_id": leaf.task_id,
                    "attempt": attempt,
                    "status": leaf.status.value,
                    "energy": leaf.energy_score,
                    "reward": reward,
                    "proof_token": leaf.proof_token,
                }

                if leaf.status == TaskStatus.VERIFIED:
                    verified = True
                else:
                    # Retry: adjust context with feedback for next iteration
                    leaf.context_slice["last_error"] = leaf.verification_receipt.get("error", "Failed")

            execution_trace.append(last_receipt)

        # 4. Bottom-up proof synthesis
        def _synth(n: DichotomicTaskNode):
            if n.is_leaf:
                return
            if n.left_child:
                _synth(n.left_child)
            if n.right_child:
                _synth(n.right_child)
            self.engine.synthesize_node(n)

        _synth(root_node)

        return {
            "root_task_id": root_node.task_id,
            "root_status": root_node.status.value,
            "root_proof_token": root_node.proof_token,
            "total_energy": root_node.energy_score,
            "leaves_verified": sum(1 for l in leaves if l.status == TaskStatus.VERIFIED),
            "total_leaves": len(leaves),
            "execution_trace": execution_trace,
            "repo_map_tokens": len(repo_map) // 4,
            "tree_dict": root_node.to_dict(),
        }
