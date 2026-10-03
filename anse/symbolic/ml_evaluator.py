"""
ML Architecture Performance Evaluator.

Phase 2: Micro-ML Architect.
Converts `MLExecutionResult` into a continuous energy score.
"""

from __future__ import annotations

import re

from anse.config import PerformanceConfig, get_config
from anse.symbolic.ml_sandbox import MLExecutionResult
from anse.symbolic.performance_evaluator import PerformanceCategory, PerformanceEnergyResult


class MLEnergyEvaluator:
    """
    Evaluates ML architecture candidate code.
    """

    def __init__(self, config: PerformanceConfig | None = None) -> None:
        self.config = config or get_config().performance
        self.max_pain = 1000.0
        self.max_params = 50000

    def evaluate(self, result: MLExecutionResult) -> PerformanceEnergyResult:
        stderr = result.stderr or ""

        # 1. Fatal Errors
        if result.timed_out:
            return self._build_failure_result(
                result,
                PerformanceCategory.TIMEOUT,
                "COMPUTATIONAL CRASH (TIMEOUT): Training took too long. Check for infinite loops or extremely heavy layers.",
            )

        if re.search(r"SyntaxError", stderr, re.IGNORECASE):
            return self._build_failure_result(
                result,
                PerformanceCategory.SYNTAX_ERROR,
                f"COMPUTATIONAL CRASH (SYNTAX ERROR): Code could not be parsed.\nTraceback:\n{stderr[-1000:]}",
            )

        if result.is_shape_mismatch:
            return self._build_failure_result(
                result,
                PerformanceCategory.CRASH,
                f"MAXIMUM PAIN: Tensor Shape Mismatch.\nSystem 2 Diagnosis: Your linear/conv layer dimensions do not align with the forward pass tensor shapes. Trace the tensor shapes carefully.\nTraceback:\n{stderr[-1000:]}",
            )

        if result.is_oom:
            return self._build_failure_result(
                result,
                PerformanceCategory.CRASH,
                f"MAXIMUM PAIN: CUDA Out of Memory.\nSystem 2 Diagnosis: Your model allocated too many tensors or excessively large hidden states.\nTraceback:\n{stderr[-1000:]}",
            )

        if result.returncode != 0:
            return self._build_failure_result(
                result,
                PerformanceCategory.CRASH,
                f"COMPUTATIONAL CRASH: Runtime exception raised.\nTraceback:\n{stderr[-1000:]}",
            )

        # 2. Physics / Architectural Constraints
        if result.parameters > self.max_params:
            energy = float(result.parameters - self.max_params)
            return PerformanceEnergyResult(
                score=energy,
                category=PerformanceCategory.INEFFICIENT,
                is_valid=False,
                duration_ms=result.duration_ms,
                peak_ram_mb=0.0,
                execution=result,
                pain_signal=(
                    f"PERFORMANCE PAIN SIGNAL: Memory Limit Exceeded.\n"
                    f"Energy = {energy} (Parameters = {result.parameters}).\n"
                    f"System 2 Diagnosis: Your model is too large. You must keep parameters under {self.max_params} to save VRAM. Shrink hidden dimensions or remove layers."
                ),
                speedup_factor=1.0,
                memory_reduction_ratio=0.0,
                energy_delta=-energy,
                relative_energy=float("inf"),
            )

        # 3. Model Accuracy and Loss
        energy = result.val_loss
        if result.accuracy < 0.95:
            # Model trains, but accuracy is low.
            category = PerformanceCategory.MODERATE
            pain_signal = (
                f"PERFORMANCE PAIN SIGNAL: Accuracy too low.\n"
                f"Energy = {energy:.4f} (Validation Loss).\n"
                f"Accuracy = {result.accuracy * 100:.2f}% (Target: > 95%).\n"
                f"System 2 Diagnosis: The model trains, but suffers from dead neurons or underfitting. Consider adding GELU activations, LayerNorm, or adjusting layer depth."
            )
        else:
            category = PerformanceCategory.OPTIMIZED
            pain_signal = (
                f"PERFORMANCE REWARD: Target accuracy achieved!\n"
                f"Energy = {energy:.4f} (Validation Loss).\n"
                f"Accuracy = {result.accuracy * 100:.2f}%.\n"
                f"Parameters = {result.parameters}.\n"
                f"Status: OPTIMIZED model successfully discovered."
            )

        return PerformanceEnergyResult(
            score=energy,
            category=category,
            is_valid=True,
            duration_ms=result.duration_ms,
            peak_ram_mb=0.0,
            execution=result,
            pain_signal=pain_signal,
            speedup_factor=1.0,
            memory_reduction_ratio=1.0,
            energy_delta=0.0,
            relative_energy=1.0,
        )

    def _build_failure_result(
        self, result: MLExecutionResult, category: PerformanceCategory, pain_signal: str
    ) -> PerformanceEnergyResult:
        return PerformanceEnergyResult(
            score=self.max_pain,
            category=category,
            is_valid=False,
            duration_ms=result.duration_ms,
            peak_ram_mb=0.0,
            execution=result,
            pain_signal=pain_signal,
            speedup_factor=0.0,
            memory_reduction_ratio=0.0,
            energy_delta=-self.max_pain,
            relative_energy=float("inf"),
        )
