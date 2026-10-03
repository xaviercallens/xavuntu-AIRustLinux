"""
ANSE 2.0: Autopoietic Neuro-Symbolic Energy-Based System (V2 Hardness).

Public API:
- FastSurrogateRealityEngine: System 1.5 ultra-fast (<2ms) thought filtering.
- MeZOOptimizer, EdgeContinuousPlasticityEngine: Zeroth-order edge learning.
- PopperianAdversaryEngine, ASTWhistleblower: System 3 adversarial falsification.
- REMSleepDaemon, ElasticWeightConsolidation: Sleep phase EWC memory consolidation.
- ANSEEngineV2: Master unified autopoietic engine.
"""

from anse.v2.engine_v2 import ANSEEngineV2, ANSEV2CycleResult
from anse.v2.mezo_optimizer import EdgeContinuousPlasticityEngine, MeZOOptimizer, MeZOStepResult
from anse.v2.popperian_adversary import (
    AdversarialTestCase,
    ASTWhistleblower,
    FalsificationReport,
    PopperianAdversaryEngine,
)
from anse.v2.rem_consolidation import (
    AnchorMemoryTrace,
    ElasticWeightConsolidation,
    REMSleepDaemon,
    REMSleepSummary,
)
from anse.v2.surrogate_cache import (
    FastSurrogateRealityEngine,
    RolloutFilterSummary,
    SurrogateEnergyPredictor,
    SurrogateEvaluationResult,
)

__all__ = [
    "ANSEEngineV2",
    "ANSEV2CycleResult",
    "FastSurrogateRealityEngine",
    "SurrogateEnergyPredictor",
    "SurrogateEvaluationResult",
    "RolloutFilterSummary",
    "MeZOOptimizer",
    "MeZOStepResult",
    "EdgeContinuousPlasticityEngine",
    "PopperianAdversaryEngine",
    "ASTWhistleblower",
    "AdversarialTestCase",
    "FalsificationReport",
    "REMSleepDaemon",
    "ElasticWeightConsolidation",
    "AnchorMemoryTrace",
    "REMSleepSummary",
]
