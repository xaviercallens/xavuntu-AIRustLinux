"""
Code-block parser: extract Python code from raw LLM output.

Supports:
  - Fenced code blocks: ```python ... ```
  - Bare triple-backtick blocks: ``` ... ```
  - Indented code (fallback)
  - Strips common LLM preamble like "Here is the code:"
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass

def check_complexity_floor(code: str, min_complexity: int = 3) -> bool:
    """Check if the cyclomatic complexity (branch count) of the code is at least min_complexity."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
        
    branches = sum(1 for node in ast.walk(tree)
                   if isinstance(node, (ast.If, ast.For, ast.While,
                                        ast.ExceptHandler, ast.With, ast.Assert)))
    return branches >= min_complexity

# ─── Output types ────────────────────────────────────────────────────────────


@dataclass
class ParseResult:
    code: str
    """The extracted Python source code."""

    confidence: float
    """0.0–1.0 confidence that the extracted block is complete, valid Python."""

    raw: str
    """The original unmodified LLM output."""

    extraction_method: str
    """Which extraction strategy was used (for debugging / logging)."""


# ─── Patterns ────────────────────────────────────────────────────────────────

# Match ```python ... ``` (greedy, DOTALL)
_FENCED_PYTHON_RE = re.compile(
    r"```python\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)

# Match ``` ... ``` (no language specified)
_FENCED_GENERIC_RE = re.compile(
    r"```\s*\n(.*?)```",
    re.DOTALL,
)

# Match a line that looks like the start of a def or class (fallback)
_CODE_HEURISTIC_RE = re.compile(
    r"^((?:import |from |def |class |#|@|\s{4}|\s{2}(?!$)).*)",
    re.MULTILINE,
)


# ─── Public API ──────────────────────────────────────────────────────────────


def extract_code(text: str) -> ParseResult:
    """
    Extract the first Python code block from *text*.

    Tries strategies in order:
      1. Fenced ```python block
      2. Fenced ``` block
      3. Heuristic scan for code-like lines

    Returns a :class:`ParseResult` with the best match found.
    Raises :class:`NoCodeFoundError` if nothing code-like exists.
    """
    text = text.strip()

    # Strategy 1 — explicit python fence
    match = _FENCED_PYTHON_RE.search(text)
    if match:
        code = _clean(match.group(1))
        return ParseResult(
            code=code,
            confidence=0.95,
            raw=text,
            extraction_method="fenced_python",
        )

    # Strategy 2 — generic fence
    match = _FENCED_GENERIC_RE.search(text)
    if match:
        code = _clean(match.group(1))
        return ParseResult(
            code=code,
            confidence=0.75,
            raw=text,
            extraction_method="fenced_generic",
        )

    # Strategy 3 — heuristic code lines
    lines = text.splitlines()
    code_lines = [line for line in lines if _CODE_HEURISTIC_RE.match(line)]
    if code_lines:
        code = _clean("\n".join(code_lines))
        return ParseResult(
            code=code,
            confidence=0.40,
            raw=text,
            extraction_method="heuristic",
        )

    raise NoCodeFoundError(
        f"No Python code block found in LLM output.\nRaw text (first 200 chars):\n{text[:200]}"
    )


def extract_all_code_blocks(text: str) -> list[ParseResult]:
    """
    Extract *all* fenced code blocks from *text* (useful when the LLM
    generates multiple functions or a module with several blocks).
    """
    results: list[ParseResult] = []

    for match in _FENCED_PYTHON_RE.finditer(text):
        code = _clean(match.group(1))
        results.append(
            ParseResult(
                code=code,
                confidence=0.95,
                raw=text,
                extraction_method="fenced_python",
            )
        )

    if not results:
        for match in _FENCED_GENERIC_RE.finditer(text):
            code = _clean(match.group(1))
            results.append(
                ParseResult(
                    code=code,
                    confidence=0.75,
                    raw=text,
                    extraction_method="fenced_generic",
                )
            )

    return results


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _clean(code: str) -> str:
    """Strip trailing whitespace and de-dent if the whole block is indented."""
    return textwrap.dedent(code).strip()


class NoCodeFoundError(ValueError):
    """Raised when no Python code can be extracted from LLM output."""
