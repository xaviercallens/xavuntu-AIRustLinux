#!/usr/bin/env python3
"""
Overnight driver for the remediation card workflow.

THE INVARIANT: a card is done only when the driver has run every one of its
`accept` commands and all of them exited 0. The model's own exit code, and
anything the model says about its work, are evidence of nothing. An earlier
draft of this file marked cards done on the model's exit code alone and never
ran `accept` at all -- the same self-certification defect the card set exists
to remove (see AUDIT_2026-09-25.md §2).

Nothing here reports success it did not verify. Functions that cannot do their
work raise; none of them return True on a skipped operation.

Human-tier cards are never executed: they carry `accept: []`, so there is
nothing for the driver to verify, and by convention a person runs them.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.remediation_headless_wrapper import (  # noqa: E402
    HeadlessError,
    invoke_claude,
)

logger = logging.getLogger("night_runner")

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = REPO_ROOT / ".night_runner.lock"

# Per-card spend ceilings. These are ceilings, not predictions: actual cost is
# measured per invocation and summed into the run log.
BUDGET_BY_TIER: dict[str, float] = {"low": 1.50, "mid": 4.00}
TIMEOUT_BY_TIER: dict[str, float] = {"low": 1200.0, "mid": 2400.0}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AcceptOutcome:
    command: str
    exit_code: int
    stdout_tail: str
    stderr_tail: str


@dataclass(frozen=True)
class CardOutcome:
    card_id: str
    phase: int
    tier: str
    passed: bool
    reason: str
    model_exit_code: int | None
    session_id: str | None
    cost_usd: float
    accept_results: list[AcceptOutcome]
    committed_sha: str | None
    # A card nobody ran is neither passed nor failed. Without this the dry-run
    # prints "FAIL / 1 failed" for work it deliberately did not attempt --
    # an unverified outcome label, in the tool whose job is to refuse those.
    skipped: bool = False
    timestamp: str = field(default_factory=utc_now)


@dataclass
class RunLog:
    started_at: str = field(default_factory=utc_now)
    ended_at: str | None = None
    total_cost_usd: float = 0.0
    outcomes: list[CardOutcome] = field(default_factory=list)
    aborted_reason: str | None = None

    @property
    def passed(self) -> int:
        return sum(1 for o in self.outcomes if o.passed)

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if not o.passed and not o.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for o in self.outcomes if o.skipped)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "cards": {
                "attempted": len(self.outcomes),
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
            },
            "outcomes": [asdict(o) for o in self.outcomes],
            "aborted_reason": self.aborted_reason,
        }


# ---------------------------------------------------------------- git helpers


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=check,
    )


def working_tree_is_clean() -> bool:
    return not git("status", "--porcelain").stdout.strip()


def head_sha() -> str:
    return git("rev-parse", "HEAD").stdout.strip()


def rollback_to(sha: str) -> None:
    """Discard whatever a failed card left behind.

    Deliberately narrow: reset --hard plus clean of untracked files, both
    scoped to the repo. This is destructive by design and only ever runs on a
    tree the driver itself checkpointed one card earlier.
    """
    git("reset", "--hard", sha)
    git("clean", "-fd")


# ------------------------------------------------------------- card rendering


def render_card(card: dict[str, Any], rules: list[str]) -> str:
    """The full prompt a card-executing model sees. Mirrors v2_tasks.render()."""
    lines: list[str] = ["RULES (apply to every card):"]
    lines += [f"  - {r}" for r in rules]
    lines.append("")
    lines.append(
        f"CARD {card['id']}: {card['title']} "
        f"[tier={card['tier']}, phase={card['phase']}]"
    )
    for key, label in (
        ("read_first", "READ FIRST"),
        ("create", "CREATE"),
        ("edit", "EDIT"),
    ):
        if card.get(key):
            lines.append(f"{label}: {', '.join(card[key])}")
    lines.append("")
    lines.append("SPEC:")
    lines += [f"  - {s}" for s in card.get("spec", [])]
    if card.get("tests"):
        lines.append("")
        lines.append("TESTS:")
        lines += [f"  - {t}" for t in card["tests"]]
    lines.append("")
    lines.append("ACCEPT (the driver runs these after you finish; all must exit 0):")
    lines += [f"  $ {a}" for a in card.get("accept", [])]
    lines.append("")
    lines.append(
        "Implement the card now. Do not edit the accept commands, the card file, "
        "or any test in order to make a check pass. If the card's premise is "
        "false against the current code, stop and say so instead of adapting it."
    )
    return "\n".join(lines)


# --------------------------------------------------------------- verification


def run_accept(card: dict[str, Any], timeout_s: float = 900.0) -> list[AcceptOutcome]:
    """Execute a card's accept commands. This is the only source of truth."""
    outcomes: list[AcceptOutcome] = []
    for command in card.get("accept", []):
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            outcomes.append(
                AcceptOutcome(
                    command=command,
                    exit_code=proc.returncode,
                    stdout_tail=proc.stdout[-2000:],
                    stderr_tail=proc.stderr[-2000:],
                )
            )
        except subprocess.TimeoutExpired:
            outcomes.append(
                AcceptOutcome(
                    command=command,
                    exit_code=124,
                    stdout_tail="",
                    stderr_tail=f"accept command timed out after {timeout_s:.0f}s",
                )
            )
        if outcomes[-1].exit_code != 0:
            break  # first failure is enough; the card is not done
    return outcomes


# ------------------------------------------------------------------ execution


def execute_card(card: dict[str, Any], rules: list[str], dry_run: bool) -> CardOutcome:
    """Run one card end to end: checkpoint, model, verify, commit or roll back."""
    card_id, tier, phase = card["id"], card["tier"], card["phase"]

    if not card.get("accept"):
        return CardOutcome(
            card_id=card_id,
            phase=phase,
            tier=tier,
            passed=False,
            reason="human-tier card: no accept commands for the driver to verify",
            skipped=True,
            model_exit_code=None,
            session_id=None,
            cost_usd=0.0,
            accept_results=[],
            committed_sha=None,
        )

    if dry_run:
        return CardOutcome(
            card_id=card_id,
            phase=phase,
            tier=tier,
            passed=False,
            reason="dry-run: not executed",
            skipped=True,
            model_exit_code=None,
            session_id=None,
            cost_usd=0.0,
            accept_results=[],
            committed_sha=None,
        )

    checkpoint = head_sha()
    prompt = render_card(card, rules)

    try:
        result = invoke_claude(
            prompt,
            tier=tier,
            max_budget_usd=BUDGET_BY_TIER[tier],
            timeout_s=TIMEOUT_BY_TIER[tier],
            cwd=REPO_ROOT,
        )
    except (HeadlessError, ValueError) as exc:
        return CardOutcome(
            card_id=card_id,
            phase=phase,
            tier=tier,
            passed=False,
            reason=f"could not invoke model: {exc}",
            model_exit_code=None,
            session_id=None,
            cost_usd=0.0,
            accept_results=[],
            committed_sha=None,
        )

    # The model's exit code decides nothing. Run accept regardless -- a model
    # that errored may still have left a correct tree, and one that exited 0
    # routinely has not.
    accept_results = run_accept(card)
    all_passed = bool(accept_results) and all(a.exit_code == 0 for a in accept_results)

    committed: str | None = None
    if all_passed:
        if working_tree_is_clean():
            reason = "accept passed (card made no changes)"
        else:
            git("add", "-A")
            git(
                "commit",
                "-m",
                f"{card_id}: {card['title']}\n\n"
                f"Executed by night_phase_runner ({tier} tier).\n"
                f"All {len(accept_results)} accept command(s) exited 0.\n"
                f"session={result.session_id} cost=${result.cost_usd:.4f}\n\n"
                "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>",
            )
            committed = head_sha()
            reason = "accept passed"
    else:
        failed = next((a for a in accept_results if a.exit_code != 0), None)
        reason = (
            f"accept failed: {failed.command} -> exit {failed.exit_code}"
            if failed
            else "no accept commands ran"
        )
        rollback_to(checkpoint)

    return CardOutcome(
        card_id=card_id,
        phase=phase,
        tier=tier,
        passed=all_passed,
        reason=reason,
        model_exit_code=result.exit_code,
        session_id=result.session_id,
        cost_usd=result.cost_usd,
        accept_results=accept_results,
        committed_sha=committed,
    )


# -------------------------------------------------------------- orchestration


def ready_cards(cards: list[dict[str, Any]], done: set[str]) -> list[dict[str, Any]]:
    """Cards not yet done whose dependencies are all done, in phase order.

    Dependencies are honoured across phases, so a phase-0 card blocked on a
    phase-5 card simply waits rather than being silently skipped.
    """
    pending = [c for c in cards if c["id"] not in done]
    return sorted(
        (c for c in pending if all(d in done for d in c.get("depends_on", []))),
        key=lambda c: (c["phase"], c["id"]),
    )


def run(
    tasks_path: Path,
    status_path: Path,
    log_dir: Path,
    only_phase: int | None,
    max_cards: int | None,
    budget_ceiling: float,
    dry_run: bool,
) -> RunLog:
    doc = yaml.safe_load(tasks_path.read_text())
    cards: list[dict[str, Any]] = doc["cards"]
    rules: list[str] = doc.get("rules", [])

    done: set[str] = set()
    if status_path.exists():
        done = set(json.loads(status_path.read_text()).get("done", []))

    log = RunLog()

    if not dry_run and not working_tree_is_clean():
        log.aborted_reason = (
            "working tree is dirty; refusing to start. The driver commits and "
            "rolls back per card and cannot distinguish your edits from a card's."
        )
        logger.error(log.aborted_reason)
        return log

    while True:
        if max_cards is not None and len(log.outcomes) >= max_cards:
            break
        if log.total_cost_usd >= budget_ceiling:
            log.aborted_reason = (
                f"run budget ceiling ${budget_ceiling:.2f} reached "
                f"(spent ${log.total_cost_usd:.2f})"
            )
            logger.warning(log.aborted_reason)
            break

        queue = ready_cards(cards, done)
        if only_phase is not None:
            queue = [c for c in queue if c["phase"] == only_phase]
        # Human-tier cards can never be completed here; skip them so they do
        # not wedge the queue.
        queue = [c for c in queue if c.get("accept")]
        if not queue:
            break

        card = queue[0]
        logger.info("-> %s [%s] %s", card["id"], card["tier"], card["title"])
        outcome = execute_card(card, rules, dry_run)
        log.outcomes.append(outcome)
        log.total_cost_usd += outcome.cost_usd

        if outcome.passed:
            done.add(card["id"])
            if not dry_run:
                status_path.parent.mkdir(parents=True, exist_ok=True)
                status_path.write_text(
                    json.dumps({"done": sorted(done)}, indent=2) + "\n"
                )
                # Fold the bookkeeping into the card's own commit. Without this
                # the runner leaves status.json modified, and since it refuses
                # to start on a dirty tree it would abort every subsequent
                # night -- a scheduler that runs exactly once.
                git("add", str(status_path))
                if outcome.committed_sha is not None:
                    git("commit", "--amend", "--no-edit")
                else:
                    # Card changed nothing of its own; record the pass alone.
                    git("commit", "-m", f"chore(night): record {card['id']} done")
            logger.info(
                "   PASS %s (%s, $%.4f)", card["id"], outcome.reason, outcome.cost_usd
            )
        elif outcome.skipped:
            logger.info("   SKIP %s: %s", card["id"], outcome.reason)
            # Advance the local cursor only. `done` is never persisted for a
            # skipped card (that write is guarded by outcome.passed), so this
            # lets a dry run enumerate the whole plan without ever recording a
            # card nobody ran.
            done.add(card["id"])
        else:
            logger.error("   FAIL %s: %s", card["id"], outcome.reason)
            # Leave it pending. A failed card that stays pending is retried
            # tomorrow; marking it done would hide the failure.
            break

    log.ended_at = utc_now()
    if not dry_run:
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = log.started_at.replace(":", "-")
        (log_dir / f"run_{stamp}.json").write_text(
            json.dumps(log.to_dict(), indent=2) + "\n"
        )
    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=REPO_ROOT / "docs/remediation/tasks.yaml")
    parser.add_argument("--status", type=Path, default=REPO_ROOT / "docs/remediation/status.json")
    parser.add_argument("--log-dir", type=Path, default=REPO_ROOT / "docs/remediation/nightly_logs")
    parser.add_argument("--phase", type=int, default=None)
    parser.add_argument("--max-cards", type=int, default=None)
    parser.add_argument("--budget-ceiling", type=float, default=25.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S"
    )

    lock = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.error("another night_phase_runner holds %s; exiting", LOCK_PATH)
        return 3
    lock.write(f"{os.getpid()} {utc_now()}\n")
    lock.flush()

    try:
        log = run(
            tasks_path=args.tasks,
            status_path=args.status,
            log_dir=args.log_dir,
            only_phase=args.phase,
            max_cards=args.max_cards,
            budget_ceiling=args.budget_ceiling,
            dry_run=args.dry_run,
        )
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()

    logger.info(
        "run complete: %d passed, %d failed, %d skipped, $%.4f spent",
        log.passed,
        log.failed,
        log.skipped,
        log.total_cost_usd,
    )
    if log.aborted_reason:
        return 2
    return 0 if log.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
