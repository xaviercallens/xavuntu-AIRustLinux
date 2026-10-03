"""
anse.v5.engine_v5 - ANSE Phase V5 Master Engine.

Unifies:
  1. Non-Autoregressive System 1 Decision Triage via local CPU Laya.
  2. Rosetta Stone Triplet Cross-Domain Verification (Lean 4 + Python + Rust).
  3. Test-Time Compute GRPO Policy Explorer.
  4. Autonomous Scientific Curricula Formulation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from anse.v5.autonomous_curriculum import AutonomousCurriculumEngine, ScientificHypothesis
from anse.v5.grpo_explorer import GRPOExplorer, GRPOResult
from anse.v5.laya_system_one import LayaSystemOneDecisionEngine
from anse.v5.rosetta_stone import RosettaStoneEngine, RosettaTriplet, RosettaVerificationResult

logger = logging.getLogger(__name__)


class ANSEEngineV5:
    """Master neuro-symbolic engine for ANSE Phase V5 (Autonomous Science & Cross-Domain Verification)."""

    def __init__(self, laya_model_dir: str | Path | None = None, device: str = "cpu") -> None:
        self.device = device
        self.laya = LayaSystemOneDecisionEngine(model_dir=laya_model_dir, device=device)
        self.rosetta = RosettaStoneEngine()
        self.grpo = GRPOExplorer(group_size=8)
        self.curriculum = AutonomousCurriculumEngine()
        logger.info("Initialized ANSEEngineV5 (device=%s, laya_loaded=%s).", self.device, self.laya.is_loaded)

    def triage_hypothesis(self, hypothesis_text: str, choices: list[str] | None = None) -> dict[str, Any]:
        """Performs single-forward-pass System 1 triage on CPU via Laya."""
        return self.laya.triage_hypothesis(hypothesis_text, choices=choices)

    def verify_rosetta_triplet(self, triplet: RosettaTriplet) -> RosettaVerificationResult:
        """Executes simultaneous 3-domain cross-verification across Lean 4, Python, and Rust."""
        return self.rosetta.verify_triplet(triplet)

    def explore_grpo(self, prompt: str, candidates: list[dict[str, str]] | None = None) -> GRPOResult:
        """Runs test-time compute GRPO exploration across candidate reasoning paths."""
        return self.grpo.evaluate_group(prompt, candidates)

    def get_curricula(self) -> list[dict[str, Any]]:
        """Returns catalog of PhD-level scientific curricula ready for execution."""
        return [h.to_dict() for h in self.curriculum.list_curricula()]

    def run_e2e_science_pipeline(self, hypothesis_id: str) -> dict[str, Any]:
        """Runs complete end-to-end V5 pipeline on a scientific hypothesis:
        1. Curriculum retrieval
        2. System 1 Laya triage
        3. Rosetta Stone cross-domain alignment
        4. Test-time compute GRPO confirmation
        """
        hypo = self.curriculum.get_hypothesis(hypothesis_id)
        if not hypo:
            raise ValueError(f"Unknown hypothesis: {hypothesis_id}")

        # 1. System 1 Triage
        triage = self.laya.triage_hypothesis(hypo.abstract)

        # 2. Rosetta Stone Verification
        rosetta_res = self.rosetta.verify_triplet(hypo.triplet)

        # 3. GRPO Test-Time Compute Exploration
        grpo_res = self.grpo.evaluate_group(f"Formulate and optimize: {hypo.title}")

        return {
            "status": "success",
            "phase": "ANSE V5 (Autonomous Science & Rosetta Stone)",
            "hypothesis_id": hypothesis_id,
            "title": hypo.title,
            "domain": hypo.domain,
            "system_one_triage": triage,
            "rosetta_verification": rosetta_res.to_dict(),
            "grpo_exploration": grpo_res.to_dict(),
            "all_aligned": rosetta_res.triplet_aligned,
            "proof_token": rosetta_res.proof_token,
        }
