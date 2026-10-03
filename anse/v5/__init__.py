"""
anse.v5 - Autonomous Neuro-Symbolic Execution Phase V5.

Integrates:
  - LayaSystemOneDecisionEngine: Non-autoregressive System 1 decision triage on CPU.
  - RosettaStoneEngine: Cross-domain triplet verification (Lean 4 + Python + Rust).
  - GRPOExplorer: Test-time compute group relative policy exploration.
  - AutonomousCurriculumEngine: Generative scientific curriculum formulation.
  - ANSEEngineV5: Unified master coordinator.
"""

from anse.v5.autonomous_curriculum import AutonomousCurriculumEngine, ScientificHypothesis
from anse.v5.engine_v5 import ANSEEngineV5
from anse.v5.grpo_explorer import GRPOExplorer, GRPOResult, GRPOTrajectory
from anse.v5.laya_system_one import LayaSystemOneDecisionEngine
from anse.v5.rosetta_stone import RosettaStoneEngine, RosettaTriplet, RosettaVerificationResult

__all__ = [
    "ANSEEngineV5",
    "AutonomousCurriculumEngine",
    "GRPOExplorer",
    "GRPOResult",
    "GRPOTrajectory",
    "LayaSystemOneDecisionEngine",
    "RosettaStoneEngine",
    "RosettaTriplet",
    "RosettaVerificationResult",
    "ScientificHypothesis",
]
