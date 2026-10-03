#!/usr/bin/env python3
"""Shared static-analysis helpers for Lean 4 specs under specs/lean4/MVK.

Used by scripts/metrics.py (aggregate counts) and scripts/check_unit.py
(per-unit oracle for the sorry-elimination workflow). Pure text analysis:
no dependency on the Lean toolchain, so it runs anywhere Python 3 runs.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

SORRY_RE = re.compile(r"\bsorry\b")
AXIOM_RE = re.compile(r"^\s*axiom\s+(\w+)")
THEOREM_RE = re.compile(r"^\s*(theorem|lemma)\s+(\w+)")
COMMENT_LINE_RE = re.compile(r"^\s*--")
BLOCK_COMMENT_OPEN = "/-"
BLOCK_COMMENT_CLOSE = "-/"


def lean_files(root: Path) -> list[Path]:
    return sorted((root / "MVK").rglob("*.lean"))


def strip_block_comments(lines: list[str]) -> list[str]:
    """Best-effort removal of /- ... -/ block comments (not nesting-aware,
    which matches how these specs are written in practice)."""
    out = []
    in_block = False
    for line in lines:
        if in_block:
            if BLOCK_COMMENT_CLOSE in line:
                in_block = False
                line = line.split(BLOCK_COMMENT_CLOSE, 1)[1]
            else:
                out.append("")
                continue
        while BLOCK_COMMENT_OPEN in line:
            before, _, rest = line.partition(BLOCK_COMMENT_OPEN)
            if BLOCK_COMMENT_CLOSE in rest:
                _, _, after = rest.partition(BLOCK_COMMENT_CLOSE)
                line = before + after
            else:
                line = before
                in_block = True
                break
        out.append(line)
    return out


@dataclass
class TheoremRecord:
    file: str
    name: str
    line: int
    statement: str
    statement_hash: str
    has_sorry: bool


@dataclass
class FileStats:
    path: str
    sorry: int = 0
    sorry_lines: list[int] = field(default_factory=list)
    axioms: list[tuple[str, int]] = field(default_factory=list)
    theorems: list[TheoremRecord] = field(default_factory=list)


def _extract_statement(lines: list[str], start_idx: int) -> str:
    """Collect lines from a theorem/lemma header up to (not including) the
    first top-level ':=' that starts a proof, or up to a blank line / next
    declaration if no ':=' is found nearby."""
    buf = []
    for i in range(start_idx, min(start_idx + 40, len(lines))):
        line = lines[i]
        if ":=" in line:
            buf.append(line.split(":=", 1)[0])
            break
        buf.append(line)
    else:
        pass
    text = " ".join(l.strip() for l in buf if l.strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def analyze_file(path: Path) -> FileStats:
    raw_lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    lines = strip_block_comments(raw_lines)
    stats = FileStats(path=str(path))
    for i, line in enumerate(lines):
        if COMMENT_LINE_RE.match(line):
            continue
        if SORRY_RE.search(line):
            stats.sorry += 1
            stats.sorry_lines.append(i + 1)
        m = AXIOM_RE.match(line)
        if m:
            stats.axioms.append((m.group(1), i + 1))
        m = THEOREM_RE.match(line)
        if m:
            name = m.group(2)
            statement = _extract_statement(lines, i)
            digest = hashlib.sha256(statement.encode("utf-8")).hexdigest()[:16]
            window = "\n".join(raw_lines[i:i + 40])
            has_sorry = bool(SORRY_RE.search(window))
            stats.theorems.append(
                TheoremRecord(
                    file=str(path),
                    name=name,
                    line=i + 1,
                    statement=statement,
                    statement_hash=digest,
                    has_sorry=has_sorry,
                )
            )
    return stats


def analyze_tree(root: Path) -> list[FileStats]:
    return [analyze_file(p) for p in lean_files(root)]


def theorem_hash_map(root: Path) -> dict[str, str]:
    """Maps 'relative/path.lean::theorem_name' -> statement hash, for the
    anti-weakening check in check_unit.py."""
    out: dict[str, str] = {}
    for fs in analyze_tree(root):
        rel = str(Path(fs.path).relative_to(root))
        for t in fs.theorems:
            out[f"{rel}::{t.name}"] = t.statement_hash
    return out
