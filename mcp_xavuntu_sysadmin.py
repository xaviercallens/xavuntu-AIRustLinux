#!/usr/bin/env python3
"""
mcp_xavuntu_sysadmin.py — Model Context Protocol (MCP) Stdio Server for Xavuntu AI & LinuxOS-AI.

Exposes native system administration capabilities to Antigravity, Claude Code, and Gemini CLI:
1. `install_package`: Package manager auto-detection and installation with dry-run support.
2. `setup_web_server`: Enterprise Nginx/Apache deployment with SSL/TLS.
3. `install_database`: Enterprise Oracle 21c/23c, PostgreSQL, and Redis provisioning.
4. `check_system_requirements`: Hardware & kernel compatibility auditing.
5. `system_health_audit`: Real-time /proc and /sys telemetry and bottleneck analysis.
6. `clean_system`: Cache and log cleanup.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

_repo_root = os.path.dirname(os.path.abspath(__file__))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from anse.admin.system_admin import SystemAdminEngine

logger = logging.getLogger("mcp_sysadmin")
logging.basicConfig(level=logging.ERROR, stream=sys.stderr)


TOOLS_MANIFEST = [
    {
        "name": "install_package",
        "description": "Install software packages on Xavuntu/Linux with auto-detection of package manager (apt, snap, dnf, etc.)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Package name to install"},
                "version": {"type": "string", "description": "Specific version (optional)"},
                "manager": {
                    "type": "string",
                    "enum": ["auto", "apt", "snap", "dnf", "yum", "pacman", "brew"],
                    "default": "auto",
                    "description": "Package manager to use",
                },
                "dry_run": {"type": "boolean", "default": True, "description": "Simulate without executing"},
            },
            "required": ["package"],
        },
    },
    {
        "name": "setup_web_server",
        "description": "Configure and deploy production Nginx or Apache web server with SSL/TLS Let's Encrypt support",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server_type": {"type": "string", "enum": ["nginx", "apache", "both"], "default": "nginx"},
                "ssl_enabled": {"type": "boolean", "default": True},
                "domain": {"type": "string", "description": "Domain name for SSL certificate"},
                "auto_start": {"type": "boolean", "default": True},
            },
            "required": ["server_type"],
        },
    },
    {
        "name": "install_database",
        "description": "Plan and deploy enterprise databases (Oracle 21c/23c Free Edition, PostgreSQL, MySQL, Redis)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_type": {"type": "string", "enum": ["oracle", "postgres", "mysql", "redis"], "default": "oracle"},
                "version": {"type": "string", "default": "21c"},
                "memory_gb": {"type": "number", "default": 8.0},
                "storage_gb": {"type": "number", "default": 50.0},
                "install_path": {"type": "string", "default": "/opt/oracle"},
                "auto_start": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "check_system_requirements",
        "description": "Audit system hardware, kernel, and environment requirements for specific software",
        "inputSchema": {
            "type": "object",
            "properties": {
                "software": {"type": "string", "description": "Software to check (e.g. 'oracle', 'docker', 'nginx', 'kubernetes')"},
                "detailed": {"type": "boolean", "default": True},
            },
            "required": ["software"],
        },
    },
    {
        "name": "system_health_audit",
        "description": "Retrieve comprehensive real-time hardware telemetry and diagnostic bottleneck analysis",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "clean_system",
        "description": "Prune stale temporary logs, developer pip caches, and drop inactive page caches",
        "inputSchema": {
            "type": "object",
            "properties": {
                "aggressive": {"type": "boolean", "default": False},
            },
        },
    },
]


class MCPSysAdminServer:
    def __init__(self):
        self.engine = SystemAdminEngine()

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = request.get("method")
        msg_id = request.get("id")

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS_MANIFEST},
            }

        elif method == "tools/call":
            params = request.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})

            try:
                result_content = self.dispatch_tool(name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(result_content, indent=2) if isinstance(result_content, (dict, list)) else str(result_content)}
                        ]
                    },
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32603, "message": str(e)},
                }

        elif method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "xavuntu-sysadmin-mcp", "version": "1.0.0"},
                },
            }

        elif method == "notifications/initialized":
            return None

        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

    def dispatch_tool(self, name: str, args: Dict[str, Any]) -> Any:
        if name == "install_package":
            pkg = args.get("package", "")
            ver = args.get("version")
            mgr = args.get("manager", "auto")
            dry = args.get("dry_run", True)
            plan = self.engine.plan_package_install(pkg, ver, mgr, dry_run=dry)
            if dry:
                return plan.to_dict()
            return self.engine.execute_package_install(plan)

        elif name == "setup_web_server":
            st = args.get("server_type", "nginx")
            ssl = args.get("ssl_enabled", True)
            dom = args.get("domain")
            auto = args.get("auto_start", True)
            plan = self.engine.plan_web_server(server_type=st, ssl_enabled=ssl, domain=dom, auto_start=auto)
            return plan.to_dict()

        elif name == "install_database":
            db_type = args.get("db_type", "oracle")
            ver = args.get("version", "21c")
            mem = float(args.get("memory_gb", 8.0))
            storage = float(args.get("storage_gb", 50.0))
            path = args.get("install_path", "/opt/oracle")
            auto = args.get("auto_start", True)
            plan = self.engine.plan_database_install(db_type=db_type, version=ver, memory_gb=mem, storage_gb=storage, install_path=path, auto_start=auto)
            return plan.to_dict()

        elif name == "check_system_requirements":
            software = args.get("software", "oracle")
            rep = self.engine.check_requirements(software, detailed=args.get("detailed", True))
            return rep.to_dict()

        elif name == "system_health_audit":
            return self.engine.analyze_performance()

        elif name == "clean_system":
            return self.engine.clean_system(aggressive=args.get("aggressive", False))

        else:
            raise ValueError(f"Unknown tool: {name}")

    def run_stdio(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                resp = self.handle_request(req)
                if resp:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                logger.error(f"Error handling MCP line: {e}")


if __name__ == "__main__":
    server = MCPSysAdminServer()
    server.run_stdio()
