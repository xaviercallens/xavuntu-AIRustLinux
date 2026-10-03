"""
Performance Agent Loop: Autonomous computational physics optimization cycle.

Use Case 1 — Algorithmic Performance Engineer:
----------------------------------------------
The AI agent is fed a slow, brute-force algorithm.
It iteratively minimizes continuous computational energy:
    E = Execution Time (ms) + Peak RAM Usage (MB)
If the code simply rewrites loops, E remains high (System 2 pain signal).
When it discovers vectorization, E drops dramatically (System 2 reward).
Traces of computational physics are harvested into episodic memory,
enabling the JEPA world model to predict computational cost from code latents.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from anse.config import ANSEConfig, get_config
from anse.core.encoder import HiddenStateExtractor, HiddenStateRecord
from anse.memory.harvester import Harvester, LoopTrace
from anse.symbolic.parser import extract_code
from anse.symbolic.performance_evaluator import (
    PerformanceCategory,
    PerformanceEnergyEvaluator,
    PerformanceEnergyResult,
)
from anse.symbolic.sandbox import ExecutionResult, SandboxExecutor

logger = logging.getLogger(__name__)


# ─── Summary ─────────────────────────────────────────────────────────────────


@dataclass
class PerformanceLoopSummary:
    """Outcome of running the performance optimization loop on an algorithm."""

    task: str
    converged: bool
    iterations: int
    initial_energy: float
    final_energy: float
    energy_drop: float
    speedup_factor: float
    final_category: str
    final_code: str
    traces: list[LoopTrace]
    total_duration_ms: float


# ─── Prompts ─────────────────────────────────────────────────────────────────

PERF_SYSTEM_PROMPT = """You are an expert Performance & High-Performance Computing (HPC) engineer.
Your mission is to optimize Python algorithms for minimum latency and peak memory usage.
Replace slow nested loops, quadratic scans, and redundant allocations with NumPy vectorization,
broadcasting, contiguous memory layout, or optimal data structures.
Ensure functional correctness is strictly preserved.
Enclose your code inside a single ```python ... ``` block. Do not output extraneous text."""

PERF_INITIAL_PROMPT_TEMPLATE = """TASK: {task}

BASELINE IMPLEMENTATION (SLUG):
```python
{naive_code}
```

COMPUTATIONAL PHYSICS BASELINE:
- Execution Time: {baseline_time:.2f} ms
- Peak RAM: {baseline_ram:.2f} MB
- Baseline Energy: {baseline_energy:.2f}

OBJECTIVE:
Rewrite the algorithm to minimize Physical Energy E = Execution Time (ms) + Peak RAM (MB).
Aim for at least a {target_speedup:.1f}x speedup using vectorization while strictly preserving correctness."""

PERF_PAIN_PROMPT_TEMPLATE = """TASK: {task}

PERFORMANCE PAIN FEEDBACK:
Your candidate attempt resulted in:
{pain_signal}

Return code: {returncode}
Stderr:
{stderr}
Stdout:
{stdout}

Ponder deeply on computational physics: eliminate loop bottlenecks, avoid memory copies,
and provide the complete optimized Python code in a ```python ... ``` block."""


# ─── Loop ────────────────────────────────────────────────────────────────────


class PerformanceAgentLoop:
    """
    Orchestrates the generate -> execute -> measure physics -> pain signal -> retry cycle.
    """

    def __init__(
        self,
        extractor: HiddenStateExtractor | None = None,
        sandbox: SandboxExecutor | None = None,
        evaluator: PerformanceEnergyEvaluator | None = None,
        harvester: Harvester | None = None,
        config: ANSEConfig | None = None,
        world_model: Any | None = None,
        max_retries: int = 3,
        target_speedup: float = 2.0,
    ) -> None:
        self.config = config or get_config()
        self.extractor = extractor or HiddenStateExtractor(config=self.config.model)
        self.sandbox = sandbox or SandboxExecutor(config=self.config.sandbox)
        self.evaluator = evaluator or PerformanceEnergyEvaluator(config=self.config.performance)
        self.harvester = harvester or Harvester(config=self.config.memory)
        self.world_model = world_model
        self.max_retries = max_retries
        self.target_speedup = target_speedup

    def _run_iteration(
        self,
        task: str,
        test_harness: str,
        baseline_exec: ExecutionResult,
        baseline_energy: PerformanceEnergyResult,
        prompt: str,
        iteration: int,
        desired_speedup: float,
    ) -> tuple[bool, str, PerformanceEnergyResult, ExecutionResult, LoopTrace, str]:
        iter_start = time.time()

        raw_response, hs_record = self.extractor.extract(
            prompt=prompt,
            system_prompt=PERF_SYSTEM_PROMPT,
        )

        parse_res = extract_code(raw_response)
        candidate_code = parse_res.code

        candidate_full = candidate_code.strip() + "\n\n" + test_harness.strip()
        exec_res = self.sandbox.execute(candidate_full)

        energy_res = self.evaluator.evaluate(
            result=exec_res,
            baseline_result=baseline_exec,
            code=candidate_code,
        )

        iter_duration_ms = (time.time() - iter_start) * 1000.0
        speedup = energy_res.speedup_factor or 0.0

        converged = False
        if energy_res.is_valid and (
            speedup >= desired_speedup
            or energy_res.category
            in (PerformanceCategory.VECTORIZED, PerformanceCategory.OPTIMIZED)
        ):
            converged = True

        logger.info(
            "Iteration %d: Energy=%.2f (%s) - Speedup=%.1fx - Converged=%s (took %.1fms)",
            iteration,
            energy_res.score,
            energy_res.category.value,
            speedup,
            converged,
            iter_duration_ms,
        )

        trace_metadata = self._build_perf_trace_metadata(
            hs_record=hs_record,
            exec_res=exec_res,
            energy_res=energy_res,
            baseline_energy=baseline_energy.score,
        )

        trace = LoopTrace(
            task=task,
            prompt=prompt,
            code=candidate_code,
            raw_response=raw_response,
            energy=energy_res.score,
            energy_category=energy_res.category.value,
            converged=converged,
            iteration=iteration,
            duration_ms=iter_duration_ms,
            returncode=exec_res.returncode,
            execution_stdout=exec_res.stdout,
            execution_stderr=exec_res.stderr,
            hidden_state=hs_record.to_embedding(),
            metadata=trace_metadata,
        )
        self.harvester.record(trace)

        next_prompt = PERF_PAIN_PROMPT_TEMPLATE.format(
            task=task,
            pain_signal=energy_res.pain_signal,
            returncode=exec_res.returncode,
            stderr=exec_res.stderr[-800:] if exec_res.stderr else "(clean)",
            stdout=exec_res.stdout[-800:] if exec_res.stdout else "(clean)",
        )
        return converged, candidate_code, energy_res, exec_res, trace, next_prompt

    def run_optimization(
        self,
        task: str,
        naive_code: str,
        test_harness: str,
        max_retries: int | None = None,
        target_speedup: float | None = None,
    ) -> PerformanceLoopSummary:
        """
        Execute the autonomous performance optimization loop.

        Parameters
        ----------
        task:
            Description of the algorithm and optimization goal.
        naive_code:
            The slow, brute-force baseline Python function.
        test_harness:
            Testing script that calls the function and verifies correctness.
        max_retries:
            Maximum number of optimization attempts.
        target_speedup:
            Desired minimum speedup factor (e.g. 2.0x).
        """
        retries_limit = max_retries if max_retries is not None else self.max_retries
        desired_speedup = target_speedup if target_speedup is not None else self.target_speedup
        traces: list[LoopTrace] = []
        start_wall_time = time.time()

        # 1. Profile baseline implementation
        logger.info("Profiling baseline naive code for task: %s...", task[:40])
        baseline_full = naive_code.strip() + "\n\n" + test_harness.strip()
        baseline_exec = self.sandbox.execute(baseline_full)
        baseline_energy = self.evaluator.evaluate(baseline_exec)

        logger.info(
            "Baseline measured: time=%.2fms, RAM=%.2fMB, Energy=%.2f",
            baseline_exec.duration_ms,
            baseline_exec.peak_ram_mb,
            baseline_energy.score,
        )

        prompt = PERF_INITIAL_PROMPT_TEMPLATE.format(
            task=task,
            naive_code=naive_code.strip(),
            baseline_time=baseline_exec.duration_ms,
            baseline_ram=baseline_exec.peak_ram_mb,
            baseline_energy=baseline_energy.score,
            target_speedup=desired_speedup,
        )

        best_code = naive_code
        last_energy_res: PerformanceEnergyResult | None = None
        converged = False

        for iteration in range(1, retries_limit + 1):
            logger.info(
                "Optimization Iteration %d/%d for '%s'", iteration, retries_limit, task[:30]
            )

            (
                converged,
                candidate_code,
                energy_res,
                exec_res,
                trace,
                next_prompt,
            ) = self._run_iteration(
                task=task,
                test_harness=test_harness,
                baseline_exec=baseline_exec,
                baseline_energy=baseline_energy,
                prompt=prompt,
                iteration=iteration,
                desired_speedup=desired_speedup,
            )

            last_energy_res = energy_res
            traces.append(trace)

            if converged:
                best_code = candidate_code
                logger.info(
                    "Performance optimization converged on iteration %d! Speedup: %.1fx",
                    iteration,
                    energy_res.speedup_factor or 0.0,
                )
                break

            prompt = next_prompt

        total_wall_ms = (time.time() - start_wall_time) * 1000.0
        final_energy = last_energy_res.score if last_energy_res else baseline_energy.score
        final_category = last_energy_res.category.value if last_energy_res else "baseline"
        final_speedup = (
            last_energy_res.speedup_factor
            if (last_energy_res and last_energy_res.speedup_factor)
            else 1.0
        )
        energy_drop = baseline_energy.score - final_energy

        return PerformanceLoopSummary(
            task=task,
            converged=converged,
            iterations=len(traces),
            initial_energy=baseline_energy.score,
            final_energy=final_energy,
            energy_drop=energy_drop,
            speedup_factor=final_speedup,
            final_category=final_category,
            final_code=best_code,
            traces=traces,
            total_duration_ms=total_wall_ms,
        )

    def _build_perf_trace_metadata(
        self,
        hs_record: HiddenStateRecord,
        exec_res: ExecutionResult,
        energy_res: PerformanceEnergyResult,
        baseline_energy: float,
    ) -> dict[str, Any]:
        """Build telemetry metadata for continuous learning and JEPA training."""
        metadata: dict[str, Any] = {
            "model_id": hs_record.model_id,
            "duration_ms": energy_res.duration_ms,
            "peak_ram_mb": energy_res.peak_ram_mb,
            "speedup_factor": energy_res.speedup_factor,
            "energy_delta": energy_res.energy_delta,
            "baseline_energy": baseline_energy,
            "is_valid": energy_res.is_valid,
            "tier_used": exec_res.tier_used,
        }

        # Optional JEPA world model prediction
        if self.world_model is not None:
            try:
                import torch

                embedding = hs_record.to_embedding()
                h_tensor = torch.tensor(embedding, dtype=torch.float32)
                predicted_energy = self.world_model.predict_energy_scalar(h_tensor)
                actual_energy = energy_res.score
                surprise = abs(predicted_energy - actual_energy)

                metadata["jepa_predicted_energy"] = round(predicted_energy, 2)
                metadata["jepa_surprise"] = round(surprise, 2)
            except Exception as e:
                metadata["jepa_error"] = str(e)

        return metadata
