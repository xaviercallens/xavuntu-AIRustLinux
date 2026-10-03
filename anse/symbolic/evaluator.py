"""
Energy evaluator: converts raw :class:`ExecutionResult` into a scalar
Energy score  E ∈ [0, 100].

Energy is the foundational reward signal for all ANSE learning loops.
Lower energy = better.  Zero = perfect execution.

Energy scale
────────────
  0.0  Clean execution, all tests pass
  5.0  Clean execution, no tests defined
 30.0  Wrong output (diff against expected)
 40.0  ModuleNotFoundError / ImportError
 50.0  Unit-test failure (AssertionError)
 60.0  Runtime exception
 80.0  Execution timeout
100.0  SyntaxError (code is unparseable)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from anse.symbolic.hidden_tests import TestReport
from anse.symbolic.sandbox import ExecutionResult

# ─── Categories ──────────────────────────────────────────────────────────────


class EnergyCategory(str, Enum):  # noqa: UP042
    PERFECT = "perfect"
    NO_TESTS = "no_tests"
    WRONG_OUTPUT = "wrong_output"
    IMPORT_ERROR = "import_error"
    TEST_FAILURE = "test_failure"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    SYNTAX_ERROR = "syntax_error"
    TRIVIAL_SIMULATION = "trivial_simulation"


# Default energy levels (can be overridden by subclassing EnergyEvaluator)
_DEFAULT_ENERGY: dict[EnergyCategory, float] = {
    EnergyCategory.PERFECT: 0.0,
    EnergyCategory.NO_TESTS: 5.0,
    EnergyCategory.WRONG_OUTPUT: 30.0,
    EnergyCategory.IMPORT_ERROR: 40.0,
    EnergyCategory.TEST_FAILURE: 50.0,
    EnergyCategory.RUNTIME_ERROR: 60.0,
    EnergyCategory.TIMEOUT: 80.0,
    EnergyCategory.SYNTAX_ERROR: 100.0,
    EnergyCategory.TRIVIAL_SIMULATION: 1_000_000.0,
}


@dataclass
class EnergyResult:
    score: float
    """The raw energy value in [0, 100]."""

    category: EnergyCategory
    """Which failure mode was detected."""

    pain_signal: str
    """Human-readable feedback to append to the prompt as a 'Pain Signal'."""

    execution: ExecutionResult
    """The underlying execution result."""

    expected_output: str | None = None
    """If an expected output was provided, stored here for reference."""

    def difficulty_tier(self) -> str:
        """Classify task difficulty based on energy and failure category (Directive D5).

        Returns:
            'trivial': Solved or near-perfect on first try (E == 0)
            'fixable': Minor error or assertion failure (0 < E < 20)
            'hard': Structural error, runtime exception (20 <= E < 50)
            'phd': Impossible for sub-3B to self-correct (E >= 50)
        """
        if self.score == 0.0:
            return "trivial"
        if self.score < 20.0:
            return "fixable"
        if self.score < 50.0:
            return "hard"
        return "phd"


# ─── Evaluator ───────────────────────────────────────────────────────────────


class EnergyEvaluator:
    """
    Convert an :class:`ExecutionResult` into an :class:`EnergyResult`.

    Parameters
    ----------
    energy_levels:
        Override the default energy-per-category mapping.
    """

    def __init__(
        self,
        energy_levels: dict[EnergyCategory, float] | None = None,
    ) -> None:
        self._levels = {**_DEFAULT_ENERGY, **(energy_levels or {})}

    # ── Public ────────────────────────────────────────────────────────────────

    def evaluate(
        self,
        result: ExecutionResult,
        code: str | None = None,
        expected_output: str | None = None,
    ) -> EnergyResult:
        """
        Classify *result* and return an :class:`EnergyResult`.

        Parameters
        ----------
        result:
            Output from :class:`~anse.symbolic.sandbox.SandboxExecutor`.
        code:
            Optional source code string that produced the result.
        expected_output:
            Optional string the stdout should equal (stripped). If provided,
            a mismatch adds a WRONG_OUTPUT penalty on top of any other error.
        """
        category, pain = self._categorise(result, code=code)
        score = self._levels[category]

        # Secondary check: wrong output even if execution succeeded
        if (
            category in (EnergyCategory.PERFECT, EnergyCategory.NO_TESTS)
            and expected_output is not None
        ):
            actual = result.stdout.strip()
            expected = expected_output.strip()
            if actual != expected:
                category = EnergyCategory.WRONG_OUTPUT
                score = self._levels[EnergyCategory.WRONG_OUTPUT]
                pain = (
                    f"Your code ran without errors but produced the wrong output.\n"
                    f"Expected:\n{expected}\n\nActual:\n{actual}"
                )

        return EnergyResult(
            score=score,
            category=category,
            pain_signal=pain,
            execution=result,
            expected_output=expected_output,
        )

    def evaluate_hidden_tests(
        self,
        result: ExecutionResult,
        report: TestReport | None,
    ) -> EnergyResult:
        """
        Graded energy from independently run hidden tests.

        Crashes before the harness keep their categorical energy. Otherwise
        E = E_test_failure * failed / total, so partial progress lowers energy.
        *result.stdout* must already have the harness report line stripped.
        """
        err = self._check_error_categories(result, result.stdout or "", result.stderr or "")
        if err is not None and (report is None or err[0] is not EnergyCategory.TEST_FAILURE):
            return EnergyResult(
                score=self._levels[err[0]], category=err[0], pain_signal=err[1], execution=result
            )

        ceiling = self._levels[EnergyCategory.TEST_FAILURE]
        if report is None or report.total == 0:
            return EnergyResult(
                score=ceiling,
                category=EnergyCategory.TEST_FAILURE,
                pain_signal="The hidden tests never ran. Your code must not exit or block at import time.",
                execution=result,
            )
        if report.all_passed:
            return EnergyResult(
                score=self._levels[EnergyCategory.PERFECT],
                category=EnergyCategory.PERFECT,
                pain_signal=f"All {report.total} hidden tests passed. Energy = 0.",
                execution=result,
            )
        failures = "\n".join(f"  - {f}" for f in report.failures)
        return EnergyResult(
            score=ceiling * report.failed / report.total,
            category=EnergyCategory.TEST_FAILURE,
            pain_signal=(
                f"{report.failed} of {report.total} hidden tests failed. First failures:\n{failures}"
            ),
            execution=result,
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _check_test_presence(self, stdout: str, code: str | None) -> bool:
        if _matches(stdout, r"(passed|ok|\.{3,}|test_)"):
            return True
        if code is not None and ("assert " in code or "assert(" in code):
            return True
        return False

    def _check_error_categories(
        self, result: ExecutionResult, stdout: str, stderr: str
    ) -> tuple[EnergyCategory, str] | None:
        if _matches(stderr, r"TRIVIAL_SIMULATION"):
            return (
                EnergyCategory.TRIVIAL_SIMULATION,
                f"Your code is too simple to be a genuine solution to this hard problem.\nStderr:\n{stderr}",
            )
        if result.timed_out:
            return (
                EnergyCategory.TIMEOUT,
                f"Your code timed out after the allowed execution window.\nStderr:\n{stderr}",
            )
        if _matches(stderr, r"SyntaxError"):
            return (
                EnergyCategory.SYNTAX_ERROR,
                f"Your code has a syntax error and could not be parsed.\nError:\n{stderr}",
            )
        if _matches(stderr, r"(ModuleNotFoundError|ImportError)"):
            return (
                EnergyCategory.IMPORT_ERROR,
                f"Your code tried to import a module that is not available.\nError:\n{stderr}",
            )
        if _matches(stderr, r"AssertionError") or _matches(stdout, r"FAILED|FAIL"):
            return (
                EnergyCategory.TEST_FAILURE,
                f"One or more tests failed.\nStderr:\n{stderr}\nStdout:\n{stdout}",
            )
        if result.returncode != 0 and stderr:
            return (
                EnergyCategory.RUNTIME_ERROR,
                f"Your code raised a runtime exception.\nTraceback:\n{stderr}",
            )
        return None

    def _categorise(
        self,
        result: ExecutionResult,
        code: str | None = None,
    ) -> tuple[EnergyCategory, str]:
        """Return (category, pain_signal) for *result*."""
        stderr = result.stderr or ""
        stdout = result.stdout or ""

        err_cat = self._check_error_categories(result, stdout, stderr)
        if err_cat is not None:
            return err_cat

        # Code ran cleanly — check if there were tests
        if self._check_test_presence(stdout, code):
            return (
                EnergyCategory.PERFECT,
                "All tests passed. Energy = 0.",
            )

        return (
            EnergyCategory.NO_TESTS,
            "Code executed successfully but no tests were detected.",
        )


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _matches(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, re.IGNORECASE))


# ─── Convenience singleton ────────────────────────────────────────────────────
_default_evaluator: EnergyEvaluator | None = None


def evaluate_energy(
    result: ExecutionResult,
    code: str | None = None,
    expected_output: str | None = None,
) -> EnergyResult:
    """Module-level convenience function using the default :class:`EnergyEvaluator`."""
    global _default_evaluator
    if _default_evaluator is None:
        _default_evaluator = EnergyEvaluator()
    return _default_evaluator.evaluate(result, code=code, expected_output=expected_output)
