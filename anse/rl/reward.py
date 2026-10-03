"""
anse.rl.reward — Differential Multi-Objective Reward Calculator for Kernel Parity.

Implements the ANSE-RL reward functional:
R_diff = (\u03b1 \u22c5 \u03a6_func) + (\u03b2 \u22c5 min(Ops_RunuX / Ops_Linux, 2.0)) - (\u03b3 \u22c5 E_ANSE) + B_target
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RewardComponents:
    functional_reward: float
    performance_reward: float
    energy_penalty: float
    milestone_bonus: float
    total_reward: float
    phase: int
    passed_iso_80: bool
    passed_iso_90: bool
    passed_iso_100: bool = False
    passed_degradation_50: bool = False
    passed_perf_gain_10: bool = False
    passed_perf_gain_20: bool = False
    passed_perf_gain_30: bool = False
    passed_ai_speedup_50: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "functional_reward": round(self.functional_reward, 3),
            "performance_reward": round(self.performance_reward, 3),
            "energy_penalty": round(self.energy_penalty, 3),
            "milestone_bonus": round(self.milestone_bonus, 3),
            "total_reward": round(self.total_reward, 3),
            "phase": self.phase,
            "passed_iso_80": self.passed_iso_80,
            "passed_iso_90": self.passed_iso_90,
            "passed_iso_100": self.passed_iso_100,
            "passed_degradation_50": self.passed_degradation_50,
            "passed_perf_gain_10": self.passed_perf_gain_10,
            "passed_perf_gain_20": self.passed_perf_gain_20,
            "passed_perf_gain_30": self.passed_perf_gain_30,
            "passed_ai_speedup_50": self.passed_ai_speedup_50,
        }


class DifferentialRewardCalculator:
    """
    Computes multi-objective differential reward signals across curriculum phases:
    - Phase 1: 80% Iso-Functionality Bootstrap (alpha=100, beta=10)
    - Phase 2: 90% Iso-Functionality Convergence & +10% Perf Gain (alpha=500, beta=50)
    - Phase 3: 100% Iso-Functionality & +20% Global Perf Gain (alpha=1000, beta=100)
    - Phase 4: Google TPU / AI Supremacy (alpha=1500, beta=150, +30% Global, +50% AI Speedup)
    """

    def __init__(self, phase: int = 2) -> None:
        self.phase = phase
        self._configure_weights()

    def _configure_weights(self) -> None:
        if self.phase == 1:
            self.alpha = 100.0
            self.beta = 10.0
            self.gamma = 0.001
            self.cap_ops_ratio = 2.0
            self.bonus_amount = 50.0
        elif self.phase == 2:
            self.alpha = 500.0
            self.beta = 50.0
            self.gamma = 0.001
            self.cap_ops_ratio = 3.0
            self.bonus_amount = 100.0
        elif self.phase == 3:
            self.alpha = 1000.0
            self.beta = 100.0
            self.gamma = 0.0005
            self.cap_ops_ratio = None  # Uncapped
            self.bonus_amount = 500.0
        elif self.phase == 4:
            self.alpha = 1500.0
            self.beta = 150.0
            self.gamma = 0.0002
            self.cap_ops_ratio = None  # Uncapped
            self.bonus_amount = 750.0
        else:  # Phase 5+: Audit-hardened full campaign
            # F-22 fix: Phase 5 was silently using Phase 4 weights.
            # cap_ops_ratio=50.0 prevents 37–104x ops ratios from producing
            # meaningless reward magnitudes (beta * 104 = 15,600 >> any gate bonus).
            self.alpha = 2000.0
            self.beta = 200.0
            self.gamma = 0.0001
            self.cap_ops_ratio = 50.0
            self.bonus_amount = 1000.0

    def compute_reward(
        self,
        functional_parity: float,  # Phi_func in [0.0, 1.0]
        ops_ratio: float,          # Ops_RunuX / Ops_Linux
        energy_anse: float,        # E_ANSE = w_t * dt + w_m * RAM + Pi_penalty * phi
        perf_gain_pct: float = 10.0,  # Performance gain % over baseline
        ai_speedup_pct: float = 50.0, # AI Computing speedup %
        failed_or_panicked: bool = False,
        **kwargs: float,           # Optional: degradation_pct= for direct deg-50 gate check
    ) -> RewardComponents:
        """
        Calculates the differential reward signal.
        """
        if failed_or_panicked:
            # Catastrophic failure penalty (-1000)
            return RewardComponents(
                functional_reward=-100.0,
                performance_reward=0.0,
                energy_penalty=-1000.0,
                milestone_bonus=0.0,
                total_reward=-1100.0,
                phase=self.phase,
                passed_iso_80=False,
                passed_iso_90=False,
                passed_iso_100=False,
                passed_degradation_50=False,
                passed_perf_gain_10=False,
                passed_perf_gain_20=False,
                passed_perf_gain_30=False,
                passed_ai_speedup_50=False,
            )

        # 1. Functional component
        func_reward = self.alpha * functional_parity

        # 2. Performance component
        effective_ops = min(ops_ratio, self.cap_ops_ratio) if self.cap_ops_ratio else ops_ratio
        perf_reward = self.beta * effective_ops

        # 3. Energy penalty component
        energy_pen = self.gamma * energy_anse

        # 4. Milestone Gates
        passed_iso_80 = functional_parity >= 0.80
        passed_iso_90 = functional_parity >= 0.90
        passed_iso_100 = functional_parity >= 0.9999
        # F-10 fix: align with differential_arena.py — accept either criterion.
        # ops_ratio >= 0.67 means RunuX is at most 1.49x slower (50% degradation proxy).
        # degradation_pct (if provided as kwargs) allows the direct check.
        _deg_pct = kwargs.get("degradation_pct", None) if kwargs else None
        passed_deg_50 = (ops_ratio >= 0.67) or (_deg_pct is not None and _deg_pct <= 50.0)
        passed_perf_gain_10 = perf_gain_pct >= 10.0
        passed_perf_gain_20 = perf_gain_pct >= 20.0
        passed_perf_gain_30 = perf_gain_pct >= 30.0
        passed_ai_speedup_50 = ai_speedup_pct >= 50.0

        milestone_bonus = 0.0
        if self.phase == 1:
            if passed_iso_80 and passed_deg_50:
                milestone_bonus = self.bonus_amount
        elif self.phase == 2:
            if passed_iso_90 and passed_deg_50 and passed_perf_gain_10:
                milestone_bonus = self.bonus_amount
        elif self.phase == 3:
            if passed_iso_100 and passed_deg_50 and passed_perf_gain_20:
                milestone_bonus = self.bonus_amount
        else:  # Phase 4 (Run 4)
            if passed_iso_100 and passed_deg_50 and passed_perf_gain_30 and passed_ai_speedup_50:
                milestone_bonus = self.bonus_amount

        total_r = func_reward + perf_reward - energy_pen + milestone_bonus

        return RewardComponents(
            functional_reward=func_reward,
            performance_reward=perf_reward,
            energy_penalty=energy_pen,
            milestone_bonus=milestone_bonus,
            total_reward=total_r,
            phase=self.phase,
            passed_iso_80=passed_iso_80,
            passed_iso_90=passed_iso_90,
            passed_iso_100=passed_iso_100,
            passed_degradation_50=passed_deg_50,
            passed_perf_gain_10=passed_perf_gain_10,
            passed_perf_gain_20=passed_perf_gain_20,
            passed_perf_gain_30=passed_perf_gain_30,
            passed_ai_speedup_50=passed_ai_speedup_50,
        )
