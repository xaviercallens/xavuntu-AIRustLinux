"""
Performance Energy Evaluator: converts :class:`~anse.symbolic.sandbox.ExecutionResult`
into a continuous mathematical computational physics Energy score.

Formal Concept (Use Case 1 — Algorithmic Performance Engineer):
---------------------------------------------------------------
Energy Signal:
    E = w_t * Execution Time (ms) + w_m * Peak RAM Usage (MB)
    Crash / Syntax Error / Incorrect Output = E = ∞ (or penalty 1e6)

Monotonicity Property:
    If code is functionally correct and executes faster or uses less RAM,
    Energy drops continuously. High energy acts as a latent 'pain signal'
    inducing System 2 pondering and dynamic LoRA weight updates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from anse.config import PerformanceConfig, get_config
from anse.symbolic.sandbox import ExecutionResult

# ─── Categories ──────────────────────────────────────────────────────────────


class PerformanceCategory(str, Enum):  # noqa: UP042
    SYNTAX_ERROR = "syntax_error"
    CRASH = "crash"
    TIMEOUT = "timeout"
    TEST_FAILURE = "test_failure"
    WRONG_OUTPUT = "wrong_output"
    INEFFICIENT = "inefficient"
    MODERATE = "moderate"
    OPTIMIZED = "optimized"
    VECTORIZED = "vectorized"


@dataclass
class PerformanceEnergyResult:
    """Outcome of evaluating computational performance energy."""

    score: float
    """The continuous energy value E ∈ [0, ∞). Lower is faster and leaner."""

    category: PerformanceCategory
    """Qualitative categorization of the execution."""

    is_valid: bool
    """Whether the code executed cleanly and satisfied all correctness criteria."""

    duration_ms: float
    """Wall-clock execution duration in milliseconds."""

    peak_ram_mb: float
    """Peak RAM consumption in Megabytes."""

    execution: ExecutionResult
    """Underlying sandbox execution result."""

    pain_signal: str
    """Pain/reward diagnostic feedback for System 2 pondering or prompt injection."""

    speedup_factor: float | None = None
    """Speedup relative to baseline: T_baseline / T_cand."""

    memory_reduction_ratio: float | None = None
    """Fractional memory saved relative to baseline: 1.0 - (RAM_cand / RAM_baseline)."""

    energy_delta: float | None = None
    """Change in energy: E_baseline - E_cand. Positive indicates improvement."""

    relative_energy: float | None = None
    """Normalized energy relative to baseline: (T / T_base) + (M / M_base)."""


# ─── Evaluator ───────────────────────────────────────────────────────────────


class PerformanceEnergyEvaluator:
    """
    Evaluates candidate code in terms of continuous computational physics:
    Execution Time (ms) + Peak RAM Usage (MB).
    """

    def __init__(self, config: PerformanceConfig | None = None) -> None:
        self.config = config or get_config().performance

    def _check_correctness_gate(
        self, result: ExecutionResult, stdout: str, stderr: str, expected_output: str | None
    ) -> PerformanceEnergyResult | None:
        if result.timed_out:
            return self._build_failure_result(
                result=result,
                category=PerformanceCategory.TIMEOUT,
                pain_signal=(
                    f"COMPUTATIONAL CRASH (TIMEOUT): Execution exceeded time limit.\n"
                    f"Stderr:\n{stderr[-1000:]}"
                ),
            )
        if re.search(r"SyntaxError", stderr, re.IGNORECASE):
            return self._build_failure_result(
                result=result,
                category=PerformanceCategory.SYNTAX_ERROR,
                pain_signal=(
                    f"COMPUTATIONAL CRASH (SYNTAX ERROR): Code could not be parsed.\n"
                    f"Traceback:\n{stderr[-1000:]}"
                ),
            )
        if re.search(r"AssertionError", stderr, re.IGNORECASE) or re.search(r"FAILED|FAIL", stdout):
            return self._build_failure_result(
                result=result,
                category=PerformanceCategory.TEST_FAILURE,
                pain_signal=(
                    f"CORRECTNESS FAILURE: Code failed functional verification tests.\n"
                    f"Optimization must strictly preserve algorithmic correctness.\n"
                    f"Stderr:\n{stderr[-1000:]}\nStdout:\n{stdout[-1000:]}"
                ),
            )
        if result.returncode != 0:
            return self._build_failure_result(
                result=result,
                category=PerformanceCategory.CRASH,
                pain_signal=(
                    f"COMPUTATIONAL CRASH: Runtime exception raised (exit code {result.returncode}).\n"
                    f"Traceback:\n{stderr[-1000:]}"
                ),
            )
        if expected_output is not None:
            actual = stdout.strip()
            expected = expected_output.strip()
            if actual != expected:
                return self._build_failure_result(
                    result=result,
                    category=PerformanceCategory.WRONG_OUTPUT,
                    pain_signal=(
                        f"CORRECTNESS FAILURE: Output does not match expected reference.\n"
                        f"Expected:\n{expected[:500]}\n\nActual:\n{actual[:500]}"
                    ),
                )
        return None

    def _categorize_performance(
        self, speedup: float | None, duration_ms: float, base_t: float
    ) -> PerformanceCategory:
        if speedup is not None:
            if speedup >= 5.0 or (duration_ms < 0.15 * base_t):
                return PerformanceCategory.VECTORIZED
            if speedup >= 2.0:
                return PerformanceCategory.OPTIMIZED
            if speedup >= 1.05:
                return PerformanceCategory.MODERATE
            return PerformanceCategory.INEFFICIENT
        return (
            PerformanceCategory.OPTIMIZED if duration_ms < 50.0 else PerformanceCategory.INEFFICIENT
        )

    def _generate_pain_signal(
        self,
        category: PerformanceCategory,
        raw_energy: float,
        duration_ms: float,
        peak_ram_mb: float,
        speedup: float | None,
        baseline_result: ExecutionResult | None,
    ) -> str:
        if category in (PerformanceCategory.VECTORIZED, PerformanceCategory.OPTIMIZED):
            speedup_str = f"{speedup:.1f}x speedup" if speedup else "fast execution"
            return (
                f"PERFORMANCE REWARD: Massive Energy Drop! (Energy = {raw_energy:.2f})\n"
                f"- Execution Time: {duration_ms:.2f} ms ({speedup_str})\n"
                f"- Peak RAM: {peak_ram_mb:.2f} MB\n"
                f"- Status: {category.value.upper()} implementation successfully discovered."
            )
        base_info = ""
        if baseline_result is not None:
            base_info = (
                f" (Baseline: {baseline_result.duration_ms:.2f} ms, "
                f"{baseline_result.peak_ram_mb:.2f} MB)"
            )
        return (
            f"PERFORMANCE PAIN SIGNAL: High Computational Energy (E = {raw_energy:.2f})\n"
            f"- Execution Time: {duration_ms:.2f} ms{base_info}\n"
            f"- Peak RAM: {peak_ram_mb:.2f} MB\n"
            f"System 2 Pain Diagnosis:\n"
            f"The algorithm is functionally correct but computationally inefficient. "
            f"Nested Python loops and unvectorized allocations create high latency and memory overhead. "
            f"Ponder further: replace sequential for-loops with NumPy array broadcasting, "
            f"contiguous memory layout, or SIMD vectorization to minimize Energy towards zero."
        )

    def evaluate(
        self,
        result: ExecutionResult,
        baseline_result: ExecutionResult | None = None,
        expected_output: str | None = None,
        code: str | None = None,
    ) -> PerformanceEnergyResult:
        """
        Evaluate *result* and compute the continuous energy score.

        Parameters
        ----------
        result:
            Output from :class:`~anse.symbolic.sandbox.SandboxExecutor`.
        baseline_result:
            Optional baseline execution result (e.g. naive unvectorized code)
            used to compute relative speedup and energy reduction.
        expected_output:
            Optional expected stdout for output validation.
        code:
            Optional source code string.
        """
        stderr = result.stderr or ""
        stdout = result.stdout or ""

        # 1. Correctness Gate: Any fatal failure spikes energy to infinity (penalty)
        failure_res = self._check_correctness_gate(result, stdout, stderr, expected_output)
        if failure_res is not None:
            return failure_res

        # 1.5. Landauer Bound Check (Physical Hardness)
        def validate_physical_bounds(duration_ms: float, ram_mb: float) -> None:
            MIN_POSSIBLE_TIME_MS = 1e-4  # 0.1 microseconds
            MIN_POSSIBLE_RAM_MB = 1e-2   # ~10 KB
            if duration_ms < MIN_POSSIBLE_TIME_MS:
                raise ValueError(f"PHYSICS VIOLATION: Execution time {duration_ms} ms violates CPU/OS scheduling physics.")
            if 0.0 < ram_mb < MIN_POSSIBLE_RAM_MB:
                raise ValueError(f"PHYSICS VIOLATION: Memory allocation {ram_mb} MB is lower than Python interpreter overhead.")

        try:
            validate_physical_bounds(result.duration_ms, result.peak_ram_mb)
        except ValueError as e:
            return self._build_failure_result(
                result=result,
                category=PerformanceCategory.CRASH,
                pain_signal=str(e),
            )

        # 2. Continuous Physics Calculation
        duration_ms = max(result.duration_ms, 0.001)
        peak_ram_mb = max(result.peak_ram_mb, 0.0)

        raw_energy = (self.config.weight_time_ms * duration_ms) + (
            self.config.weight_peak_ram_mb * peak_ram_mb
        )

        speedup: float | None = None
        mem_red: float | None = None
        energy_delta: float | None = None
        rel_energy: float | None = None
        base_t = float("inf")

        if baseline_result is not None:
            base_t = max(baseline_result.duration_ms, 0.001)
            base_m = max(baseline_result.peak_ram_mb, 0.001)
            base_energy = (self.config.weight_time_ms * base_t) + (
                self.config.weight_peak_ram_mb * base_m
            )

            speedup = base_t / duration_ms
            mem_red = max(0.0, 1.0 - (peak_ram_mb / base_m))
            energy_delta = base_energy - raw_energy
            rel_energy = (duration_ms / base_t) + (peak_ram_mb / base_m)

        # 3. Categorization based on performance gain
        category = self._categorize_performance(speedup, duration_ms, base_t)

        # 4. Generate Latent Feedback (Pain vs Reward Signal)
        pain_signal = self._generate_pain_signal(
            category, raw_energy, duration_ms, peak_ram_mb, speedup, baseline_result
        )

        return PerformanceEnergyResult(
            score=raw_energy,
            category=category,
            is_valid=True,
            duration_ms=duration_ms,
            peak_ram_mb=peak_ram_mb,
            execution=result,
            pain_signal=pain_signal,
            speedup_factor=speedup,
            memory_reduction_ratio=mem_red,
            energy_delta=energy_delta,
            relative_energy=rel_energy,
        )

    def _build_failure_result(
        self,
        result: ExecutionResult,
        category: PerformanceCategory,
        pain_signal: str,
    ) -> PerformanceEnergyResult:
        """Construct infinite energy result for failed execution."""
        return PerformanceEnergyResult(
            score=self.config.penalty_infinite_energy,
            category=category,
            is_valid=False,
            duration_ms=result.duration_ms,
            peak_ram_mb=result.peak_ram_mb,
            execution=result,
            pain_signal=pain_signal,
            speedup_factor=0.0,
            memory_reduction_ratio=0.0,
            energy_delta=-self.config.penalty_infinite_energy,
            relative_energy=float("inf"),
        )
