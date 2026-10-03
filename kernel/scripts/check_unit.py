#!/usr/bin/env python3
"""Oracle + anti-cheat gate for a single work unit (see
docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md section 4.2).

Every unit produced by scripts/units/generate.py must pass this check
before its PR is allowed to merge. It does two things:

1. Anti-cheat: diff the working tree against a base ref and reject the
   change if it touches files outside the unit's declared scope, or if it
   introduces any of the forbidden patterns (new sorry/axiom/allow/etc.),
   or -- for lean_sorry units -- if it changes what the theorem states
   rather than just how it is proved.

2. Oracle: a type-specific correctness check (Lean type-checks, crate
   builds/tests, etc.).

This script intentionally has no third-party dependencies (stdlib only)
so it runs the same way in CI and in a low-tier-model sandbox.

Usage:
    scripts/check_unit.py --type lean_sorry --file specs/lean4/MVK/Phase4/ARP.lean \
        --theorem arp_reply_matches_request [--base origin/main]

    scripts/check_unit.py --type unsafe_safety --file crates/foo/src/lib.rs --crate foo
    scripts/check_unit.py --type static_mut    --file crates/foo/src/lib.rs --crate foo
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lean_tools import analyze_file as lean_analyze_file  # noqa: E402

FORBIDDEN_ADDED_PATTERNS = [
    (re.compile(r"^\+\s*.*\bsorry\b"), "introduces `sorry`"),
    (re.compile(r"^\+\s*axiom\s"), "introduces a new `axiom`"),
    (re.compile(r"^\+.*\ballow\("), "adds a new `allow(...)` lint suppression"),
    (re.compile(r"^\+.*#\[ignore\]"), "adds `#[ignore]` to a test"),
    (re.compile(r"^\+.*\btodo!\("), "adds `todo!()`"),
    (re.compile(r"^\+.*\bunimplemented!\("), "adds `unimplemented!()`"),
    (re.compile(r"^\+.*unreachable_unchecked"), "adds `unreachable_unchecked`"),
    (re.compile(r"^\+.*\bnative_decide\b"), "adds `native_decide` (bypasses kernel checking)"),
    (re.compile(r"^\+.*\badmit\b"), "adds `admit`"),
]


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd or REPO_ROOT, capture_output=True, text=True)


def git_diff(base: str, paths: list[str]) -> str:
    result = run(["git", "diff", f"{base}...HEAD", "--"] + paths)
    return result.stdout


def changed_files(base: str) -> list[str]:
    result = run(["git", "diff", "--name-only", f"{base}...HEAD"])
    return [l for l in result.stdout.splitlines() if l.strip()]


def check_scope(base: str, allowed: list[str]) -> list[str]:
    errors = []
    touched = changed_files(base)
    allowed_set = set(allowed)
    for f in touched:
        if f not in allowed_set:
            errors.append(f"touches out-of-scope file: {f} (allowed: {allowed})")
    return errors


def check_forbidden_patterns(base: str, paths: list[str]) -> list[str]:
    errors = []
    diff = git_diff(base, paths)
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for pattern, msg in FORBIDDEN_ADDED_PATTERNS:
            if pattern.match(line):
                errors.append(f"{msg}: {line.strip()[:120]}")
    return errors


def check_lean_sorry(args: argparse.Namespace) -> tuple[bool, list[str]]:
    errors = []
    file_path = REPO_ROOT / args.file
    if not file_path.exists():
        return False, [f"file not found: {args.file}"]

    scope_errors = check_scope(args.base, [args.file])
    errors.extend(scope_errors)

    fs = lean_analyze_file(file_path)
    target = next((t for t in fs.theorems if t.name == args.theorem), None)
    if target is None:
        errors.append(f"theorem `{args.theorem}` not found in {args.file} after edit")
    elif target.has_sorry:
        errors.append(f"theorem `{args.theorem}` still contains `sorry`")

    forbidden = check_forbidden_patterns(args.base, [args.file])
    errors.extend(forbidden)

    if target is not None and args.expect_hash and target.statement_hash != args.expect_hash:
        errors.append(
            f"theorem statement changed (hash {args.expect_hash} -> "
            f"{target.statement_hash}). Only the proof body may change "
            f"for a lean_sorry unit; if the statement itself was wrong, "
            f"escalate to T3 with the `spec-change` tag instead."
        )

    if not errors:
        lean_root = REPO_ROOT / "specs" / "lean4"
        rel = file_path.relative_to(lean_root)
        proc = run(["lake", "env", "lean", str(rel)], cwd=lean_root)
        if proc.returncode != 0:
            errors.append(f"`lake env lean {rel}` failed:\n{proc.stdout}\n{proc.stderr}")

    return (len(errors) == 0), errors


def _check_files_exist(files: list[str]) -> list[str]:
    return [f"file not found: {f}" for f in files if not (REPO_ROOT / f).exists()]


def check_unsafe_safety(args: argparse.Namespace) -> tuple[bool, list[str]]:
    errors = _check_files_exist(args.files)
    if errors:
        return False, errors
    errors.extend(check_scope(args.base, args.files))
    errors.extend(check_forbidden_patterns(args.base, args.files))

    for f in args.files:
        lines = (REPO_ROOT / f).read_text(encoding="utf-8", errors="replace").split("\n")
        for i, line in enumerate(lines):
            if not re.search(r"unsafe\s*\{", line):
                continue
            window = "\n".join(lines[max(0, i - 5):i])
            if "SAFETY:" not in window:
                errors.append(f"unsafe block at {f}:{i + 1} still lacks a preceding SAFETY: comment")

    if not errors and args.crate:
        proc = run(["cargo", "check", "-p", args.crate])
        if proc.returncode != 0:
            errors.append(f"`cargo check -p {args.crate}` failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")

    return (len(errors) == 0), errors


def check_static_mut(args: argparse.Namespace) -> tuple[bool, list[str]]:
    errors = _check_files_exist(args.files)
    if errors:
        return False, errors
    errors.extend(check_scope(args.base, args.files))
    errors.extend(check_forbidden_patterns(args.base, args.files))

    for f in args.files:
        if re.search(r"\bstatic\s+mut\b", (REPO_ROOT / f).read_text(encoding="utf-8", errors="replace")):
            errors.append(f"{f} still contains `static mut`")

    if not errors and args.crate:
        proc = run(["cargo", "test", "--lib", "-p", args.crate])
        if proc.returncode != 0:
            errors.append(f"`cargo test --lib -p {args.crate}` failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")

    return (len(errors) == 0), errors


CHECKERS = {
    "lean_sorry": check_lean_sorry,
    "unsafe_safety": check_unsafe_safety,
    "static_mut": check_static_mut,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--type", required=True, choices=sorted(CHECKERS))
    parser.add_argument("--file", dest="files", action="append", required=True,
                        help="repo-relative path to an edited file; repeatable for unsafe_safety/static_mut "
                             "so one unit can cover a whole crate (scope = exactly these files)")
    parser.add_argument("--theorem", help="theorem/lemma name (lean_sorry units)")
    parser.add_argument("--crate", help="crate name (unsafe_safety / static_mut units)")
    parser.add_argument("--expect-hash", help="expected theorem statement hash, to detect silent weakening")
    parser.add_argument("--base", default="origin/main", help="base ref to diff against")
    args = parser.parse_args()

    if args.type == "lean_sorry":
        if not args.theorem:
            parser.error("--theorem is required for --type lean_sorry")
        if len(args.files) != 1:
            parser.error("--type lean_sorry takes exactly one --file")
    args.file = args.files[0]

    ok, errors = CHECKERS[args.type](args)
    if ok:
        print(f"PASS: {args.type} unit for {', '.join(args.files)} ({args.theorem or args.crate})")
        return 0

    print(f"FAIL: {args.type} unit for {', '.join(args.files)}", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
