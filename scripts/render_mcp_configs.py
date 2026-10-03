#!/usr/bin/env python3
"""
Render this checkout's MCP server configs so their `command`/`args` paths
point at *this* machine's venv and repo root, instead of whichever machine
last hand-edited them (see CLAUDE.md's Antigravity/Claude Code config
matrix and anse/infrastructure/agent_environment.py for the detection this
script builds on).

Claude Code's `.mcp.json` already uses the portable `${CLAUDE_PROJECT_DIR:-.}`
variable (supported since Claude Code 2.1.203) and is checked, not rewritten.
Google Antigravity has no documented equivalent, so
`.antigravity/mcp_config.json` gets this machine's literal, freshly-computed
absolute path stamped in here instead -- rerun this after cloning the repo
onto a new machine or user account.

Usage:
    python scripts/render_mcp_configs.py                # renders for the detected agent
    python scripts/render_mcp_configs.py --agent antigravity
    python scripts/render_mcp_configs.py --agent claude_code
    python scripts/render_mcp_configs.py --all           # renders every known config
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from anse.infrastructure.agent_environment import (  # noqa: E402
    ANTIGRAVITY,
    CLAUDE_CODE,
    detect_coding_agent,
)


def render_antigravity_config(project_root: Path) -> Path:
    """Stamp this machine's absolute paths into `.antigravity/mcp_config.json`.

    Also de-duplicates the repeated "claude-subtask-workflow" key a prior
    hand-edit left in (JSON parsers keep only the last occurrence, silently
    dropping the first) by writing each server key exactly once.
    """
    venv_python = project_root / ".venv" / "bin" / "python"
    guard_server = project_root / "mcp_guard_server.py"
    workflow_server = project_root / "mcp_claude_workflow.py"
    config = {
        "mcpServers": {
            "antigravity-guard": {
                "command": str(venv_python),
                "args": [str(guard_server)],
                "env": {"PYTHONPATH": str(project_root)},
            },
            "claude-subtask-workflow": {
                "command": str(venv_python),
                "args": [str(workflow_server)],
                "env": {"PYTHONPATH": str(project_root)},
            },
            "logic-planner": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
            },
            "local-filesystem": {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    str(project_root / "anse"),
                    str(project_root / "tests"),
                    str(project_root / "formal"),
                ],
            },
            "github-radar": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
            },
            "memory-graph": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
            },
        }
    }
    path = project_root / ".antigravity" / "mcp_config.json"
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def check_claude_code_config(project_root: Path) -> tuple[Path, bool]:
    """Verify `.mcp.json` still uses the portable `${CLAUDE_PROJECT_DIR:-.}`
    form rather than rewriting it -- Claude Code expands that variable
    itself at launch, so no per-machine substitution is needed here."""
    path = project_root / ".mcp.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    portable = all(
        "${CLAUDE_PROJECT_DIR" in server.get("command", "")
        for server in config.get("mcpServers", {}).values()
    )
    return path, portable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=[CLAUDE_CODE, ANTIGRAVITY], default=None)
    parser.add_argument("--all", action="store_true", help="render every known config")
    args = parser.parse_args(argv)

    agent = args.agent or detect_coding_agent()
    targets = (CLAUDE_CODE, ANTIGRAVITY) if args.all else (agent,)

    exit_code = 0
    for target in targets:
        if target == ANTIGRAVITY:
            path = render_antigravity_config(ROOT_DIR)
            print(f"wrote {path}")
        elif target == CLAUDE_CODE:
            path, portable = check_claude_code_config(ROOT_DIR)
            status = "portable" if portable else "NEEDS FIX: hardcoded path found"
            print(f"{path}: {status}")
            if not portable:
                exit_code = 1
        else:
            print(f"agent '{target}' not detected/specified; nothing rendered for it")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
