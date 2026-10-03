"""GPU discipline: every script that touches the T4 or Ollama must hold the shared lease.

Why (LL.md, gpu_lease.py header): on 2026-09-27 two projects fought over the one T4 and a
prover baseline was killed mid-flight. The fix is a file lock on disk 2
(``/mnt/disks/disk-socrateai-local-1/gpu_lease/gpu_lease.py``) that a runner enters with
``with gpu_lease(holder, purpose, ...):``. The lease is opt-in per script, so nothing stops a
new runner from forgetting it. This module is the mechanical check (card G-1): a pure scan of
the runner directories that names every file which references the GPU or Ollama but never
mentions ``gpu_lease``. ``tests/v2/test_gpu_discipline.py`` asserts the list is empty for
this repository; a new unleased runner fails the suite.

What counts as a GPU/Ollama reference (evaluated on the file's CODE, with comments and
docstrings removed, so prose about the GPU never flags a file):

* the Ollama endpoint ``localhost:11434`` or an ``OLLAMA`` symbol (``OLLAMA_HOST``, an
  ``OLLAMA = "http://..."`` constant);
* the word ``cuda`` (``torch.cuda.is_available()``, ``.to("cuda")``);
* ``torch.device(...)`` with anything but the literal ``"cpu"`` (a CPU pin is by
  definition not GPU use, and several scripts pin the CPU on purpose);
* a model or trainer placed on a runtime-resolved device, ``x.to(profile.device)`` or
  ``Trainer(device=profile.device)`` - the form the nightly dream phase uses, which names
  none of the strings above yet trains on whatever ``resolve_capability_profile`` found;
* launching (by path literal) a ``scripts/`` or ``v2_runners/`` file that itself references
  the GPU - an orchestrator that starts GPU runners is a GPU runner.

Pure over file text: the only I/O is reading the files under ``root``.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

SCAN_DIRS: tuple[str, ...] = ("scripts", "v2_runners")
LEASE_TOKEN = "gpu_lease"

_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("localhost:11434", re.compile(r"localhost:11434")),
    ("OLLAMA", re.compile(r"\bOLLAMA")),
    ("cuda", re.compile(r"\bcuda\b")),
    ("torch.device", re.compile(r"torch\.device\(\s*(?![\"']cpu[\"'])")),
    ("resolved device",
     re.compile(r"\.to\(\s*(?!torch\b)\w+\.device\s*\)|\bdevice\s*=\s*(?!torch\b)\w+\.device\b")),
)
_LAUNCH = re.compile(r"[\"']((?:scripts|v2_runners)/[\w./-]+\.py)[\"']")


def _docstring_positions(source: str) -> set[tuple[int, int]]:
    """(lineno, col_offset) of every docstring node; empty if the file does not parse."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    positions: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            positions.add((body[0].value.lineno, body[0].value.col_offset))
    return positions


def code_text(source: str) -> str:
    """The source with comments and docstrings blanked out (layout preserved).

    A file that cannot be tokenized is returned unchanged: an unparsable runner is judged on
    everything it says, which can only over-report, never hide a GPU reference.
    """
    docstrings = _docstring_positions(source)
    lines = source.splitlines(keepends=True)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, SyntaxError):
        return source
    for tok in tokens:
        drop = tok.type == tokenize.COMMENT or (
            tok.type == tokenize.STRING and (tok.start[0], tok.start[1]) in docstrings
        )
        if not drop:
            continue
        (r1, c1), (r2, c2) = tok.start, tok.end
        for row in range(r1, r2 + 1):
            line = lines[row - 1]
            lo = c1 if row == r1 else 0
            hi = c2 if row == r2 else len(line.rstrip("\r\n"))
            lines[row - 1] = line[:lo] + " " * (hi - lo) + line[hi:]
    return "".join(lines)


def gpu_evidence(code: str) -> list[str]:
    """Names of the GPU/Ollama markers present in ``code`` (already comment-stripped)."""
    return [name for name, pattern in _MARKERS if pattern.search(code)]


def holds_lease(code: str) -> bool:
    """True if the code mentions the lease at all (import or call of ``gpu_lease``)."""
    return LEASE_TOKEN in code


def launched_scripts(code: str) -> list[str]:
    """Repo-relative ``scripts/...py`` / ``v2_runners/...py`` literals the code launches."""
    return sorted(set(_LAUNCH.findall(code)))


def _runner_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for name in SCAN_DIRS:
        base = root / name
        if base.is_dir():
            files.extend(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(files)


def offenders(root: Path) -> list[Path]:
    """Runner files (relative to ``root``) that reference the GPU/Ollama without the lease.

    Includes orchestrators that launch a direct GPU runner without holding the lease.
    """
    codes = {p.relative_to(root): code_text(p.read_text(encoding="utf-8", errors="replace"))
             for p in _runner_files(root)}
    direct = {rel for rel, code in codes.items() if gpu_evidence(code)}
    out: list[Path] = []
    for rel, code in codes.items():
        if holds_lease(code):
            continue
        launches_gpu = any(Path(s) in direct for s in launched_scripts(code))
        if rel in direct or launches_gpu:
            out.append(rel)
    return sorted(out)
