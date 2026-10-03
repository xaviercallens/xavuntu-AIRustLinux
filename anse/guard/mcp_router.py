#!/usr/bin/env python3
"""
Antigravity MCP Router & Gateway Integrator
Routes tools and JSON-RPC across in-process FastMCP Python servers and external stdio MCP processes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _expand_env_vars(val: Any) -> Any:
    """Expand ${VAR} environment variables recursively in config structures."""
    if isinstance(val, str):
        matches = ENV_VAR_PATTERN.findall(val)
        expanded = val
        for var in matches:
            env_val = os.getenv(var, "")
            expanded = expanded.replace(f"${{{var}}}", env_val)
        return expanded
    elif isinstance(val, list):
        return [_expand_env_vars(item) for item in val]
    elif isinstance(val, dict):
        return {k: _expand_env_vars(v) for k, v in val.items()}
    return val


class MCPRouter:
    """
    Centralized router for multi-server MCP infrastructure.
    Supports in-process FastMCP optimization for Python servers and stdio transports for community servers.
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path: Path | None = Path(config_path) if config_path else None
        self.servers: dict[str, dict[str, Any]] = {}
        self.tool_to_server: dict[str, str] = {}
        self.tools_cache: list[dict[str, Any]] = []
        self._in_process_servers: dict[str, Any] = {}

        if self.config_path and self.config_path.exists():
            self.load_config(self.config_path)

    def load_config(self, path: str | Path) -> dict[str, Any]:
        """Load and parse MCP server definitions from a json configuration file."""
        cfg_path = Path(path)
        if not cfg_path.exists():
            raise FileNotFoundError(f"MCP configuration file not found at: {cfg_path}")

        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        declared = raw.get("mcpServers", {})
        self.servers = _expand_env_vars(declared)
        self.config_path = cfg_path
        logger.info("Loaded %d MCP servers from %s", len(self.servers), cfg_path)
        self._register_in_process_servers()
        return self.servers

    def _register_in_process_servers(self) -> None:
        """Identify local python FastMCP servers for ultra-low latency direct calls."""
        for name, cfg in self.servers.items():
            args = cfg.get("args", [])
            for arg in args:
                if "mcp_guard_server.py" in str(arg):
                    try:
                        import mcp_guard_server

                        self._in_process_servers[name] = mcp_guard_server.mcp
                        logger.info("Registered in-process FastMCP server: %s", name)
                    except Exception as exc:
                        logger.warning("Failed to link in-process FastMCP server %s: %s", name, exc)
                elif "mcp_claude_workflow.py" in str(arg):
                    try:
                        import mcp_claude_workflow

                        self._in_process_servers[name] = mcp_claude_workflow.mcp
                        logger.info("Registered in-process FastMCP server: %s", name)
                    except Exception as exc:
                        logger.warning("Failed to link in-process FastMCP server %s: %s", name, exc)

    def list_servers(self) -> dict[str, Any]:
        """List all configured MCP servers and their transport types."""
        result: dict[str, Any] = {}
        for name, cfg in self.servers.items():
            is_in_proc = name in self._in_process_servers
            result[name] = {
                "command": cfg.get("command"),
                "args": cfg.get("args", []),
                "is_in_process": is_in_proc,
                "transport": "in-process" if is_in_proc else "stdio",
                "disabled": cfg.get("disabled", False),
            }
        return result

    async def list_tools(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Collect and return all available tools across all active MCP servers."""
        if self.tools_cache and not force_refresh:
            return self.tools_cache

        aggregated_tools: list[dict[str, Any]] = []
        mapping: dict[str, str] = {}

        for server_name, srv_cfg in self.servers.items():
            if srv_cfg.get("disabled", False):
                continue

            # Check in-process FastMCP first
            if server_name in self._in_process_servers:
                try:
                    fastmcp_instance = self._in_process_servers[server_name]
                    tools = await fastmcp_instance.list_tools()
                    for t in tools:
                        t_dict = {
                            "name": t.name,
                            "description": t.description or "",
                            "inputSchema": getattr(t, "parameters", {}),
                            "server": server_name,
                            "transport": "in-process",
                        }
                        aggregated_tools.append(t_dict)
                        mapping[t.name] = server_name
                except Exception as exc:
                    logger.error("Error listing tools for in-process server %s: %s", server_name, exc)
                continue

            # External stdio MCP server
            cmd = srv_cfg.get("command")
            args = srv_cfg.get("args", [])
            env = srv_cfg.get("env", {})
            full_env = {**os.environ, **env}

            try:
                params = StdioServerParameters(command=cmd, args=args, env=full_env)
                async with stdio_client(params) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tool_list = await session.list_tools()
                        for t in tool_list.tools:
                            t_dict = {
                                "name": t.name,
                                "description": t.description or "",
                                "inputSchema": getattr(t, "input_schema", getattr(t, "inputSchema", {})),
                                "server": server_name,
                                "transport": "stdio",
                            }
                            aggregated_tools.append(t_dict)
                            mapping[t.name] = server_name
            except Exception as exc:
                logger.error("Error connecting to stdio server %s: %s", server_name, exc)

        self.tool_to_server = mapping
        self.tools_cache = aggregated_tools
        return self.tools_cache

    async def call_tool(
        self,
        server_name: str | None,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dispatch a tool call to the appropriate MCP server."""
        args_payload = arguments or {}

        # Resolve server name if not specified or 'auto'
        resolved_server = server_name
        if not resolved_server or resolved_server == "auto":
            resolved_server = self.tool_to_server.get(tool_name)
            if not resolved_server:
                # Refresh cache to discover any newly added tools
                await self.list_tools(force_refresh=True)
                resolved_server = self.tool_to_server.get(tool_name)

        if not resolved_server or resolved_server not in self.servers:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' could not be mapped to any known MCP server.",
            }

        # Case 1: In-process FastMCP execution
        if resolved_server in self._in_process_servers:
            try:
                fastmcp_instance = self._in_process_servers[resolved_server]
                res = await fastmcp_instance.call_tool(tool_name, args_payload)
                structured = getattr(res, "structured_content", None)
                if structured is not None:
                    return {"success": True, "server": resolved_server, "result": structured}

                content = getattr(res, "content", [])
                text_results = [getattr(c, "text", str(c)) for c in content]
                final_res = "\n".join(text_results)
                try:
                    parsed_res = json.loads(final_res)
                    return {"success": True, "server": resolved_server, "result": parsed_res}
                except Exception:
                    return {"success": True, "server": resolved_server, "result": final_res}
            except Exception as exc:
                logger.exception("In-process MCP execution error on '%s': %s", tool_name, exc)
                return {"success": False, "server": resolved_server, "error": str(exc)}

        # Case 2: Stdio MCP execution
        srv_cfg = self.servers[resolved_server]
        cmd = srv_cfg.get("command")
        args = srv_cfg.get("args", [])
        env = srv_cfg.get("env", {})
        full_env = {**os.environ, **env}

        try:
            params = StdioServerParameters(command=cmd, args=args, env=full_env)
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    res = await session.call_tool(tool_name, arguments=args_payload)
                    content = getattr(res, "content", [])
                    extracted_text = [getattr(c, "text", str(c)) for c in content]
                    payload_text = "\n".join(extracted_text)
                    try:
                        parsed = json.loads(payload_text)
                        return {"success": True, "server": resolved_server, "result": parsed}
                    except Exception:
                        return {"success": True, "server": resolved_server, "result": payload_text}
        except Exception as exc:
            logger.exception("Stdio MCP execution error on '%s': %s", tool_name, exc)
            return {"success": False, "server": resolved_server, "error": str(exc)}

    async def handle_json_rpc(
        self,
        server_name: str,
        rpc_request: dict[str, Any],
    ) -> dict[str, Any]:
        """Proxy a JSON-RPC 2.0 message to an MCP server."""
        req_id = rpc_request.get("id")
        method = rpc_request.get("method", "")
        params = rpc_request.get("params", {})

        if method == "tools/list":
            tools = await self.list_tools()
            filtered = [t for t in tools if t.get("server") == server_name] if server_name != "all" else tools
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": filtered},
            }

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            call_res = await self.call_tool(server_name, tool_name, arguments)
            if call_res.get("success"):
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": call_res.get("result"),
                }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": call_res.get("error", "Execution failed")},
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not implemented in gateway proxy."},
        }
