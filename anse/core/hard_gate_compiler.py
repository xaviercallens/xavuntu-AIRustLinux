#!/usr/bin/env python3
"""
ANSE Hard-Gate Compiler: Fail-Closed Two-Stage Verification Engine with REPL Pain Loop.

Stage 1: Deterministic Syntax Compilation (Exit Code == 0 via `lake env lean` / `python3`).
Stage 2: Semantic & Epistemic Audit (Zero hypothesis smuggling, zero vacuous mocks, zero LaTeX bleed-through).
"""

from __future__ import annotations

import os
import subprocess
from typing import Callable, Optional, Tuple

from anse.core.semantic_gatekeeper import SemanticGatekeeper
from anse.symbolic.repl_pain_loop import REPLPainLoop, detect_latex_bleed_through


class HardGateCompiler:
    def __init__(self, max_retries: int = 5, timeout_seconds: int = 90):
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.gatekeeper = SemanticGatekeeper()
        self.repl_loop = REPLPainLoop(max_retries=max_retries, timeout_seconds=timeout_seconds)

    def compile_and_verify(
        self,
        file_path: str,
        llm_callback: Optional[Callable[[str, str], None]] = None,
        topic: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Two-Stage Hard-Gate Verification:
        Stage 1: Deterministic Syntax Compilation (Exit Code == 0).
        Stage 2: Semantic & Epistemic Audit (No hypothesis smuggling, no LaTeX bleed-through).
        Assigns E = 10^6 and triggers retry if any stage fails.
        """
        extension = os.path.splitext(file_path)[1]

        for attempt in range(self.max_retries):
            # Check for file existence
            if extension == '.lean':
                actual_full_path = os.path.join("formal", file_path) if not file_path.startswith("formal/") else file_path
                cmd = ["lake", "env", "lean", file_path]
                cwd = "formal"
            elif extension == '.py':
                actual_full_path = file_path
                cmd = ["python3", file_path]
                cwd = "."
            else:
                return False, f"Unsupported extension: {extension}"

            if not os.path.exists(actual_full_path):
                return False, f"File does not exist: {actual_full_path}"

            with open(actual_full_path, "r", encoding="utf-8") as f:
                code_content = f.read()

            # Pre-Stage: Anti-LaTeX Bleed-Through Check for Lean 4
            if extension == '.lean':
                leaks = detect_latex_bleed_through(code_content)
                if leaks:
                    err_msg = f"LATEX BLEED-THROUGH DETECTED: {', '.join(leaks)}. Replace with native Lean 4 Unicode or ASCII."
                    print(f"[Hard-Gate Pre-Stage FAILED - E=1000000]: {err_msg}")
                    if llm_callback:
                        llm_callback(file_path, err_msg)
                        continue
                    return False, f"Semantic audit rejected: {err_msg}"

            print(f"[Hard-Gate] Attempt {attempt+1}/{self.max_retries} for {file_path}")
            try:
                res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=self.timeout_seconds)
                output = res.stderr if res.stderr else res.stdout
            except subprocess.TimeoutExpired:
                err_msg = f"Compilation timed out after {self.timeout_seconds}s."
                if llm_callback:
                    llm_callback(file_path, err_msg)
                    continue
                return False, err_msg

            # Stage 1: Syntax Compilation Check
            if res.returncode != 0:
                print(f"[Hard-Gate Stage 1 - Syntax FAILED]: {file_path}. Error:\n{output[:300]}...")
                if llm_callback:
                    print("[Hard-Gate] Requesting LLM correction for Syntax...")
                    llm_callback(file_path, output)
                    continue
                return False, f"Compilation failed: {output}"

            # Stage 2: Semantic & Epistemic Hard-Gate
            if extension == '.lean':
                sem_passed, sem_violations, penalty_energy = self.gatekeeper.audit_lean_code(code_content, topic=topic)
            else:
                sem_passed, sem_violations, penalty_energy = self.gatekeeper.audit_python_code(code_content)

            if not sem_passed:
                err_msg = "\n".join([f"[{v.rule}] {v.message}" for v in sem_violations])
                print(f"[Hard-Gate Stage 2 - Semantic REJECTED: E={penalty_energy:.0f}]:\n{err_msg}")
                if llm_callback:
                    print("[Hard-Gate] Requesting LLM correction for Epistemic/Semantic Smuggling...")
                    llm_callback(file_path, f"SEMANTIC HARD-GATE REJECTION:\n{err_msg}")
                    continue
                return False, f"Semantic audit rejected: {err_msg}"

            print(f"[Hard-Gate] SUCCESS: {file_path} passed both Syntax & Semantic Audits.")
            return True, "Success"

        print(f"[Hard-Gate] FATAL: Failed to verify {file_path} after {self.max_retries} attempts. Pipeline Halted.")
        return False, "Compilation / Semantic validation blocked."
