"""
Agentic execution loop with symbolic grounding and pain-signal injection.

Formal Lean 4 Specification:
-----------------------------
See `formal/ANSE/Basic.lean` & `formal/ANSE/Theorems.lean`:
  theorem exists_minimiser (E : EnergyFn X Y) (x : X) :
    ∃ y_star : Y, ∀ y : Y, E.eval x y_star ≤ E.eval x y

  theorem safe_improvement_nonincreasing (ε : ℝ) (hε : 0 < ε) (energy : ArchitectureState → ℝ)
    (s₁ s₂ : ArchitectureState) : safeProposal ε hε energy s₁ s₂ → energy s₂ ≤ energy s₁

Thermodynamic Active Inference & Low-Tier Hardness:
---------------------------------------------------
1. Discrete Energy Minimisation:
     y_0 ~ P(y|x)
     e_0 = Energy(Exec(y_0))
     If e_0 > 0:
       y_{t+1} ~ P(y | x, y_t, pain_signal(e_t, stderr_t))
   Until e_t ≤ threshold (convergence) or max_retries reached.

2. Low-Tier Hardness Directives (D1–D8):
   - D1: Compressed pain prompt template for small models (<100 lines, AST-focused).
   - D2: Adaptive retry capacity gating based on prompt token budget.
   - D3: Fail-fast early stopping on catastrophic E1 (>10^6) or diverging E2.
   - D4: Skeleton lesson formatting stripping verbose boilerplate.
   - D5: Difficulty tier classification (easy, medium, hard, PhD-level).
   - D6: Offline trace harvesting for continuous DPO/GRPO fine-tuning.
   - D7: Tier-specific gates (G1–G9) preventing regression.
   - D8: Autopoietic prompt strategy registry with live runtime swapping.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

from anse.config import ANSEConfig, PromptBudgetPolicy, get_config, get_model_tier, is_small_model
from anse.core.encoder import HiddenStateExtractor, HiddenStateRecord
from anse.memory.harvester import Harvester, LoopTrace
from anse.memory.lessons import (
    Lesson,
    LessonMemory,
    extract_skeleton,
    format_lessons,
    format_lessons_skeleton,
)
from anse.symbolic.evaluator import EnergyCategory, EnergyEvaluator, EnergyResult
from anse.symbolic.hidden_tests import TestReport, parse_report
from anse.symbolic.parser import NoCodeFoundError, extract_code
from anse.symbolic.sandbox import ExecutionResult, SandboxExecutor

# Phase 2: optional JEPA world model for energy prediction
try:
    from anse.jepa.world_model import JEPAWorldModel
except ImportError:
    JEPAWorldModel = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


# ─── Loop Result Summary ─────────────────────────────────────────────────────


@dataclass
class LoopSummary:
    """Outcome of running the agent loop on a single task."""

    task: str
    converged: bool
    iterations: int
    final_energy: float
    final_category: str
    final_code: str
    traces: list[LoopTrace]
    total_duration_ms: float
    tests_passed: int | None = None
    tests_total: int | None = None
    lessons_used: int = 0


# ─── System & Pain Prompts ───────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Python programmer.
Write complete, self-contained, working Python code that solves the user's task.
Include basic validation or asserts at the bottom if appropriate.
Enclose your code inside a single ```python ... ``` markdown block.
Do not output extraneous explanation outside the code block."""

SYSTEM_PROMPT_HIDDEN_TESTS = """You are an expert Python programmer.
Write complete, self-contained, working Python code that solves the user's task.
Use exactly the function names and signatures the task specifies.
Your code will be verified by hidden tests, so do not include tests, prints or example usage.
Enclose your code inside a single ```python ... ``` markdown block.
Do not output extraneous explanation outside the code block."""

RETRY_SYSTEM_PROMPT_DIAGNOSE = """You are an expert Python programmer fixing your own failed code.
First write 1-3 sentences explaining exactly why the reported failure happens.
Then give the complete corrected code in a single ```python ... ``` markdown block.
The corrected code must differ from the failed code in its logic, not just its wording.
Use exactly the function names and signatures the task specifies. Do not include tests or prints."""

STAGNATION_NOTE = """
WARNING: the code you just returned behaves identically to an attempt that already failed.
Repeating it cannot work. Re-read the failing test, find the specific input it uses, and change the logic that handles that input.
"""

PAIN_PROMPT_TEMPLATE = """TASK: {task}

PAIN SIGNAL: Your previous attempt failed with Energy {energy:.1f} ({category}).
Your previous code:
```python
{code}
```
Execution feedback:
---
{test_feedback}Return code: {returncode}
Stderr:
{stderr}
Stdout:
{stdout}
---
Analyze the failure, correct the bug, and provide the complete fixed Python code in a ```python ... ``` block."""

PAIN_PROMPT_TEMPLATE_COMPRESSED = """TASK: {task}

PAIN SIGNAL: Your previous attempt failed with Energy {energy:.1f} ({category}).
Failing code summary:
```python
{code}
```
Execution feedback:
---
{test_feedback}Return code: {returncode}
Stderr:
{stderr}
---
Analyze the failure and provide the complete fixed Python code in a ```python ... ``` block."""


def compress_failing_code(code: str, max_chars: int = 200) -> str:
    """Extract function signature and error context within budget (Directive D1)."""
    if not code:
        return "(no code block was found in your reply)"
    return extract_skeleton(code, max_chars=max_chars) or code[:max_chars]


# ─── Agent Loop ──────────────────────────────────────────────────────────────


class AgentLoop:
    """
    Orchestrates the generate -> execute -> evaluate -> record -> retry cycle.
    """

    def __init__(
        self,
        extractor: HiddenStateExtractor | None = None,
        sandbox: SandboxExecutor | None = None,
        evaluator: EnergyEvaluator | None = None,
        harvester: Harvester | None = None,
        config: ANSEConfig | None = None,
        max_retries: int = 3,
        convergence_threshold: float = 5.0,
        world_model: Any | None = None,
        lesson_memory: LessonMemory | None = None,
        adaptive_retry: bool = False,
        prompt_budget: PromptBudgetPolicy | None = None,
        force_adaptive: bool = False,
        adversarial_validation: bool = False,
    ) -> None:
        self.config = config or get_config()
        self.extractor = extractor or HiddenStateExtractor(config=self.config.model)
        self.sandbox = sandbox or SandboxExecutor(config=self.config.sandbox)
        self.evaluator = evaluator or EnergyEvaluator()
        self.harvester = harvester or Harvester(config=self.config.memory)
        self.max_retries = max_retries
        self.convergence_threshold = convergence_threshold
        self.world_model = world_model  # Phase 2: optional JEPA energy predictor
        self.lesson_memory = lesson_memory

        # Model tier detection (Directive D1, D2)
        model_name = self.config.model.api_model_name or self.config.model.model_id
        self.model_name = model_name
        self.is_small = is_small_model(model_name)
        self.model_tier = get_model_tier(model_name)
        self.adversarial_validation = adversarial_validation or self.is_small

        # Directive D2: Disable adaptive retry for sub-3B models unless explicitly forced
        if adaptive_retry and self.is_small and not force_adaptive:
            logger.info("Adaptive retry disabled for <=3B model '%s' (Directive D2)", model_name)
            self.adaptive_retry = False
        else:
            self.adaptive_retry = adaptive_retry

        # Directive D1: Prompt budget policy
        if prompt_budget is not None:
            self.prompt_budget = prompt_budget
        elif hasattr(self.config, "prompt_budget") and self.config.prompt_budget is not None:
            self.prompt_budget = (
                PromptBudgetPolicy.for_model(model_name)
                if self.is_small
                else self.config.prompt_budget
            )
        else:
            self.prompt_budget = PromptBudgetPolicy.for_model(model_name)

        # Directive D8: Swappable prompt strategy from registry
        self.prompt_strategy = None
        if hasattr(self.config, "autopoiesis") and self.config.autopoiesis.enabled:
            try:
                from anse.autopoiesis.registry import ComponentRegistry

                reg = ComponentRegistry(self.config.autopoiesis.workspace / "registry")
                if "prompt_strategy" in reg.components():
                    mod = reg.load_active("prompt_strategy")
                    if hasattr(mod, "format_pain_prompt"):
                        self.prompt_strategy = mod.format_pain_prompt
                        logger.info("Loaded active prompt_strategy from ComponentRegistry (Directive D8)")
            except Exception as e:
                logger.debug("Prompt strategy registry check: %s", e)

    def run(
        self,
        task: str,
        expected_output: str | None = None,
        max_retries: int | None = None,
        hidden_tests: list[str] | None = None,
    ) -> LoopSummary:
        """
        Execute the agentic trial-and-error loop on *task*.

        When *hidden_tests* are given, energy is graded from those tests (run
        independently in the sandbox) instead of the model's own asserts, and a
        verified solution is stored in the lesson memory, if one is attached.

        Returns:
            LoopSummary containing all iteration traces and final convergence status.
        """
        retries_limit = max_retries if max_retries is not None else self.max_retries
        traces: list[LoopTrace] = []
        start_time = time.time()

        # Directive D4: Skeleton-only lesson injection for small models
        lessons = self.lesson_memory.retrieve(task) if self.lesson_memory is not None else []
        if self.is_small:
            lesson_block = format_lessons_skeleton(lessons)
        else:
            lesson_block = format_lessons(lessons)
        system_prompt = SYSTEM_PROMPT_HIDDEN_TESTS if hidden_tests else SYSTEM_PROMPT

        prompt = f"{lesson_block}TASK:\n{task}"
        code = ""
        last_energy: EnergyResult | None = None
        report: TestReport | None = None
        first_failure = ""
        seen_codes: set[str] = set()
        stagnation = 0
        energy_history: list[float] = []
        error_trace_history: list[str] = []
        non_shrink_count = 0
        # Best-of-N tracking: keep the lowest-energy verified candidate
        best_energy_score = float("inf")
        best_code = ""
        best_energy_res: EnergyResult | None = None
        best_report: TestReport | None = None
        best_iteration = 0

        for iteration in range(1, retries_limit + 1):
            logger.info("Task '%s...' - Iteration %d/%d", task[:40], iteration, retries_limit)
            iter_start = time.time()

            # 1. Generate code and extract hidden state
            if self.adaptive_retry and iteration > 1:
                # Let the model reason before fixing, and sample hotter each time it repeats itself.
                raw_response, hs_record = self.extractor.extract(
                    prompt=prompt,
                    system_prompt=RETRY_SYSTEM_PROMPT_DIAGNOSE,
                    temperature=min(1.0, self.config.model.temperature + 0.4 * stagnation),
                )
            else:
                raw_response, hs_record = self.extractor.extract(
                    prompt=prompt,
                    system_prompt=system_prompt,
                )

            # 2. Parse code from response
            try:
                code = extract_code(raw_response).code
            except NoCodeFoundError as exc:
                code = ""
                report = None
                exec_res = ExecutionResult(
                    stdout="",
                    stderr=str(exc),
                    returncode=1,
                    timed_out=False,
                    duration_ms=0.0,
                    tier_used=1,
                )
            else:
                from antigravity_harness.core.anti_stub_guard import AntiStubGuard
                from anse.symbolic.parser import check_complexity_floor
                
                is_trivial = False
                reject_reason = ""
                
                # 2.1 Adversarial Validation (Red Team)
                if self.adversarial_validation:
                    from anse.core.red_team import DeepThinkAuditor
                    
                    auditor = DeepThinkAuditor()
                    state = {
                        "math_problem": task,
                        "lean_code": code,
                        "python_metrics": {"error": 0.0, "latency_ms": 0.0},
                        "thoughts": []
                    }
                    result = auditor.invoke(state)
                    adv_resp = result['verdict']
                    
                    if "REJECT" in adv_resp.upper():
                        is_trivial = True
                        reject_reason = f"TRIVIAL_SIMULATION: Adversary Validator rejected the code: {adv_resp}"
                
                # 2.2 AST Anti-Stub Wall
                if not is_trivial:
                    guard = AntiStubGuard()
                    audit_res = guard.audit_code(code)
                    if not audit_res.is_clean:
                        is_trivial = True
                        violations = ", ".join(v.message for v in audit_res.violations)
                        reject_reason = f"TRIVIAL_SIMULATION: AntiStubGuard detected stubs/mocks: {violations}"

                # 2.3 Complexity Floor (Legacy)
                if not is_trivial and iteration > 1 and last_energy and last_energy.difficulty_tier() in ("hard", "phd"):
                    if not check_complexity_floor(code, min_complexity=5):
                        is_trivial = True
                        reject_reason = "TRIVIAL_SIMULATION: cyclomatic complexity below floor"
                
                if is_trivial:
                    exec_res = ExecutionResult(
                        stdout="",
                        stderr=reject_reason,
                        returncode=2,
                        timed_out=False,
                        duration_ms=0.0,
                        tier_used=1,
                    )
                    report = None
                else:
                    # 3. Execute in Sandbox
                    exec_res, report = self._execute(code, hidden_tests)

            # 4. Evaluate Energy
            if hidden_tests:
                energy_res = self.evaluator.evaluate_hidden_tests(exec_res, report)
            else:
                energy_res = self.evaluator.evaluate(
                    result=exec_res,
                    code=code,
                    expected_output=expected_output,
                )
            last_energy = energy_res
            energy_history.append(energy_res.score)

            # Directive D5: Task Difficulty Estimator (Pre-Retry Triage)
            diff_tier = energy_res.difficulty_tier()
            if (
                iteration == 1
                and self.is_small
                and self.prompt_budget.difficulty_triage
            ):
                if diff_tier == "phd":
                    logger.info(
                        "PhD-level task detected; capping sub-3B retries to 1 (D5-PhD)"
                    )
                    retries_limit = 1
                elif diff_tier == "hard" and retries_limit > 2:
                    logger.info(
                        "Task difficulty classified as 'hard' (E=%.1f) for <=3B model; capping retries_limit to 2 (Directive D5)",
                        energy_res.score,
                    )
                    retries_limit = 2

            converged = self._is_converged(energy_res, report, hidden_tests)

            # Update best-of-N: prefer verified passes with lowest energy
            is_verified = bool(report and report.all_passed) if hidden_tests else converged
            was_verified = bool(best_report and best_report.all_passed) if hidden_tests else best_energy_score < float("inf")
            # Prefer any verified over unverified; among same class, prefer lower energy
            if (is_verified and not was_verified) or (
                is_verified == was_verified and energy_res.score < best_energy_score
            ):
                best_energy_score = energy_res.score
                best_code = code
                best_energy_res = energy_res
                best_report = report
                best_iteration = iteration

            iter_duration_ms = (time.time() - iter_start) * 1000.0
            if not converged and not first_failure:
                first_failure = energy_res.pain_signal

            logger.info(
                "Iteration %d: Energy=%.1f (%s) - Converged=%s (took %.1fms)",
                iteration,
                energy_res.score,
                energy_res.category.value,
                converged,
                iter_duration_ms,
            )

            # Directive D3: Energy-monotonic early stop checks
            early_stop_reason = ""
            if not converged and self.is_small and self.prompt_budget.energy_monotonic_pruning:
                if iteration == 1 and energy_res.score > 60.0:
                    early_stop_reason = "E1_catastrophic_failure"
                    logger.info(
                        "Early stopping on iteration 1: E_1=%.1f > 60.0 for <=3B model (Directive D3)",
                        energy_res.score,
                    )
                elif (
                    iteration == 2
                    and energy_res.score > energy_history[0]
                    and energy_res.score > 40.0
                ):
                    early_stop_reason = "E2_diverging_energy"
                    logger.info(
                        "Early stopping on iteration 2: E_2=%.1f > E_1=%.1f and > 40.0 for <=3B model (Directive D3)",
                        energy_res.score,
                        energy_history[0],
                    )

            # TASK-01: Banach REPL Convergence Monitor (GAP-01)
            current_stderr = exec_res.stderr or ""
            error_trace_history.append(current_stderr)
            if iteration >= 2 and not converged and not early_stop_reason:
                previous_stderr = error_trace_history[-2]
                len_delta = len(current_stderr) - len(previous_stderr)
                if len_delta >= 0:
                    non_shrink_count += 1
                else:
                    non_shrink_count = 0
                    
                if non_shrink_count >= 2 and self.is_small:
                    early_stop_reason = "banach_convergence_failure"
                    logger.info("Banach delta: stderr Δ=%d (non-shrink streak: %d). Early stopping.", len_delta, non_shrink_count)
                else:
                    logger.info("Banach delta: stderr Δ=%d (non-shrink streak: %d)", len_delta, non_shrink_count)

            normalised = " ".join(code.split())
            if normalised and normalised in seen_codes:
                stagnation += 1
            seen_codes.add(normalised)

            # 5. Build and record LoopTrace
            trace = LoopTrace(
                task=task,
                prompt=prompt,
                code=code,
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
                metadata=self._build_trace_metadata(hs_record, exec_res, energy_res),
            )
            trace.metadata["lessons_used"] = len(lessons)
            trace.metadata["stagnation"] = stagnation
            trace.metadata["difficulty_tier"] = diff_tier
            if early_stop_reason:
                trace.metadata["early_stop_reason"] = early_stop_reason
            if report is not None:
                trace.metadata["tests_passed"] = report.passed
                trace.metadata["tests_total"] = report.total
            traces.append(trace)
            self.harvester.record(trace)

            if converged:
                logger.info("Task converged on iteration %d!", iteration)
                break

            if early_stop_reason:
                break

            # 6. Inject Pain Signal for next iteration if retries remain
            if iteration < retries_limit:
                test_feedback = f"{energy_res.pain_signal}\n" if hidden_tests else ""
                if self.prompt_strategy is not None:
                    prompt = lesson_block + self.prompt_strategy(
                        task=task,
                        code=code,
                        energy=energy_res.score,
                        category=energy_res.category.value,
                        returncode=exec_res.returncode,
                        stderr=exec_res.stderr,
                        stdout=exec_res.stdout,
                        model_tier=self.model_tier,
                        test_feedback=energy_res.pain_signal if hidden_tests else "",
                    )
                elif self.is_small and self.prompt_budget.compress_code:
                    # Directive D1: compressed pain prompt
                    compressed_code = compress_failing_code(
                        code, max_chars=self.prompt_budget.max_code_chars
                    )
                    stderr_snip = (
                        exec_res.stderr[-self.prompt_budget.max_stderr_chars :]
                        if exec_res.stderr
                        else "(empty)"
                    )
                    prompt = lesson_block + PAIN_PROMPT_TEMPLATE_COMPRESSED.format(
                        task=task,
                        test_feedback=test_feedback,
                        code=compressed_code,
                        energy=energy_res.score,
                        category=energy_res.category.value,
                        returncode=exec_res.returncode,
                        stderr=stderr_snip,
                    )
                else:
                    code_snip = (
                        code[-self.prompt_budget.max_code_chars :]
                        if code
                        else "(no code block was found in your reply)"
                    )
                    stderr_snip = (
                        exec_res.stderr[-self.prompt_budget.max_stderr_chars :]
                        if exec_res.stderr
                        else "(empty)"
                    )
                    stdout_snip = (
                        exec_res.stdout[-self.prompt_budget.max_stdout_chars :]
                        if exec_res.stdout
                        else "(empty)"
                    )
                    prompt = lesson_block + PAIN_PROMPT_TEMPLATE.format(
                        task=task,
                        test_feedback=test_feedback,
                        code=code_snip,
                        energy=energy_res.score,
                        category=energy_res.category.value,
                        returncode=exec_res.returncode,
                        stderr=stderr_snip,
                        stdout=stdout_snip if not self.prompt_budget.omit_stdout else "(omitted)",
                    )
                if self.adaptive_retry and stagnation:
                    prompt += STAGNATION_NOTE

        total_duration_ms = (time.time() - start_time) * 1000.0

        # Best-of-N selection: return the best verified candidate, not the last one.
        # Fall back to the last attempt if no verified candidate exists.
        use_best = best_energy_res is not None and best_code
        final_code = best_code if use_best else code
        final_energy_res = best_energy_res if use_best else last_energy
        final_report = best_report if use_best else report
        final_energy = final_energy_res.score if final_energy_res else 100.0
        final_category = (
            final_energy_res.category.value
            if final_energy_res
            else EnergyCategory.RUNTIME_ERROR.value
        )
        converged = bool(
            final_report and final_report.all_passed
        ) if hidden_tests else bool(traces) and any(t.converged for t in traces)

        if use_best and best_iteration != len(traces):
            logger.info(
                "Best-of-N selected iteration %d (E=%.1f) over last iteration %d (E=%.1f)",
                best_iteration,
                best_energy_score,
                len(traces),
                last_energy.score if last_energy else 100.0,
            )

        if converged and hidden_tests and self.lesson_memory is not None:
            self.lesson_memory.add(
                Lesson(task=task, code=final_code, failure=first_failure, iterations=len(traces))
            )

        return LoopSummary(
            task=task,
            converged=converged,
            iterations=len(traces),
            final_energy=final_energy,
            final_category=final_category,
            final_code=final_code,
            traces=traces,
            total_duration_ms=total_duration_ms,
            tests_passed=final_report.passed if final_report is not None else None,
            tests_total=final_report.total if final_report is not None else None,
            lessons_used=len(lessons),
        )

    def _execute(
        self, code: str, hidden_tests: list[str] | None
    ) -> tuple[ExecutionResult, TestReport | None]:
        if not hidden_tests:
            return self.sandbox.execute(code), None
        from anse.symbolic.trusted_driver import build_driver, trusted_payload

        nonce = "ANSE-" + secrets.token_hex(8)
        budget = max(1.0, 0.8 * self.sandbox._cfg.timeout_seconds)
        driver_script = build_driver(nonce, code, budget, tests=hidden_tests)
        exec_res = self.sandbox.execute(driver_script, force_tier=1)
        payload = trusted_payload(exec_res, nonce)
        report = parse_report(payload, nonce) if payload is not None else None
        exec_res.stdout = ""
        return exec_res, report

    def _is_converged(
        self,
        energy_res: EnergyResult,
        report: TestReport | None,
        hidden_tests: list[str] | None,
    ) -> bool:
        if hidden_tests:
            return report is not None and report.all_passed and energy_res.score == 0.0
        return energy_res.score <= self.convergence_threshold

    def _build_trace_metadata(
        self,
        hs_record: HiddenStateRecord,
        exec_res: ExecutionResult,
        energy_res: EnergyResult,
    ) -> dict[str, Any]:
        """Build metadata dict for a LoopTrace, including optional JEPA predictions."""
        metadata: dict[str, Any] = {
            "timed_out": exec_res.timed_out,
            "tier_used": exec_res.tier_used,
            "dangerous_imports": exec_res.dangerous_imports,
            "model_id": hs_record.model_id,
        }

        # Phase 2: JEPA energy prediction (if world model is available)
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

                logger.info(
                    "JEPA prediction: predicted=%.1f actual=%.1f surprise=%.1f",
                    predicted_energy,
                    actual_energy,
                    surprise,
                )
            except Exception as e:
                logger.warning("JEPA prediction failed: %s", e)
                metadata["jepa_error"] = str(e)

        return metadata
