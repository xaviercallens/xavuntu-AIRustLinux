"""Origin policy: which rows may enter a training mix (card N-9).

Rule (docs/v2/README.md ground rule 5): transcript-derived data - what a coding agent said in
a Claude Code or Antigravity session, or rows distilled from those transcripts - is NOT
training data until a human writes ``docs/v2/gates/N8.md`` (card N-8). Until that file
exists such rows are refused. Rows with no ``origin`` at all are refused too: unknown
provenance is not allowed provenance. Everything else (sandbox-verified episodes, logged
LLM calls with a verdict) passes; the dilution cap in ``scripts/ltm_learning_mix.py`` still
bounds the unverified share.

Pure: the only I/O is ``gate_file.exists()``, which the caller injects.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path

NO_TRAIN_ORIGINS: frozenset[str] = frozenset({"claude_code", "antigravity", "transcript"})
REASON_MISSING_ORIGIN = "missing_origin"


def refusal_reason(row: dict, gate_file: Path) -> str | None:
    """Why ``row`` may not be trained on, or ``None`` if it may.

    Reasons: ``missing_origin`` (no / empty ``origin``) and ``gated_origin:<origin>`` (a
    transcript-derived origin while ``gate_file`` does not exist).
    """
    origin = row.get("origin")
    if not isinstance(origin, str) or not origin:
        return REASON_MISSING_ORIGIN
    if origin in NO_TRAIN_ORIGINS and not gate_file.exists():
        return f"gated_origin:{origin}"
    return None


def allowed(row: dict, gate_file: Path) -> bool:
    """True iff ``row`` may enter the training mix under the N-8 gate."""
    return refusal_reason(row, gate_file) is None


def partition(rows: Iterable[dict], gate_file: Path) -> tuple[list[dict], dict[str, int]]:
    """Split rows into the allowed ones and a count of refusals by reason."""
    kept: list[dict] = []
    refused: Counter[str] = Counter()
    for row in rows:
        reason = refusal_reason(row, gate_file)
        if reason is None:
            kept.append(row)
        else:
            refused[reason] += 1
    return kept, dict(sorted(refused.items()))
