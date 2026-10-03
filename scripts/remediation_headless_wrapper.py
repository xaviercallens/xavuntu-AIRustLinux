#!/usr/bin/env python3
"""
Headless Claude invocation for remediation cards.

Every flag used here was verified against `claude --help` on version 2.1.282
and by a live invocation. Two flags an earlier draft of this file used do NOT
exist or do not work, and must not be reintroduced:

  --max-turns          : not a Claude Code flag (absent from --help).
  --model claude-haiku-4b : rejected with [claude-code:unrecognized_model].

Model ids below are the verified ones. `claude-haiku-4-5-20251001` returned a
real completion; a trivial prompt cost $0.0258 including cache creation, so
treat per-card cost as measured-at-runtime, never as an estimate baked into
a document.

This module only RUNS the model. It never decides whether a card passed --
that is the driver's job, via the card's `accept` commands. See
night_phase_runner.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Verified model ids. `claude --model <id>` rejects anything else with
# [claude-code:unrecognized_model], which surfaces as a non-zero exit.
MODEL_BY_TIER: dict[str, str] = {
    "low": "claude-haiku-4-5-20251001",
    "mid": "claude-sonnet-5",
}
FALLBACK_MODEL = "claude-sonnet-5"

# Tools a card-executing agent needs. Deliberately excludes WebFetch/WebSearch:
# a remediation card is repo-local work and should not reach the network.
ALLOWED_TOOLS = "Read,Edit,Write,Bash,Grep,Glob"


class HeadlessError(RuntimeError):
    """Raised when the CLI could not be invoked at all."""


@dataclass(frozen=True)
class HeadlessResult:
    """Outcome of one `claude -p` invocation. Says nothing about card success."""

    exit_code: int
    session_id: str | None
    cost_usd: float
    output_text: str
    error: str | None
    num_turns: int | None
    permission_denials: int


def model_for_tier(tier: str) -> str:
    """Model id for a tier. Human-tier cards are never executed by a model."""
    try:
        return MODEL_BY_TIER[tier]
    except KeyError:
        raise ValueError(
            f"tier {tier!r} is not model-executable; expected one of {sorted(MODEL_BY_TIER)}"
        ) from None


def build_command(tier: str, max_budget_usd: float, cwd: Path) -> list[str]:
    """Assemble the argv. Kept separate so tests can assert on it."""
    exe = shutil.which("claude")
    if exe is None:
        raise HeadlessError("`claude` is not on PATH")
    return [
        exe,
        "-p",
        "--model",
        model_for_tier(tier),
        "--fallback-model",
        FALLBACK_MODEL,
        "--output-format",
        "json",
        # dontAsk: auto-approves read-only work and the allowlist, denies the
        # rest. Never bypassPermissions -- an unattended agent must not be able
        # to approve arbitrary shell for itself.
        "--permission-mode",
        "dontAsk",
        # No human is present overnight; a prompt must deny, not hang.
        "--permission-prompts",
        "none",
        "--allowedTools",
        ALLOWED_TOOLS,
        "--max-budget-usd",
        f"{max_budget_usd:.2f}",
        "--add-dir",
        str(cwd),
    ]


def _parse_payload(stdout: str) -> dict[str, Any]:
    """Parse the --output-format json envelope, tolerating trailing noise."""
    stripped = stdout.strip()
    if not stripped:
        return {}
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        # stream-json or a warning line before the object: take the last line
        # that parses as an object.
        for line in reversed(stripped.splitlines()):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                return candidate
        return {}
    return parsed if isinstance(parsed, dict) else {}


def invoke_claude(
    prompt: str,
    tier: str,
    max_budget_usd: float,
    timeout_s: float,
    cwd: Path,
) -> HeadlessResult:
    """Run one headless invocation and report exactly what happened."""
    cmd = build_command(tier, max_budget_usd, cwd)
    try:
        completed = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(cwd),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return HeadlessResult(
            exit_code=124,
            session_id=None,
            cost_usd=0.0,
            output_text="",
            error=f"timed out after {timeout_s:.0f}s",
            num_turns=None,
            permission_denials=0,
        )
    except OSError as exc:
        raise HeadlessError(f"could not launch claude: {exc}") from exc

    payload = _parse_payload(completed.stdout)
    denials = payload.get("permission_denials") or []
    error: str | None = None
    if completed.returncode != 0:
        error = (completed.stderr or "").strip() or f"exit {completed.returncode}"
    elif payload.get("is_error"):
        error = str(payload.get("result", "cli reported is_error"))

    return HeadlessResult(
        exit_code=completed.returncode,
        session_id=payload.get("session_id"),
        cost_usd=float(payload.get("total_cost_usd") or 0.0),
        output_text=str(payload.get("result", completed.stdout)),
        error=error,
        num_turns=payload.get("num_turns"),
        permission_denials=len(denials) if isinstance(denials, list) else 0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one card prompt headlessly.")
    parser.add_argument("--tier", required=True, choices=sorted(MODEL_BY_TIER))
    parser.add_argument("--prompt", default="-", help="prompt text, or - for stdin")
    parser.add_argument("--max-budget-usd", type=float, default=2.0)
    parser.add_argument("--timeout-s", type=float, default=1800.0)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    prompt = sys.stdin.read() if args.prompt == "-" else args.prompt
    result = invoke_claude(
        prompt,
        tier=args.tier,
        max_budget_usd=args.max_budget_usd,
        timeout_s=args.timeout_s,
        cwd=args.cwd,
    )
    json.dump(
        {
            "exit_code": result.exit_code,
            "session_id": result.session_id,
            "cost_usd": result.cost_usd,
            "num_turns": result.num_turns,
            "permission_denials": result.permission_denials,
            "error": result.error,
            "output": result.output_text,
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")
    return result.exit_code


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
