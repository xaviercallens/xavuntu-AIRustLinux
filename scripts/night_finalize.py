#!/usr/bin/env python3
"""
Closing step of the night workflow: branch, push, and open or update a PR.

Runs after the card pass and the training pass. Builds the PR body from the
artifacts those two passes actually wrote -- the run log in
docs/remediation/nightly_logs/ and the report in training_runs/ -- so the PR
describes the night that happened rather than the night that was planned.

Rules it follows:

  * Never opens an empty PR. If the night produced no commits ahead of the
    base branch, it says so and exits 0. A PR with nothing in it is noise a
    reviewer has to open to discover is noise.
  * Never invents a result. Cards that failed are listed as failed with the
    accept command that rejected them; training stages that skipped are listed
    as skipped with their reason. A night where nothing trained is reported as
    a night where nothing trained.
  * Reuses the open PR for a branch instead of opening a second one.
  * Pushes only the night branch, never the base branch.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("night_finalize")

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "docs/remediation/nightly_logs"
TRAIN_DIR = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/training_runs")
BASE_BRANCH = "main"
BRANCH_PREFIX = "night/remediation"

ATTRIBUTION = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(REPO_ROOT), capture_output=True, text=True, check=check
    )


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def tonight_branch() -> str:
    return f"{BRANCH_PREFIX}-{datetime.now(timezone.utc):%Y-%m-%d}"


def commits_ahead(branch: str, base: str) -> list[str]:
    """Subjects of commits on `branch` not on `base`. Empty means nothing to PR."""
    proc = git("log", f"{base}..{branch}", "--oneline", check=False)
    if proc.returncode != 0:
        return []
    return [ln for ln in proc.stdout.strip().splitlines() if ln]


def latest_json(directory: Path) -> dict[str, Any] | None:
    if not directory.is_dir():
        return None
    files = sorted(directory.glob("*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("could not read %s: %s", files[-1], exc)
        return None


def render_body(
    run_log: dict[str, Any] | None,
    train_report: dict[str, Any] | None,
    commits: list[str],
) -> str:
    lines: list[str] = ["## Autonomous night run", ""]

    if run_log:
        counts = run_log.get("cards", {})
        lines += [
            f"**Cards** — {counts.get('passed', 0)} passed, "
            f"{counts.get('failed', 0)} failed, {counts.get('skipped', 0)} skipped. "
            f"Spend: ${run_log.get('total_cost_usd', 0):.4f}.",
            "",
            "Every card here was verified by the driver running its `accept` "
            "commands; a card is recorded as done only when all of them exited 0.",
            "",
        ]
        passed = [o for o in run_log.get("outcomes", []) if o.get("passed")]
        failed = [
            o
            for o in run_log.get("outcomes", [])
            if not o.get("passed") and not o.get("skipped")
        ]
        if passed:
            lines.append("| Card | Tier | Cost | Session |")
            lines.append("|---|---|---|---|")
            for o in passed:
                sid = (o.get("session_id") or "")[:8]
                lines.append(
                    f"| `{o['card_id']}` | {o['tier']} | "
                    f"${o.get('cost_usd', 0):.4f} | `{sid}` |"
                )
            lines.append("")
        if failed:
            lines.append("**Failed** (left pending, retried next run):")
            lines.append("")
            for o in failed:
                lines.append(f"- `{o['card_id']}` — {o.get('reason', 'unknown')}")
                for a in o.get("accept_results", []):
                    if a.get("exit_code"):
                        lines.append(
                            f"  - `{a['command'][:100]}` exited {a['exit_code']}"
                        )
            lines.append("")
        if run_log.get("aborted_reason"):
            lines += [f"**Run aborted:** {run_log['aborted_reason']}", ""]
    else:
        lines += ["No card run log found for this night.", ""]

    if train_report:
        c = train_report.get("counts", {})
        lines += [
            f"**Training** — {c.get('trained', 0)} trained, "
            f"{c.get('skipped', 0)} skipped, {c.get('failed', 0)} failed.",
            "",
        ]
        for stage in train_report.get("stages", []):
            lines.append(
                f"- `{stage['model']}` — **{stage['status']}**: {stage['reason']}"
            )
        lines.append("")
        cap = train_report.get("capability", {})
        if not cap.get("gpu"):
            lines += [
                f"> No GPU this run: {cap.get('detail', 'unknown')}. "
                "Nothing fell back to CPU and nothing was recorded as deployed.",
                "",
            ]
    else:
        lines += ["No training report found for this night.", ""]

    if commits:
        lines += ["<details><summary>Commits</summary>", ""]
        lines += [f"- {c}" for c in commits]
        lines += ["", "</details>", ""]

    lines += ["---", ATTRIBUTION]
    return "\n".join(lines)


def existing_pr(branch: str) -> str | None:
    proc = subprocess.run(
        ["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        items = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    return str(items[0]["number"]) if items else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE_BRANCH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-push", action="store_true", help="build the body, skip push and PR"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if git("status", "--porcelain").stdout.strip():
        logger.error("working tree is dirty; the night passes should have committed")
        return 1

    branch = current_branch()
    if not branch.startswith(BRANCH_PREFIX):
        target = tonight_branch()
        logger.info("on %s; switching to %s", branch, target)
        if not args.dry_run:
            exists = git("rev-parse", "--verify", target, check=False).returncode == 0
            git("checkout", target) if exists else git("checkout", "-b", target)
        branch = target

    commits = commits_ahead(branch, args.base)
    if not commits:
        logger.info("no commits on %s beyond %s; nothing to open a PR for", branch, args.base)
        return 0
    logger.info("%d commit(s) ahead of %s", len(commits), args.base)

    body = render_body(latest_json(LOG_DIR), latest_json(TRAIN_DIR), commits)
    title = f"Night run {datetime.now(timezone.utc):%Y-%m-%d}: {len(commits)} commit(s)"

    if args.dry_run or args.no_push:
        print(f"--- title ---\n{title}\n--- body ---\n{body}")
        return 0

    if shutil.which("gh") is None:
        logger.error("gh is not on PATH; pushed nothing")
        return 1

    push = git("push", "-u", "origin", branch, check=False)
    if push.returncode != 0:
        logger.error("push failed: %s", push.stderr.strip())
        return 1
    logger.info("pushed %s", branch)

    number = existing_pr(branch)
    body_file = REPO_ROOT / ".night_pr_body.md"
    body_file.write_text(body)
    try:
        if number:
            proc = subprocess.run(
                ["gh", "pr", "edit", number, "--title", title, "--body-file", str(body_file)],
                cwd=str(REPO_ROOT), capture_output=True, text=True, check=False,
            )
            action = f"updated PR #{number}"
        else:
            proc = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--base", args.base,
                    "--head", branch,
                    "--title", title,
                    "--body-file", str(body_file),
                ],
                cwd=str(REPO_ROOT), capture_output=True, text=True, check=False,
            )
            action = "opened PR"
    finally:
        body_file.unlink(missing_ok=True)

    if proc.returncode != 0:
        logger.error("gh failed: %s", (proc.stderr or proc.stdout).strip())
        return 1
    logger.info("%s: %s", action, (proc.stdout or "").strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
