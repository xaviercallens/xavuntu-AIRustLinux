#!/usr/bin/env python3
"""
Antigravity v2 MCP Health & Diagnostics Verifier
Checks JSON configurations, environment dependencies, Node.js packages,
and verifies tool registration for all configured MCP servers.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

CONFIG_PATHS = [
    ROOT_DIR / ".antigravity" / "mcp_config.json",
    ROOT_DIR / ".agents" / "mcp_config.json",
    Path.home() / ".gemini" / "config" / "mcp_config.json",
]


def check_json_config(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "File does not exist"
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
        servers = content.get("mcpServers", {})
        return True, f"Valid ({len(servers)} servers declared: {', '.join(servers.keys())})"
    except Exception as err:
        return False, f"JSON Error: {err}"


def check_node_packages() -> dict[str, bool]:
    packages = [
        "@modelcontextprotocol/server-sequential-thinking",
        "@modelcontextprotocol/server-filesystem",
        "@modelcontextprotocol/server-github",
        "@modelcontextprotocol/server-memory",
    ]
    npm_path = shutil.which("npm")
    if not npm_path:
        return {pkg: False for pkg in packages}

    result = subprocess.run(
        ["npm", "list", "-g", "--depth=0"],
        capture_output=True,
        text=True,
        check=False,
    )
    statuses = {}
    for pkg in packages:
        statuses[pkg] = pkg in result.stdout
    return statuses


def check_python_guard_server() -> tuple[bool, str]:
    try:
        import asyncio
        import mcp_guard_server
        tools = asyncio.run(mcp_guard_server.mcp.list_tools())
        return True, f"Operational ({len(tools)} registered tools: {', '.join(t.name for t in tools[:4])}...)"
    except Exception as err:
        return False, f"Import/Init failed: {err}"


def check_claude_workflow_server() -> tuple[bool, str]:
    try:
        import asyncio
        import mcp_claude_workflow
        tools = asyncio.run(mcp_claude_workflow.mcp.list_tools())
        return True, f"Operational ({len(tools)} registered tools: {', '.join(t.name for t in tools)})"
    except Exception as err:
        return False, f"Import/Init failed: {err}"


def main() -> int:
    print("=" * 80)
    print("🛸 ANTIGRAVITY v2 - MCP CLUSTER DIAGNOSTIC & HEALTH CHECK")
    print("=" * 80)

    # 1. Config files
    print("\n1. MCP Configuration Files:")
    all_configs_valid = True
    for cfg in CONFIG_PATHS:
        ok, msg = check_json_config(cfg)
        status_icon = "✅" if ok else "❌"
        print(f"  {status_icon} {cfg}: {msg}")
        if not ok:
            all_configs_valid = False

    # 2. Node.js MCP Packages
    print("\n2. Node.js / NPM MCP Official Servers:")
    node_status = check_node_packages()
    all_node_valid = True
    for pkg, installed in node_status.items():
        status_icon = "✅" if installed else "❌"
        print(f"  {status_icon} {pkg}: {'Installed' if installed else 'MISSING'}")
        if not installed:
            all_node_valid = False

    # 3. Python FastMCP Servers
    print("\n3. Python FastMCP Local Guard Servers:")
    guard_ok, guard_msg = check_python_guard_server()
    print(f"  {'✅' if guard_ok else '❌'} agent-hardening-engine (mcp_guard_server.py): {guard_msg}")

    wf_ok, wf_msg = check_claude_workflow_server()
    print(f"  {'✅' if wf_ok else '❌'} claude-subtask-workflow (mcp_claude_workflow.py): {wf_msg}")

    print("\n" + "=" * 80)
    overall_ok = all_configs_valid and all_node_valid and guard_ok and wf_ok
    if overall_ok:
        print("🎉 ALL MCP SERVERS & CONFIGURATIONS FULLY OPERATIONAL IN ANTIGRAVITY v2")
        print("=" * 80)
        return 0
    else:
        print("⚠️ SOME MCP COMPONENTS REQUIRE ATTENTION")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())
