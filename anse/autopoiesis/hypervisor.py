"""
Autopoiesis Hypervisor.

Phase 3: the system replaces a component of itself with a better version, safely.

A child version is promoted only if it clears three gates, in this order:

1. Equivalence   it passes every hidden test (the parent's pass count is recorded next to it)
                 and computes the same benchmark result as the parent. Correctness before speed.
                 The verdict is formed OUT OF BAND, in a process the child never runs in
                 (see "Isolation" below), so a child cannot approve itself.
2. Domination    parent and child are measured N times, interleaved, in the sandbox; the median
                 paired energy gain must exceed the measured noise and pass a sign test
                 (see :func:`judge_domination`).
3. Registry      the swap is a pointer move in :class:`~anse.autopoiesis.registry.ComponentRegistry`:
                 versioned, audited in an append-only lineage, and reversible with ``rollback``.

Energy is the project-wide definition from
:class:`~anse.symbolic.performance_evaluator.PerformanceEnergyEvaluator`:
``E = w_t * duration_ms + w_m * peak_ram_mb``. ``duration_ms`` is the wall time of the benchmark
workload, which is part of the sandboxed script, clocked by the trusted driver (interpreter
start-up and the import of the component are outside the clock).

Isolation
---------
The script handed to the sandbox is a trusted *driver* (:func:`build_driver`). The driver removes
its own source file, then starts a *worker* interpreter that loads the component and answers
requests over a pipe: "call this function with these literal arguments" or "run this workload".
The worker's stdout is pointed at ``/dev/null`` before the component is loaded. Consequences:

* the hidden tests, their expected values and the report nonce exist only in the driver process
  and in a file that is gone before the component runs; nothing the component can ``open()``
  (``__file__``, the working directory, ``sys.argv``) contains them;
* assertions are evaluated in the driver on values rebuilt with ``ast.literal_eval`` from the
  worker's replies, so a trick object (``__eq__`` always true) never reaches an ``assert``;
* duration and peak RAM are taken by the driver (its own clock, the kernel's accounting of the
  worker), so patching ``time`` or exiting early inside the component cannot shorten them;
* the hypervisor only believes a run that exited 0 and whose LAST stdout line carries the nonce.

The price: component interfaces must take and return Python literals (ints, strings, lists,
tuples, dicts, sets, booleans, None) and must not rely on mutating their arguments in place.
A child importing a module on the sandbox blocklist is refused, because Tier 1 cannot contain it.
Out of scope, and left to the Tier-2 container: attacks on the OS itself (ptrace, another
process's memory). As defence in depth the driver marks itself non-dumpable, which closes
``/proc/<driver>/mem`` and ``/proc/<driver>/fd`` to the worker. POSIX only.

Measurement caveat: ``ru_maxrss`` survives fork+exec, so the RAM term has a constant floor equal
to the footprint of the launching processes unless the component exceeds it. It cancels in the
paired gains used for the decision, but callers that want a meaningful RAM term should measure
from a lean process (``run_phase3_evolution.py`` keeps torch out of the measuring process).
"""

from __future__ import annotations

import json
import logging
import math
import secrets
import statistics
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

from anse.autopoiesis.registry import ComponentRegistry
from anse.config import SandboxConfig, get_config
from anse.symbolic.hidden_tests import TestReport, parse_report
from anse.symbolic.performance_evaluator import PerformanceEnergyEvaluator, PerformanceEnergyResult
from anse.symbolic.sandbox import ExecutionResult, SandboxExecutor, scan_dangerous_imports
from anse.symbolic.trusted_driver import (
    _DRIVER_BUDGET_FRACTION,
    _MAX_REPORTED_FAILURES,
    build_driver,
    trusted_payload,
)


@dataclass
class BaselineMetrics:
    energy: float
    duration_ms: float
    peak_ram_mb: float


def legacy_single_sample_rule(
    child_result: PerformanceEnergyResult, parent_baseline: BaselineMetrics
) -> bool:
    """
    The pre-evolution swap condition, kept verbatim so it can be evaluated against the new
    pipeline: one child sample against a baseline number, no behavioural check.
    """
    return child_result.is_valid and child_result.score < parent_baseline.energy


# ─── Domination rule ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DominationRule:
    samples: int = 12
    """Interleaved parent/child measurement pairs."""

    z: float = 3.0
    """The median paired gain must exceed z standard errors of that median."""

    min_relative_gain: float = 0.05
    """...and this fraction of the parent's median energy (floor against a lucky tiny MAD)."""

    max_sign_test_p: float = 0.01
    """...and the child must win enough pairs for a one-sided sign test at this level (11 of 12)."""


@dataclass(frozen=True)
class DominationVerdict:
    dominates: bool
    reason: str
    parent_median: float
    child_median: float
    gain: float
    """Median of the paired gains parent_i - child_i."""
    noise: float
    """Standard error of that median, estimated from the MAD of the paired gains."""
    threshold: float
    pair_wins: int
    pairs: int
    pair_wins_required: int


def _mad(values: list[float]) -> float:
    centre = statistics.median(values)
    return statistics.median(abs(v - centre) for v in values)


def required_pair_wins(pairs: int, max_p: float) -> int:
    """Smallest k with P(Binomial(pairs, 1/2) >= k) <= max_p; pairs + 1 if even a clean sweep is not enough."""
    tail = 0.0
    required = pairs + 1
    for k in range(pairs, -1, -1):
        tail += math.comb(pairs, k) / 2.0**pairs
        if tail > max_p:
            break
        required = k
    return required


def judge_domination(
    parent_energies: list[float], child_energies: list[float], rule: DominationRule | None = None
) -> DominationVerdict:
    """
    Decide whether the child's energy is lower than the parent's beyond measurement noise.

    Sample *i* of each side was measured back to back, so the analysis is PAIRED: on a shared,
    loaded machine the same code swings by 2-3x between load regimes lasting seconds, which
    ruins a comparison of two marginal medians but largely cancels inside a pair. With
    ``gain_i = parent_i - child_i`` the child dominates iff all three hold:

    * sign test: the child wins at least ``required_pair_wins`` pairs. Distribution-free; for
      identical code each pair is a coin flip, so >= 11 of 12 has probability 13/4096 (~0.3%),
      while one unlucky load spike on the child's side does not veto a genuine improvement.
    * noise margin: ``median(gain)`` exceeds ``z`` standard errors, with the spread taken from
      the data itself (``sigma ~ 1.4826 * MAD(gain)``, ``SE(median) ~ 1.2533 * sigma / sqrt(n)``),
      so one or two load spikes move neither the estimate nor its error bar.
    * practical floor: ``median(gain)`` exceeds ``min_relative_gain * median(parent)``, because
      with few samples the MAD can come out near zero by luck and a swap has a cost.

    A false promotion needs three unlikely things at once; a missed promotion only costs a
    retry, so the rule is deliberately conservative.
    """
    rule = rule or DominationRule()
    n = len(parent_energies)
    if n != len(child_energies):
        raise ValueError(f"Paired samples required: {n} parent vs {len(child_energies)} child")
    if n < 3:
        raise ValueError(f"At least 3 paired samples required, got {n}")

    gains = [p - c for p, c in zip(parent_energies, child_energies)]
    parent_median = statistics.median(parent_energies)
    child_median = statistics.median(child_energies)
    gain = statistics.median(gains)
    noise = 1.2533 * 1.4826 * _mad(gains) / math.sqrt(n)
    threshold = max(rule.z * noise, rule.min_relative_gain * parent_median)
    wins = sum(g > 0 for g in gains)
    wins_required = required_pair_wins(n, rule.max_sign_test_p)

    if wins < wins_required:
        ok, reason = False, f"child won {wins}/{n} interleaved pairs, {wins_required} required"
    elif gain <= threshold:
        ok, reason = (
            False,
            f"median paired gain {gain:.2f} does not exceed noise threshold {threshold:.2f}",
        )
    else:
        ok, reason = (
            True,
            f"median paired gain {gain:.2f} > threshold {threshold:.2f}, child won {wins}/{n} pairs",
        )
    return DominationVerdict(
        ok, reason, parent_median, child_median, gain, noise, threshold, wins, n, wins_required
    )


# ─── Measurement and decision records ────────────────────────────────────────


@dataclass(frozen=True)
class BenchmarkSample:
    energy: float
    duration_ms: float
    peak_ram_mb: float
    valid: bool
    output: str | None
    """repr() of the workload's BENCH_RESULT, or None if the run never reached the report line."""
    evaluation: PerformanceEnergyResult = field(repr=False, compare=False)


@dataclass(frozen=True)
class EquivalenceResult:
    eligible: bool
    reason: str
    parent_passed: int
    child_passed: int
    total: int
    child_failures: list[str]


@dataclass(frozen=True)
class DifferentialResult:
    completed: bool
    """False when either side produced no trusted report (mismatches then equals total)."""
    total: int
    mismatches: int
    examples: list[str]

    @property
    def agrees(self) -> bool:
        return self.completed and self.total > 0 and self.mismatches == 0


@dataclass(frozen=True)
class EvolutionDecision:
    component: str
    promoted: bool
    stage: str
    """Where the decision was taken: equivalence | benchmark | domination."""
    reason: str
    parent_version: int
    child_version: int | None
    equivalence: EquivalenceResult
    verdict: DominationVerdict | None
    parent_samples: list[BenchmarkSample]
    child_samples: list[BenchmarkSample]

    @property
    def speedup(self) -> float | None:
        """Median parent duration / median child duration, when both sides were measured."""
        if not self.parent_samples or not self.child_samples:
            return None
        child = statistics.median(s.duration_ms for s in self.child_samples)
        return statistics.median(s.duration_ms for s in self.parent_samples) / max(child, 1e-6)

    def to_record(self) -> dict[str, Any]:
        """Flat audit record written to the registry lineage."""
        record: dict[str, Any] = {
            "stage": self.stage,
            "reason": self.reason,
            "tests_total": self.equivalence.total,
            "parent_tests_passed": self.equivalence.parent_passed,
            "child_tests_passed": self.equivalence.child_passed,
            "parent_energy": None,
            "child_energy": None,
            "samples_per_side": len(self.child_samples),
        }
        if self.verdict is not None:
            record.update(
                parent_energy=round(self.verdict.parent_median, 3),
                child_energy=round(self.verdict.child_median, 3),
                median_paired_gain=round(self.verdict.gain, 3),
                noise_threshold=round(self.verdict.threshold, 3),
                pair_wins=self.verdict.pair_wins,
            )
        return record


# ─── Hypervisor ──────────────────────────────────────────────────────────────


class AutopoiesisHypervisor:
    """Validates a child version against the active parent and swaps it in through the registry."""

    def __init__(
        self,
        registry: ComponentRegistry,
        sandbox: SandboxExecutor | None = None,
        evaluator: PerformanceEnergyEvaluator | None = None,
        rule: DominationRule | None = None,
        sandbox_config: SandboxConfig | None = None,
    ) -> None:
        """*sandbox_config* must be the configuration *sandbox* was built with (blocklist, timeout)."""
        self.registry = registry
        self.sandbox_config = sandbox_config or get_config().sandbox
        self.sandbox = sandbox or SandboxExecutor(config=self.sandbox_config)
        self.evaluator = evaluator or PerformanceEnergyEvaluator()
        self.rule = rule or DominationRule()
        self._proxies: dict[str, RCUComponentProxy] = {}

    def register_proxy(self, component: str, callable_obj: Any) -> RCUComponentProxy:
        """Register a live RCU proxy for a component to enable atomic zero-downtime hot-swaps."""
        proxy = RCUComponentProxy(
            callable_obj, name=component, version=self.registry.active_version(component)
        )
        self._proxies[component] = proxy
        return proxy

    def get_proxy(self, component: str) -> RCUComponentProxy | None:
        """Return the active RCU proxy for a component if registered."""
        return self._proxies.get(component)

    # ── isolated execution ───────────────────────────────────────────────────
    def _run_driver(self, code: str, **mode: Any) -> tuple[ExecutionResult, str | None]:
        """
        Run *code* behind a fresh driver; returns the raw result and the trusted JSON payload
        (None if the run cannot be trusted). Tier 1 is forced because the AST scan would flag the
        driver's own imports; the component's imports are vetted by :meth:`blocked_imports`.
        """
        nonce = "ANSE-" + secrets.token_hex(16)
        budget = max(1.0, _DRIVER_BUDGET_FRACTION * self.sandbox_config.timeout_seconds)
        result = self.sandbox.execute(build_driver(nonce, code, budget, **mode), force_tier=1)
        line = trusted_payload(result, nonce)
        return result, (line[len(nonce) + 1 :] if line is not None else None)

    def blocked_imports(self, code: str) -> list[str]:
        """Imports of *code* that the Tier-1 sandbox cannot contain (the sandbox's own blocklist)."""
        return scan_dangerous_imports(code, self.sandbox_config.dangerous_modules)

    # ── gate 1: equivalence ──────────────────────────────────────────────────
    def run_hidden_tests(self, code: str, tests: list[str]) -> TestReport | None:
        """Hidden tests against *code*, asserted in the driver process; None if no trusted report came back."""
        _, payload = self._run_driver(code, tests=list(tests))
        if payload is None:
            return None
        return parse_report("report " + payload, "report")

    def check_equivalence(
        self, parent_code: str, child_code: str, tests: list[str]
    ) -> EquivalenceResult:
        """The child must pass every hidden test; what the parent passes is recorded alongside."""
        if not tests:
            return EquivalenceResult(
                False, "no hidden tests: equivalence cannot be established", 0, 0, 0, []
            )
        blocked = self.blocked_imports(child_code)
        if blocked:
            reason = "child imports modules the sandbox cannot contain: " + ", ".join(
                sorted(set(blocked))
            )
            return EquivalenceResult(False, reason, 0, 0, len(tests), [])
        parent = self.run_hidden_tests(parent_code, tests)
        child = self.run_hidden_tests(child_code, tests)
        parent_passed = parent.passed if parent else 0
        if child is None:
            return EquivalenceResult(
                False,
                "child crashed or timed out before the hidden tests reported",
                parent_passed,
                0,
                len(tests),
                [],
            )
        if not child.all_passed or child.total != len(tests):
            reason = f"child passes {child.passed}/{len(tests)} hidden tests (parent {parent_passed}/{len(tests)})"
            return EquivalenceResult(
                False, reason, parent_passed, child.passed, len(tests), child.failures
            )
        return EquivalenceResult(
            True,
            f"child passes all {len(tests)} hidden tests",
            parent_passed,
            child.passed,
            len(tests),
            [],
        )

    def differential_test(
        self, reference_code: str, candidate_code: str, entry: str, inputs: list[list[Any]]
    ) -> DifferentialResult:
        """
        Call ``entry(*args)`` for every args list in *inputs* on both versions, each in its own
        isolated worker, and compare the outcomes (repr of the value, or the exception type).
        Not part of :meth:`evolve`: it exists so a caller can audit promotions with inputs the
        gate never saw.
        """
        calls = [(entry, list(args)) for args in inputs]
        outcomes: list[list[str] | None] = []
        for code in (reference_code, candidate_code):
            _, payload = self._run_driver(code, calls=calls)
            try:
                found = json.loads(payload)["outcomes"] if payload is not None else None
            except (ValueError, KeyError, TypeError):
                found = None
            outcomes.append(
                [str(o) for o in found]
                if isinstance(found, list) and len(found) == len(calls)
                else None
            )
        reference, candidate = outcomes
        if reference is None or candidate is None:
            side = "reference" if reference is None else "candidate"
            return DifferentialResult(
                False, len(calls), len(calls), [f"{side} run produced no trusted report"]
            )
        unusable = sum(not o.startswith(("ok ", "raised ")) for o in reference)
        if unusable:
            return DifferentialResult(
                False, len(calls), len(calls), [f"reference failed on {unusable} inputs"]
            )
        examples = [
            f"{entry}{tuple(args)!r}: reference {ref} | candidate {cand}"[:300]
            for args, ref, cand in zip(inputs, reference, candidate)
            if ref != cand
        ]
        return DifferentialResult(
            True, len(calls), len(examples), examples[:_MAX_REPORTED_FAILURES]
        )

    # ── gate 2: measurement ──────────────────────────────────────────────────
    def measure_once(self, code: str, workload: str) -> BenchmarkSample:
        """
        Run *workload* once against *code* in an isolated worker. The workload must assign
        ``BENCH_RESULT``. Its repr, the workload's wall time and the worker's peak RAM are
        reported by the driver; the component cannot write, shorten or skip any of them.
        """
        result, payload = self._run_driver(code, workload=workload)
        output: str | None = None
        try:
            data = json.loads(payload) if payload is not None else None
            if data is not None:
                output = str(data["output"])
                result.duration_ms = float(data["duration_ms"])
                result.peak_ram_mb = float(data["peak_ram_mb"])
        except (ValueError, KeyError, TypeError):
            output = None
        if output is None and result.returncode == 0 and not result.timed_out:
            result.returncode = 1  # exited "cleanly" without a trusted report: that is a failure
        result.stdout = ""  # the report line is consumed here; nothing else on stdout is trusted
        evaluation = self.evaluator.evaluate(result)
        return BenchmarkSample(
            energy=evaluation.score,
            duration_ms=result.duration_ms,
            peak_ram_mb=result.peak_ram_mb,
            valid=evaluation.is_valid and output is not None,
            output=output,
            evaluation=evaluation,
        )

    def measure_interleaved(
        self, parent_code: str, child_code: str, workload: str, samples: int | None = None
    ) -> tuple[list[BenchmarkSample], list[BenchmarkSample]]:
        """
        Measure both sides *samples* times, back to back, alternating which side goes first so
        slow drift in machine load hits both equally. Stops at the first invalid run.
        """
        parent_samples: list[BenchmarkSample] = []
        child_samples: list[BenchmarkSample] = []
        for i in range(samples or self.rule.samples):
            order = (
                (("p", parent_code), ("c", child_code))
                if i % 2 == 0
                else (("c", child_code), ("p", parent_code))
            )
            for side, code in order:
                (parent_samples if side == "p" else child_samples).append(
                    self.measure_once(code, workload)
                )
            if not (parent_samples[-1].valid and child_samples[-1].valid):
                break
        return parent_samples, child_samples

    @staticmethod
    def _benchmark_failure(
        parents: list[BenchmarkSample], children: list[BenchmarkSample]
    ) -> str | None:
        if not all(s.valid for s in parents):
            return "parent failed its own benchmark: " + parents[-1].evaluation.category.value
        if not all(s.valid for s in children):
            return "child failed the benchmark: " + children[-1].evaluation.category.value
        parent_outputs = {s.output for s in parents}
        if len(parent_outputs) != 1:
            return "benchmark is not deterministic for the parent; outputs cannot be compared"
        if {s.output for s in children} != parent_outputs:
            return "child's benchmark result differs from the parent's"
        return None

    # ── full pipeline ────────────────────────────────────────────────────────
    def evolve(
        self, component: str, child_code: str, tests: list[str], workload: str
    ) -> EvolutionDecision:
        """Equivalence -> interleaved measurement -> domination -> promote (or audited rejection)."""
        parent_version = self.registry.active_version(component)
        parent_code = self.registry.code(component, parent_version)

        equivalence = self.check_equivalence(parent_code, child_code, tests)
        verdict: DominationVerdict | None = None
        parents: list[BenchmarkSample] = []
        children: list[BenchmarkSample] = []
        if not equivalence.eligible:
            stage, reason = "equivalence", equivalence.reason
        else:
            parents, children = self.measure_interleaved(parent_code, child_code, workload)
            failure = self._benchmark_failure(parents, children)
            if failure is not None:
                stage, reason = "benchmark", failure
            else:
                verdict = judge_domination(
                    [s.energy for s in parents], [s.energy for s in children], self.rule
                )
                stage, reason = "domination", verdict.reason

        promoted = verdict is not None and verdict.dominates
        decision = EvolutionDecision(
            component,
            promoted,
            stage,
            reason,
            parent_version,
            None,
            equivalence,
            verdict,
            parents,
            children,
        )
        if not promoted:
            self.registry.record_rejection(component, child_code, decision.to_record())
            return decision
        child_version = self.registry.promote(component, child_code, decision.to_record())
        if component in self._proxies:
            self._try_swap_proxy(component, child_code, child_version)
        return EvolutionDecision(
            component,
            True,
            stage,
            reason,
            parent_version,
            child_version,
            equivalence,
            verdict,
            parents,
            children,
        )

    def rollback(self, component: str, reason: str = "manual rollback") -> int:
        version = self.registry.rollback(component, reason)
        if component in self._proxies:
            code = self.registry.code(component, version)
            self._try_swap_proxy(component, code, version)
        return version

    def _try_swap_proxy(self, component: str, code: str, version: int) -> None:
        """Helper to extract updated component function and swap the live RCU proxy."""
        try:
            ns: dict[str, Any] = {}
            exec(code, ns)
            if component in ns and callable(ns[component]):
                self._proxies[component].swap(ns[component], version)
        except Exception as err:
            logger.warning("Failed to swap RCU proxy for component %s (v%d): %s", component, version, err)


class RCUComponentProxy:
    """Read-Copy-Update thread-safe proxy for zero-downtime hot-swapping in live processes.

    Ensures concurrent callers never observe partial state or torn execution frames
    during autopoietic component upgrades.
    """

    def __init__(self, initial_callable: Any, name: str = "anonymous", version: int = 1) -> None:
        self._callable = initial_callable
        self.name = name
        self._version = version
        self._lock = threading.Lock()
        self._call_count = 0

    @property
    def version(self) -> int:
        return self._version

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def active_callable(self) -> Any:
        return self._callable

    def swap(self, new_callable: Any, new_version: int | None = None) -> int:
        """Atomically swap the active callable pointer with a newly promoted version."""
        if not callable(new_callable):
            raise TypeError(f"Target component for swap must be callable, got {type(new_callable)}")
        with self._lock:
            self._callable = new_callable
            self._version = new_version if new_version is not None else self._version + 1
            return self._version

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the active version safely without taking a lock during computation."""
        fn = self._callable
        with self._lock:
            self._call_count += 1
        return fn(*args, **kwargs)

