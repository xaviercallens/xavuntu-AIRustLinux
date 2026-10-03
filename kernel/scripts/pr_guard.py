#!/usr/bin/env python3
"""PR-level anti-hallucination gate for contributions (human or AI agent).

Runs on every pull request without secrets, so it is safe for forks. It checks
the whole PR diff (merge-base...HEAD):

  1. No escape hatches added: `sorry`, `axiom`, `admit`, `native_decide` in
     .lean files; `allow(...)`, `#[ignore]`, `todo!`, `unimplemented!`,
     `unreachable_unchecked` in .rs files.
  2. No Lean theorem statement changed or deleted. A proof may change; what is
     being proven may not, unless a maintainer applies the `spec-change` label.
  3. Every `unsafe {` block added in a .rs file has a `// SAFETY:` comment in
     the 5 lines above it.

Maintainers can pass --allow spec-change (theorem statements) or
--allow escape-hatch (item 1) when a PR carries the matching label.

Usage: scripts/pr_guard.py [--base origin/main] [--allow spec-change] [--allow escape-hatch]
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lean_tools import analyze_file, strip_block_comments  # noqa: E402

LEAN_PATTERNS = [(re.compile(r"\bsorry\b"), "sorry"), (re.compile(r"^\s*axiom\s"), "axiom"),
                 (re.compile(r"\badmit\b"), "admit"), (re.compile(r"\bnative_decide\b"), "native_decide")]
RUST_PATTERNS = [(re.compile(r"\ballow\s*\("), "allow(...)"), (re.compile(r"#\[ignore\]"), "#[ignore]"),
                 (re.compile(r"\btodo!\s*\("), "todo!()"), (re.compile(r"\bunimplemented!\s*\("), "unimplemented!()"),
                 (re.compile(r"unreachable_unchecked"), "unreachable_unchecked")]
UNSAFE_RE = re.compile(r"unsafe\s*\{")


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout


def added_lines(base: str, path: str) -> list[tuple[int, str]]:
    """(new_line_number, text) for each added line in `path`."""
    out, ln = [], 0
    for line in git("diff", "-U0", f"{base}...HEAD", "--", path).splitlines():
        m = re.match(r"^@@ -\S+ \+(\d+)", line)
        if m:
            ln = int(m.group(1))
            continue
        if line.startswith("+") and not line.startswith("+++"):
            out.append((ln, line[1:]))
            ln += 1
    return out


def lean_statements(rev: str, path: str) -> dict[str, str]:
    try:
        text = git("show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return {}
    with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False) as f:
        f.write(text)
    try:
        return {t.name: t.statement_hash for t in analyze_file(Path(f.name)).theorems}
    finally:
        os.unlink(f.name)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--allow", action="append", default=[], choices=["spec-change", "escape-hatch"])
    args = ap.parse_args()

    base = git("merge-base", args.base, "HEAD").strip()
    changed = [p for p in git("diff", "--name-only", "--diff-filter=AMDR", f"{base}...HEAD").split() if p]
    problems: list[str] = []

    for path in changed:
        if path.endswith(".lean"):
            if "escape-hatch" not in args.allow and (REPO_ROOT / path).exists():
                # Match against comment-stripped lines: a raw grep false-positived on a
                # `/- ... -/` docstring mentioning `sorry` (same bug class as verify_specs.sh).
                code = strip_block_comments((REPO_ROOT / path).read_text(encoding="utf-8", errors="replace").split("\n"))
                for ln, _ in added_lines(base, path):
                    text = code[ln - 1].split("--", 1)[0] if ln - 1 < len(code) else ""
                    for pat, name in LEAN_PATTERNS:
                        if pat.search(text):
                            problems.append(f"{path}:{ln}: adds `{name}`")
            if "spec-change" not in args.allow:
                before, after = lean_statements(base, path), lean_statements("HEAD", path)
                for name, h in before.items():
                    if name not in after:
                        problems.append(f"{path}: theorem `{name}` was deleted")
                    elif after[name] != h:
                        problems.append(f"{path}: statement of `{name}` changed (only its proof may change)")
        elif path.endswith(".rs"):
            added = added_lines(base, path)
            if "escape-hatch" not in args.allow:
                for ln, text in added:
                    if text.strip().startswith("//"):
                        continue
                    for pat, name in RUST_PATTERNS:
                        if pat.search(text):
                            problems.append(f"{path}:{ln}: adds `{name}`")
            if any(UNSAFE_RE.search(t) for _, t in added) and (REPO_ROOT / path).exists():
                head_lines = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace").split("\n")
                for ln, text in added:
                    if UNSAFE_RE.search(text) and "SAFETY:" not in "\n".join(head_lines[max(0, ln - 6):ln - 1]):
                        problems.append(f"{path}:{ln}: new `unsafe` block without a preceding `// SAFETY:` comment")

    report = ["## pr_guard", f"Base `{base[:12]}`, {len(changed)} changed file(s)."]
    report += ["", "**FAIL**", *[f"- {p}" for p in problems]] if problems else ["", "**PASS**: no escape hatches, no statement changes, every new `unsafe` justified."]
    text = "\n".join(report)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(text + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
