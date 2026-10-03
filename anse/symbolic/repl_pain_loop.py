"""
ANSE REPL Pain Loop & Physical Compiler Execution Attestation.

Enforces:
1. Anti-LaTeX Bleed-Through Linter: Rejects TeX macros (\\theta, \\Sigma, \\mathbb, \\rightarrow) in Lean code.
2. Physical Lean 4 Compiler Execution: Subprocess execution of `lake env lean` with real stderr capture.
3. Two-Stage Semantic Gatekeeper Integration: Zero hypothesis smuggling, zero vacuous mocks.
4. Iterative Pain-Feedback Loop: Supplies raw compiler stderr back to generator until Exit Code == 0.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from anse.core.semantic_gatekeeper import SemanticGatekeeper, SemanticViolation


@dataclass
class CompilationAttempt:
    iteration: int
    code: str
    returncode: int
    stderr: str
    stdout: str
    energy: float
    violations: List[str] = field(default_factory=list)


@dataclass
class REPLResult:
    success: bool
    final_code: str
    iterations: int
    history: List[CompilationAttempt]
    error_message: str = ""
    energy_score: float = 0.0


# Regex pattern to catch raw LaTeX macros inside Lean source code
LATEX_BLEED_PATTERN = re.compile(
    r"\\[a-zA-Z]+(?:\s*\{[^}]*\})*|"
    r"\\(?:theta|rightarrow|leftarrow|Sigma|mathbb|mathbf|forall|exists|in|notin|times|le|ge|neq|Delta|nabla|alpha|beta|gamma|nu|mu|psi|omega|pi)\b"
)


def detect_latex_bleed_through(code: str) -> List[str]:
    """Detects raw LaTeX macros mistakenly injected into Lean 4 source code."""
    # Strip string literals to avoid flagging valid escape characters like "\n" or "\t"
    code_no_strings = re.sub(r'"(?:\\.|[^"\\])*"', '""', code)
    # Find all occurrences of LaTeX backslash patterns
    matches = LATEX_BLEED_PATTERN.findall(code_no_strings)
    # Filter out valid escape sequences
    valid_escapes = {"\\n", "\\t", "\\r", "\\\"", "\\\\"}
    violations = [m for m in matches if m not in valid_escapes]
    return list(dict.fromkeys(violations))


class REPLPainLoop:
    """Physical Lean 4 REPL Pain Loop enforcing authentic compilation before artifact publication."""

    def __init__(self, workspace_root: Optional[str] = None, max_retries: int = 5, timeout_seconds: int = 90):
        self.workspace_root = workspace_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        self.formal_dir = os.path.join(self.workspace_root, "formal")
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.gatekeeper = SemanticGatekeeper()

    def audit_and_clean_syntax(self, code: str) -> Tuple[bool, List[str]]:
        """Checks for LaTeX bleed-through in Lean source code."""
        leaks = detect_latex_bleed_through(code)
        if leaks:
            msgs = [
                f"LaTeX Bleed-Through: Lean 4 source contains TeX macro '{leak}'. "
                f"Replace with genuine Unicode (e.g. ℝ, ℂ, ℕ, →, ∑, ∀, ∃, ν, Δ) or standard ASCII."
                for leak in leaks
            ]
            return False, mss if (mss := msgs) else []
        return True, []

    def compile_lean_snippet(
        self,
        code: str,
        filename_prefix: str = "CandidateProof",
        topic: Optional[str] = None,
    ) -> CompilationAttempt:
        """
        Physically writes code to disk in formal/ANSE and executes `lake env lean`.
        Returns structured CompilationAttempt with exact returncode, stderr, and energy penalty.
        """
        # 1. First-line check: Anti-LaTeX Bleed-Through
        syntax_ok, syntax_errors = self.audit_and_clean_syntax(code)
        if not syntax_ok:
            return CompilationAttempt(
                iteration=0,
                code=code,
                returncode=1,
                stderr="\n".join(syntax_errors),
                stdout="",
                energy=1_000_000.0,
                violations=syntax_errors,
            )

        # 2. Stage 2 Pre-filter: Check for Semantic Smuggling
        sem_passed, sem_violations, sem_energy = self.gatekeeper.audit_lean_code(code, topic=topic)
        if not sem_passed:
            err_msgs = [f"[{v.rule}] {v.message}" for v in sem_violations]
            return CompilationAttempt(
                iteration=0,
                code=code,
                returncode=2,
                stderr="SEMANTIC SMUGGLING REJECTION:\n" + "\n".join(err_msgs),
                stdout="",
                energy=sem_energy,
                violations=err_msgs,
            )

        # 3. Physical Lean 4 Compilation via `lake env lean`
        temp_filename = f"_repl_{filename_prefix}_{os.getpid()}.lean"
        temp_rel_path = os.path.join("ANSE", temp_filename)
        temp_abs_path = os.path.join(self.formal_dir, temp_rel_path)

        try:
            with open(temp_abs_path, "w", encoding="utf-8") as f:
                f.write(code)

            cmd = ["lake", "env", "lean", temp_rel_path]
            proc = subprocess.run(
                cmd,
                cwd=self.formal_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )

            stderr = proc.stderr.strip()
            stdout = proc.stdout.strip()

            if proc.returncode != 0:
                energy = 1_000_000.0
                err_summary = stderr if stderr else stdout
                return CompilationAttempt(
                    iteration=0,
                    code=code,
                    returncode=proc.returncode,
                    stderr=err_summary,
                    stdout=stdout,
                    energy=energy,
                    violations=[f"Physical Compilation Error (Exit {proc.returncode}): {err_summary}"],
                )

            # Exit Code == 0 and Semantic Gatekeeper == 0
            return CompilationAttempt(
                iteration=0,
                code=code,
                returncode=0,
                stderr="",
                stdout=stdout,
                energy=0.0,
                violations=[],
            )

        except subprocess.TimeoutExpired:
            return CompilationAttempt(
                iteration=0,
                code=code,
                returncode=124,
                stderr=f"Compilation timed out after {self.timeout_seconds}s.",
                stdout="",
                energy=1_000_000.0,
                violations=["TimeoutExpired"],
            )
        finally:
            if os.path.exists(temp_abs_path):
                try:
                    os.remove(temp_abs_path)
                except OSError:
                    pass

    def run_pain_loop(
        self,
        initial_code: str,
        topic: Optional[str] = None,
        generator_repair_fn: Optional[Callable[[str, str], str]] = None,
    ) -> REPLResult:
        """
        Executes the iterative REPL Pain Loop:
        If physical compilation fails, feeds stderr back to generator_repair_fn.
        Terminates only upon Exit Code 0 and E = 0, or max_retries exhaustion.
        """
        current_code = initial_code
        history: List[CompilationAttempt] = []

        for attempt_idx in range(1, self.max_retries + 1):
            attempt = self.compile_lean_snippet(
                current_code,
                filename_prefix=f"attempt_{attempt_idx}",
                topic=topic,
            )
            attempt.iteration = attempt_idx
            history.append(attempt)

            if attempt.returncode == 0 and attempt.energy == 0.0:
                return REPLResult(
                    success=True,
                    final_code=current_code,
                    iterations=attempt_idx,
                    history=history,
                    error_message="",
                    energy_score=0.0,
                )

            # Failure occurred: if repair callback provided, generate next iteration
            if generator_repair_fn and attempt_idx < self.max_retries:
                error_feedback = attempt.stderr or "\n".join(attempt.violations)
                current_code = generator_repair_fn(current_code, error_feedback)
            else:
                break

        last_attempt = history[-1]
        return REPLResult(
            success=False,
            final_code=current_code,
            iterations=len(history),
            history=history,
            error_message=last_attempt.stderr or "\n".join(last_attempt.violations),
            energy_score=last_attempt.energy,
        )
