"""
ANSE Orchestration & Dichotomic Task Decomposition Architecture.
Integrates:
  - Dichotomy of Hardness (Recursive binary task tree)
  - Stanford DSPy programmatic compilation pipeline
  - SWE-agent / AutoCodeRover AST localized symbol navigation
  - LangGraph stateful cyclical DAG execution with checkpointing
  - Aider compact AST repo map (<800 tokens) & unified diff application
"""

from __future__ import annotations

from anse.orchestration.ast_navigator import ASTLocalizedNavigator, LocalizedSymbolWindow
from anse.orchestration.dichotomic_decomposer import (
    DichotomicTaskNode,
    DichotomyAxis,
    DichotomyEngine,
    TaskStatus,
    TokenBudgetManager,
    ZeroStubAudit,
    ZeroStubAuditResult,
)
from anse.orchestration.dspy_bridge import (
    CodeGenerationSignature,
    DichotomyPipelineModule,
    DichotomySplitSignature,
    DSPySignature,
    VerificationSignature,
    physical_hardness_metric,
)
from anse.orchestration.repo_map import RepoMapGenerator, SymbolTag, apply_unified_diff
from anse.orchestration.stateful_graph import DichotomyGraphState, StatefulDichotomyGraph
from anse.orchestration.tree_of_thoughts import ThoughtState, TreeOfThoughtsEngine

__all__ = [
    # Core Dichotomy
    "DichotomicTaskNode",
    "DichotomyAxis",
    "DichotomyEngine",
    "TaskStatus",
    "TokenBudgetManager",
    "ZeroStubAudit",
    "ZeroStubAuditResult",
    # Aider Repo Map
    "RepoMapGenerator",
    "SymbolTag",
    "apply_unified_diff",
    # DSPy Pipeline
    "DSPySignature",
    "DichotomySplitSignature",
    "CodeGenerationSignature",
    "VerificationSignature",
    "DichotomyPipelineModule",
    "physical_hardness_metric",
    # SWE-agent AST Navigator
    "ASTLocalizedNavigator",
    "LocalizedSymbolWindow",
    # LangGraph State Engine
    "DichotomyGraphState",
    "StatefulDichotomyGraph",
    # Tree of Thoughts (Yao et al., 2023)
    "ThoughtState",
    "TreeOfThoughtsEngine",
]

