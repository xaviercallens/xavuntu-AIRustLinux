#!/usr/bin/env python3
"""Verify a release's claims against the diff it actually ships. Card P6-7.

This exists because of a specific, documented failure. Release v12.4.0 was cut,
merged to `main` and tagged with a CHANGELOG asserting that cards P1-1 through
P4-1 had "landed" and that `antigravity_guard.py`, `test_rigor_guard.py` and
`pytest tests/` all passed. None of it was true of that release: the card commits
lived only on an unmerged branch, and all three gates were failing. See
`docs/remediation/AUDIT_2026-09-26.md` section 0.

The root cause was procedural, not technical -- the release notes were written
from intent rather than from the diff, and nothing checked them. This script is
that check.

Two independent verifications:

  1. **Claim -> diff.** Every card id mentioned in the release notes must
     correspond to a file that the release's actual diff touches. A note that
     says "P4-1 landed" while the diff contains nothing related is a fabricated
     claim and fails the gate.
  2. **Gate honesty.** If the notes assert a gate passes, this runs that gate and
     compares. Claiming a passing gate that exits nonzero fails.

Exit code is nonzero on any failure, so this belongs in front of `git tag`.

Usage:
    scripts/verify_release.py --base origin/main --head HEAD --notes CHANGELOG.md
    scripts/verify_release.py --base v12.4.0 --head HEAD --notes /tmp/notes.md --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CARD_PATTERN = re.compile(r"\bP[0-6]-\d{1,2}\b")

# A claim that a named gate passes. Maps the phrase to the command that settles it.
GATE_COMMANDS: dict[str, list[str]] = {
    "antigravity_guard.py": [".venv/bin/python", "antigravity_guard.py"],
    "test_rigor_guard.py": [".venv/bin/python", "test_rigor_guard.py"],
}

# Phrases that turn a gate mention into an assertion that it PASSES. A note that
# merely says a gate "fails" or "is failing" is honest and must not be flagged.
PASS_WORDS = ("pass", "passes", "passing", "green", "all gates", "✅")
FAIL_WORDS = ("fail", "fails", "failing", "exits 1", "exit 1", "nonzero", "❌")

# Phrases that mark a card mention as a DISCLOSED GAP rather than a completion
# claim. "P4-5 does not exist" and "P1-3 is not implemented" describe the absence
# of work, honestly, in the same voice this project uses to report a failing test.
# Demanding diff evidence for those sentences penalises exactly the disclosure this
# gate exists to reward -- found the hard way, when this gate blocked its own
# release notes' "Known issues, stated rather than hidden" section for naming a
# card that a nearby sentence explicitly said does not exist.
NEGATION_WORDS = (
    "does not exist", "doesn't exist", "not implemented", "not yet implemented",
    "no implementation", "not done", "never landed", "remains unmerged",
    "still unmerged", "not merged", "is missing", "blocked", "unimplemented",
)


@dataclass
class Finding:
    kind: str
    detail: str
    severity: str = "fail"


@dataclass
class Report:
    base: str
    head: str
    files_changed: int = 0
    cards_claimed: list[str] = field(default_factory=list)
    cards_unsupported: list[str] = field(default_factory=list)
    gates_checked: dict[str, int] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "fail" for f in self.findings)


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def changed_files(base: str, head: str) -> list[str]:
    return [p for p in git("diff", "--name-only", f"{base}...{head}").splitlines() if p]


def card_is_supported(card: str, files: list[str], base: str, head: str) -> bool:
    """A card claim is supported if the diff plausibly implements it.

    Two ways to qualify: a changed path names the card (e.g. a test file added
    for it), or a commit subject in the range names it AND that commit touched
    at least one file also present in the range's diff.
    """
    needle = card.lower()
    if any(needle in path.lower() for path in files):
        return True

    log = git("log", "--format=%H %s", f"{base}..{head}")
    for line in log.splitlines():
        sha, _, subject = line.partition(" ")
        if card not in subject:
            continue
        touched = [
            p
            for p in git("show", "--name-only", "--format=", sha).splitlines()
            if p.strip()
        ]
        if any(p in files for p in touched):
            return True
    return False


def claims_gate_passes(notes: str, gate: str) -> bool:
    """True only if a line mentioning the gate also asserts success."""
    for raw in notes.splitlines():
        line = raw.lower()
        if gate.lower() not in line:
            continue
        if any(w in line for w in FAIL_WORDS):
            continue  # the note is reporting a failure -- honest, not a claim
        if any(w in line for w in PASS_WORDS):
            return True
    return False


def run_gate(command: list[str]) -> int:
    proc = subprocess.run(
        command, cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=900
    )
    return proc.returncode


def verify(base: str, head: str, notes_path: Path, run_gates: bool) -> Report:
    notes = notes_path.read_text(encoding="utf-8")
    files = changed_files(base, head)
    report = Report(base=base, head=head, files_changed=len(files))

    # 1. Card claims must be backed by the diff -- unless the note discloses the
    # card as NOT done, which needs no evidence because it claims nothing.
    report.cards_claimed = sorted(set(CARD_PATTERN.findall(notes)))
    card_lines = {
        card: [ln for ln in notes.splitlines() if card in ln]
        for card in report.cards_claimed
    }
    for card in report.cards_claimed:
        if any(w in ln.lower() for ln in card_lines[card] for w in NEGATION_WORDS):
            continue
        if not card_is_supported(card, files, base, head):
            report.cards_unsupported.append(card)
            report.findings.append(
                Finding(
                    "unsupported_card_claim",
                    f"{card} is named in the release notes but nothing in "
                    f"{base}...{head} implements it",
                )
            )

    # 2. Gate claims must match reality.
    if run_gates:
        for gate, command in GATE_COMMANDS.items():
            if not claims_gate_passes(notes, gate):
                continue
            code = run_gate(command)
            report.gates_checked[gate] = code
            if code != 0:
                report.findings.append(
                    Finding(
                        "false_gate_claim",
                        f"notes claim {gate} passes, but it exited {code}",
                    )
                )

    if not files:
        report.findings.append(
            Finding("empty_release", f"{base}...{head} changes no files")
        )

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="e.g. origin/main or a previous tag")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--notes", required=True, type=Path)
    parser.add_argument(
        "--skip-gates", action="store_true", help="do not execute gate commands"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = verify(args.base, args.head, args.notes, run_gates=not args.skip_gates)

    if args.json:
        print(
            json.dumps(
                {
                    "base": report.base,
                    "head": report.head,
                    "files_changed": report.files_changed,
                    "cards_claimed": report.cards_claimed,
                    "cards_unsupported": report.cards_unsupported,
                    "gates_checked": report.gates_checked,
                    "findings": [
                        {"kind": f.kind, "detail": f.detail, "severity": f.severity}
                        for f in report.findings
                    ],
                    "ok": report.ok,
                },
                indent=2,
            )
        )
    else:
        print(f"release range : {report.base}...{report.head}")
        print(f"files changed : {report.files_changed}")
        print(
            f"cards claimed : {len(report.cards_claimed)}"
            + (f"  {', '.join(report.cards_claimed)}" if report.cards_claimed else "")
        )
        for gate, code in report.gates_checked.items():
            print(f"gate          : {gate} exited {code}")
        if report.findings:
            print("\nFINDINGS:")
            for f in report.findings:
                print(f"  [{f.severity}] {f.kind}: {f.detail}")
        print(
            "\nRESULT: "
            + ("OK — every claim is backed by the diff" if report.ok else "BLOCKED")
        )

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
