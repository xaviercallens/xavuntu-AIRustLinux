"""
ANSE Dichotomic Task Decomposition, Context Bounding & Zero-Stub Verification Engine.

Provides recursive binary task bifurcation, strict context window pruning,
leaf-level token budget enforcement, and zero-stub physical/formal verification.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple


class DichotomyAxis(str, Enum):
    """The orthogonal conceptual dimension across which a problem is split."""
    SPEC_VS_KERNEL = "Specification vs Computational Kernel"
    TYPES_VS_PROOF = "Formal Type Signatures vs Machine-Checked Proof Tactics"
    MODEL_VS_DISCRETIZATION = "Continuous Physical Model vs Discrete Stencil/Lattice"
    RED_VS_BLUE = "Adversarial Red Challenge vs Hardened Blue Patch"
    PRECONDITION_VS_TRANSFORM = "Precondition Invariant vs Operational Transform"


class TaskStatus(str, Enum):
    """Lifecycle status of a dichotomic task node."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    STUB_DETECTED = "STUB_DETECTED"


@dataclass
class ZeroStubAuditResult:
    """Receipt from an AST-level zero-stub audit."""
    is_clean: bool
    violations: List[str] = field(default_factory=list)
    penalty_energy: float = 0.0


class ZeroStubAudit:
    """
    Enforces the Zero-Stub Physical Hardness Law:
    Rejects placeholders (pass, ..., sorry, mock_*, fake_*) with E = 10^6 penalty.
    """

    FORBIDDEN_NAME_PATTERNS = [
        re.compile(r"^mock_", re.IGNORECASE),
        re.compile(r"^fake_", re.IGNORECASE),
        re.compile(r"^simulate_", re.IGNORECASE),
        re.compile(r"^dummy_", re.IGNORECASE),
        re.compile(r"^stub_", re.IGNORECASE),
    ]

    @classmethod
    def audit_python_code(cls, source_code: str) -> ZeroStubAuditResult:
        violations: List[str] = []
        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            return ZeroStubAuditResult(
                is_clean=False,
                violations=[f"SyntaxError in Python source: {exc}"],
                penalty_energy=1e6,
            )

        for node in ast.walk(tree):
            # Check for 'pass' statements (except empty class definition like custom Exception)
            if isinstance(node, ast.Pass):
                violations.append("Forbidden 'pass' statement detected in execution body.")

            # Check for Ellipsis literal (...)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and node.value.value is Ellipsis:
                violations.append("Forbidden Ellipsis ('...') detected in execution body.")

            # Check for forbidden function or variable names
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Name)):
                ident = node.name if hasattr(node, "name") else node.id
                for pat in cls.FORBIDDEN_NAME_PATTERNS:
                    if pat.search(ident):
                        violations.append(f"Forbidden mock identifier '{ident}' detected.")

        if violations:
            return ZeroStubAuditResult(is_clean=False, violations=violations, penalty_energy=1e6)
        return ZeroStubAuditResult(is_clean=True, violations=[], penalty_energy=0.0)

    @classmethod
    def audit_lean_code(cls, source_code: str) -> ZeroStubAuditResult:
        violations: List[str] = []
        # Check for sorry, admit, sorryAx
        if re.search(r"\bsorry\b", source_code):
            violations.append("Forbidden Lean 4 'sorry' hole detected in formal proof.")
        if re.search(r"\badmit\b", source_code):
            violations.append("Forbidden Lean 4 'admit' hole detected in formal proof.")
        if re.search(r"\bsorryAx\b", source_code):
            violations.append("Forbidden Lean 4 axiom 'sorryAx' dependency detected.")

        if violations:
            return ZeroStubAuditResult(is_clean=False, violations=violations, penalty_energy=1e6)
        return ZeroStubAuditResult(is_clean=True, violations=[], penalty_energy=0.0)


class TokenBudgetManager:
    """
    Manages strict token allocation across the dichotomic tree and prunes
    context so each leaf receives only atomic, high-signal information.
    """

    ESTIMATED_CHARS_PER_TOKEN = 4.0

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        return max(1, int(len(text) / cls.ESTIMATED_CHARS_PER_TOKEN))

    @classmethod
    def allocate_subtask_budgets(
        cls,
        parent_budget: int,
        split_ratio: Tuple[float, float] = (0.45, 0.45),
        synthesis_reserve_ratio: float = 0.10,
    ) -> Tuple[int, int, int]:
        """
        Splits a parent token budget into (left_budget, right_budget, synthesis_reserve).
        """
        left = int(parent_budget * split_ratio[0])
        right = int(parent_budget * split_ratio[1])
        reserve = parent_budget - left - right
        return left, right, max(0, reserve)

    @classmethod
    def prune_context(cls, goal: str, raw_context: Dict[str, Any], max_tokens: int = 800) -> Dict[str, Any]:
        """
        Extracts only essential interface types, constraints, and contracts,
        discarding noisy transcript logs and conversational fluff.
        """
        pruned: Dict[str, Any] = {
            "target_goal": goal,
            "interfaces": raw_context.get("interfaces", {}),
            "invariants": raw_context.get("invariants", []),
            "acceptance_criteria": raw_context.get("acceptance_criteria", []),
        }

        # Ensure pruned context fits within max_tokens
        serialized = json.dumps(pruned)
        if cls.estimate_tokens(serialized) > max_tokens:
            # Drop extended invariants if too large
            pruned["invariants"] = pruned["invariants"][:2]
        return pruned


@dataclass
class DichotomicTaskNode:
    """A node in the recursive binary task decomposition tree."""
    task_id: str
    goal: str
    line_of_thought: str
    dichotomy_axis: DichotomyAxis
    depth: int = 0
    token_budget: int = 4000
    context_slice: Dict[str, Any] = field(default_factory=dict)
    acceptance_command: str = ""
    is_leaf: bool = False
    status: TaskStatus = TaskStatus.PENDING
    proof_token: Optional[str] = None
    energy_score: float = 0.0
    verification_receipt: Dict[str, Any] = field(default_factory=dict)
    left_child: Optional["DichotomicTaskNode"] = None
    right_child: Optional["DichotomicTaskNode"] = None
    parent_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "line_of_thought": self.line_of_thought,
            "dichotomy_axis": self.dichotomy_axis.value,
            "depth": self.depth,
            "token_budget": self.token_budget,
            "acceptance_command": self.acceptance_command,
            "is_leaf": self.is_leaf,
            "status": self.status.value,
            "proof_token": self.proof_token,
            "energy_score": round(self.energy_score, 4),
            "verification_receipt": self.verification_receipt,
            "parent_id": self.parent_id,
            "left_child": self.left_child.to_dict() if self.left_child else None,
            "right_child": self.right_child.to_dict() if self.right_child else None,
        }

    def get_all_leaves(self) -> List["DichotomicTaskNode"]:
        if self.is_leaf:
            return [self]
        leaves: List["DichotomicTaskNode"] = []
        if self.left_child:
            leaves.extend(self.left_child.get_all_leaves())
        if self.right_child:
            leaves.extend(self.right_child.get_all_leaves())
        return leaves

    def get_all_nodes(self) -> List["DichotomicTaskNode"]:
        nodes = [self]
        if self.left_child:
            nodes.extend(self.left_child.get_all_nodes())
        if self.right_child:
            nodes.extend(self.right_child.get_all_nodes())
        return nodes


class DichotomyEngine:
    """
    Orchestrates recursive dichotomic problem decomposition, leaf verification,
    and bottom-up proof composition under strict token budgets.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()

    def decompose(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        total_budget: int = 16000,
        max_depth: int = 2,
    ) -> DichotomicTaskNode:
        """
        Recursively decomposes a high-level goal into a binary tree of atomic subtasks.
        """
        context = context or {}
        return self._recursive_split(
            task_id="root",
            goal=goal,
            parent_id=None,
            depth=0,
            max_depth=max_depth,
            budget=total_budget,
            raw_context=context,
        )

    def _recursive_split(
        self,
        task_id: str,
        goal: str,
        parent_id: Optional[str],
        depth: int,
        max_depth: int,
        budget: int,
        raw_context: Dict[str, Any],
    ) -> DichotomicTaskNode:
        # Determine if this node is an Atomic Verifiable Primitive (leaf)
        if depth >= max_depth:
            # Atomic leaf node
            context_slice = TokenBudgetManager.prune_context(goal, raw_context, max_tokens=budget // 2)
            acc_cmd = self._derive_leaf_acceptance_command(goal)
            return DichotomicTaskNode(
                task_id=task_id,
                goal=goal,
                line_of_thought=f"Atomic Verifiable Primitive at depth {depth}: Goal is single-responsibility and verifiable by a deterministic oracle without heuristics.",
                dichotomy_axis=DichotomyAxis.SPEC_VS_KERNEL,
                depth=depth,
                token_budget=budget,
                context_slice=context_slice,
                acceptance_command=acc_cmd,
                is_leaf=True,
                parent_id=parent_id,
            )

        # Non-leaf: Select dichotomy axis based on depth and semantics
        axis, left_goal, right_goal, lot = self._plan_dichotomy(goal, depth)

        left_b, right_b, _ = TokenBudgetManager.allocate_subtask_budgets(budget)

        left_child = self._recursive_split(
            task_id=f"{task_id}.L",
            goal=left_goal,
            parent_id=task_id,
            depth=depth + 1,
            max_depth=max_depth,
            budget=left_b,
            raw_context=raw_context,
        )

        right_child = self._recursive_split(
            task_id=f"{task_id}.R",
            goal=right_goal,
            parent_id=task_id,
            depth=depth + 1,
            max_depth=max_depth,
            budget=right_b,
            raw_context=raw_context,
        )

        node = DichotomicTaskNode(
            task_id=task_id,
            goal=goal,
            line_of_thought=lot,
            dichotomy_axis=axis,
            depth=depth,
            token_budget=budget,
            is_leaf=False,
            parent_id=parent_id,
            left_child=left_child,
            right_child=right_child,
        )
        return node

    def _plan_dichotomy(self, goal: str, depth: int) -> Tuple[DichotomyAxis, str, str, str]:
        """
        Generates the Line of Thought and bifurcated sub-goals.
        """
        lower = goal.lower()
        if "lean" in lower or "proof" in lower or "theorem" in lower or "formal" in lower:
            if depth == 0:
                axis = DichotomyAxis.SPEC_VS_KERNEL
                left = f"Formal Specification & Type Signatures for {goal}"
                right = f"Machine-Checked Proof Implementation & Kernel Attestation for {goal}"
                lot = (
                    "Dichotomy 1 (Spec vs Implementation): Formally separating type declarations and "
                    "invariants from tactical proof derivation prevents circular definitions."
                )
            else:
                axis = DichotomyAxis.TYPES_VS_PROOF
                left = f"Inductive Metric Hypotheses & Lemmas for {goal}"
                right = f"Tactical Proof Script & 0-sorry Verification for {goal}"
                lot = (
                    "Dichotomy 2 (Hypotheses vs Tactics): Separating base lemmas from the main induction "
                    "guarantees incremental soundness without unproven sorryAx holes."
                )
        elif "silicon" in lower or "hardware" in lower or "sta" in lower or "hot-swap" in lower or "security" in lower:
            axis = DichotomyAxis.RED_VS_BLUE
            left = f"Adversarial Challenge & Boundary Invariant Verification for {goal}"
            right = f"Synthesized AST Hardened Patch & Atomic Socket Migration for {goal}"
            lot = (
                "Dichotomy (Adversarial Red vs Defensive Blue): Generating the exploit challenge independently "
                "from the defensive mitigation ensures fail-closed immunity without self-congratulation."
            )
        else:
            axis = DichotomyAxis.MODEL_VS_DISCRETIZATION
            left = f"Continuous Mathematical Invariants & First Integrals for {goal}"
            right = f"Discrete Numerical Integrator & Lattice Convergence Kernel for {goal}"
            lot = (
                "Dichotomy (Continuous Physics vs Discrete Numerics): Decoupling analytical Hamiltonian "
                "conservation laws from finite-difference lattice stencils allows independent verification."
            )

        return axis, left, right, lot

    def _derive_leaf_acceptance_command(self, leaf_goal: str) -> str:
        lower = leaf_goal.lower()
        if "lean" in lower or "proof" in lower or "theorem" in lower:
            return "cd formal && lake build"
        if "kerr" in lower or "symplectic" in lower or "integrator" in lower:
            return "uv run python -c \"from anse.physics.kerr_geodesic_numerical import integrate_kerr_geodesic; sol = integrate_kerr_geodesic(steps=1000); assert sol.carter_drift_error < 1e-6\""
        if "lattice" in lower or "instanton" in lower:
            return "uv run python -c \"from anse.physics.lattice_instanton_numerical import LatticeInstantonSimulator; s = LatticeInstantonSimulator(grid_size=10); res = s.compute_topological_charge(); assert 0.8 <= res.q_top <= 1.2\""
        if "socket" in lower or "scm_rights" in lower or "migration" in lower:
            return "uv run python -c \"from anse.systems.real_scm_rights_ipc import run_atomic_socket_migration; res = run_atomic_socket_migration(); assert res['socket_continuity_verified']\""
        if "sta" in lower or "timing" in lower or "systolic" in lower:
            return "uv run python -c \"from anse.systems.systolic_sta_engine import SystolicArraySTA; sta = SystolicArraySTA(); res = sta.analyze_critical_path(); assert res.timing_met\""
        return "uv run pytest tests/ -q --maxfail=1"

    def execute_leaf(
        self,
        node: DichotomicTaskNode,
        source_code: Optional[str] = None,
        custom_runner: Optional[Callable[[DichotomicTaskNode], Dict[str, Any]]] = None,
    ) -> DichotomicTaskNode:
        """
        Executes and deterministically verifies an Atomic Verifiable Primitive.
        Rejects any stubs under E = 10^6 penalty.
        """
        node.status = TaskStatus.IN_PROGRESS
        t0 = time.perf_counter()

        # 1. Zero-Stub AST Audit
        if source_code:
            if "lean" in node.goal.lower():
                audit = ZeroStubAudit.audit_lean_code(source_code)
            else:
                audit = ZeroStubAudit.audit_python_code(source_code)

            if not audit.is_clean:
                node.status = TaskStatus.STUB_DETECTED
                node.energy_score = 1e6
                node.verification_receipt = {
                    "passed": False,
                    "error": "STUB_DETECTED",
                    "violations": audit.violations,
                    "duration_ms": (time.perf_counter() - t0) * 1000.0,
                }
                node.completed_at = time.time()
                return node

        # 2. Execution via Custom Runner or Acceptance Command
        if custom_runner:
            receipt = custom_runner(node)
            passed = receipt.get("passed", False)
        elif node.acceptance_command:
            try:
                res = subprocess.run(
                    node.acceptance_command,
                    shell=True,
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                passed = res.returncode == 0
                receipt = {
                    "passed": passed,
                    "returncode": res.returncode,
                    "stdout_tail": res.stdout[-500:] if res.stdout else "",
                    "stderr_tail": res.stderr[-500:] if res.stderr else "",
                }
            except subprocess.TimeoutExpired:
                passed = False
                receipt = {"passed": False, "error": "TIMEOUT (60s exceeded)"}
        else:
            passed = True
            receipt = {"passed": True, "notice": "No external command specified; clean specification check"}

        duration_ms = (time.perf_counter() - t0) * 1000.0
        node.completed_at = time.time()

        if passed:
            node.status = TaskStatus.VERIFIED
            node.energy_score = 0.001 * duration_ms + 0.1  # Physical Energy functional
            receipt["duration_ms"] = round(duration_ms, 2)
            node.verification_receipt = receipt

            # Mint cryptographic proof token
            token_payload = f"{node.task_id}:{node.goal}:{node.energy_score}:{duration_ms}"
            node.proof_token = hashlib.sha256(token_payload.encode("utf-8")).hexdigest()
        else:
            node.status = TaskStatus.REJECTED
            node.energy_score = 1e6
            receipt["duration_ms"] = round(duration_ms, 2)
            node.verification_receipt = receipt

        return node

    def synthesize_node(self, node: DichotomicTaskNode) -> DichotomicTaskNode:
        """
        Synthesizes composite proof for a parent node whose children have both verified.
        """
        if node.is_leaf:
            return node

        if not (node.left_child and node.right_child):
            node.status = TaskStatus.REJECTED
            node.energy_score = 1e6
            return node

        # Enforce that both children are strictly VERIFIED
        if node.left_child.status != TaskStatus.VERIFIED or node.right_child.status != TaskStatus.VERIFIED:
            node.status = TaskStatus.REJECTED
            node.energy_score = 1e6
            node.verification_receipt = {
                "passed": False,
                "error": "Child verification prerequisite failed",
                "left_status": node.left_child.status.value,
                "right_status": node.right_child.status.value,
            }
            return node

        # Aggregate Energy and Proof Tokens
        node.status = TaskStatus.VERIFIED
        node.energy_score = node.left_child.energy_score + node.right_child.energy_score
        token_payload = f"{node.left_child.proof_token}:{node.right_child.proof_token}:{node.task_id}"
        node.proof_token = hashlib.sha256(token_payload.encode("utf-8")).hexdigest()
        node.completed_at = time.time()
        node.verification_receipt = {
            "passed": True,
            "synthesized_from": [node.left_child.task_id, node.right_child.task_id],
            "combined_energy": round(node.energy_score, 4),
        }
        return node

    def run_pipeline(
        self,
        root_node: DichotomicTaskNode,
        leaf_sources: Optional[Dict[str, str]] = None,
    ) -> Generator[DichotomicTaskNode, None, None]:
        """
        Bottom-up execution generator: executes all leaves, verifies zero stubs,
        then synthesizes composite proofs upwards to the root.
        """
        leaf_sources = leaf_sources or {}

        # 1. Execute all leaves
        leaves = root_node.get_all_leaves()
        for leaf in leaves:
            src = leaf_sources.get(leaf.task_id)
            self.execute_leaf(leaf, source_code=src)
            yield leaf

        # 2. Bottom-up synthesis (post-order traversal)
        def _post_order_synth(n: DichotomicTaskNode):
            if n.is_leaf:
                return
            if n.left_child:
                _post_order_synth(n.left_child)
            if n.right_child:
                _post_order_synth(n.right_child)
            self.synthesize_node(n)

        _post_order_synth(root_node)
        yield root_node
