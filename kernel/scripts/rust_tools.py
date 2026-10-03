#!/usr/bin/env python3
"""Shared static-analysis helpers for the crates/ workspace.

Text-based heuristics only (no cargo/rustc invocation), so these run fast
and without a toolchain. That is a deliberate tradeoff: metrics.py is meant
to run on every PR as a cheap ratchet gate; a heavier `--with-build` mode
(real `cargo check`/`clippy`/`miri` numbers) is left for a follow-up, see
docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md WS3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

STUB_MARKER_RE = re.compile(r"\b(stub|TODO|FIXME|simplified|placeholder|not implemented)\b", re.IGNORECASE)
BLANKET_CLIPPY_ALLOW_RE = re.compile(r"allow\(clippy::all")
LAX_ALLOW_RE = re.compile(r"allow\((warnings|dead_code|unused)")
UNSAFE_BLOCK_RE = re.compile(r"unsafe\s*\{")
UNSAFE_FN_RE = re.compile(r"unsafe\s+(extern\s+\"[^\"]+\"\s+)?fn\b")
SAFETY_COMMENT_RE = re.compile(r"SAFETY:")
STATIC_MUT_RE = re.compile(r"\bstatic\s+mut\b")
TEST_ATTR_RE = re.compile(r"#\[test\]")
# Constant-body extern "C" fn: `... fn name(...) [-> T] { <single constant expr> }`
CONST_STUB_FN_RE = re.compile(
    r'extern\s+"C"\s+fn\s+\w+\s*\([^)]*\)\s*(->\s*[^{]+)?\{\s*'
    r"(0|-1|true|false|ptr::null_mut\(\)|core::ptr::null_mut\(\))\s*\}"
)


@dataclass
class CrateStats:
    name: str
    path: Path
    loc: int = 0
    tests: int = 0
    unsafe_blocks: int = 0
    unsafe_fns: int = 0
    safety_comments: int = 0
    static_mut: int = 0
    stub_marker_lines: int = 0
    const_stub_fns: int = 0
    blanket_clippy_allow: bool = False
    lax_allow: bool = False
    rs_files: list[Path] = field(default_factory=list)


def discover_crates(crates_root: Path) -> list[Path]:
    return sorted(p.parent for p in crates_root.glob("*/Cargo.toml"))


def analyze_crate(crate_dir: Path) -> CrateStats:
    name = crate_dir.name
    stats = CrateStats(name=name, path=crate_dir)
    rs_files = sorted(crate_dir.rglob("*.rs"))
    stats.rs_files = rs_files
    all_text = []
    for f in rs_files:
        text = f.read_text(encoding="utf-8", errors="replace")
        all_text.append(text)
        stats.loc += text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        stats.tests += len(TEST_ATTR_RE.findall(text))
        stats.unsafe_blocks += len(UNSAFE_BLOCK_RE.findall(text))
        stats.unsafe_fns += len(UNSAFE_FN_RE.findall(text))
        stats.safety_comments += len(SAFETY_COMMENT_RE.findall(text))
        stats.static_mut += len(STATIC_MUT_RE.findall(text))
        stats.const_stub_fns += len(CONST_STUB_FN_RE.findall(text))
        for line in text.split("\n"):
            if not line.strip().startswith("//") and STUB_MARKER_RE.search(line):
                stats.stub_marker_lines += 1
            elif line.strip().startswith("//") and STUB_MARKER_RE.search(line):
                stats.stub_marker_lines += 1
    joined = "\n".join(all_text)
    stats.blanket_clippy_allow = bool(BLANKET_CLIPPY_ALLOW_RE.search(joined))
    stats.lax_allow = bool(LAX_ALLOW_RE.search(joined))
    return stats


def analyze_workspace(crates_root: Path) -> list[CrateStats]:
    return [analyze_crate(c) for c in discover_crates(crates_root)]
