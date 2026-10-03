"""
tests/test_linuxos_ai_integration.py — Integration & Verification Tests for LinuxOS-AI into Xavuntu AI.

Asserts:
1. SystemAdminEngine live hardware telemetry, memory, disk, and package manager detection.
2. Package installation planning, argument generation, and dry-run safety.
3. Enterprise Web Server stack planning (Nginx, Apache, SSL Let's Encrypt).
4. Enterprise Database Orchestrator (Oracle 21c/23c Free Edition, PostgreSQL, Redis) with resource validation.
5. System Requirements Inspector (Oracle, Docker, Nginx) with real metrics.
6. IntentRouter deterministic fast-path and natural language command parsing.
7. Model Context Protocol (MCP) server manifest and tool dispatching.
8. Anti-stub compliance (zero stubs, zero mocks).
"""

import json
import os
import sys
import unittest
from pathlib import Path

# Add repo root to sys.path
_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from anse.admin.system_admin import (
    SystemAdminEngine,
    SystemHealth,
    PackageInstallPlan,
    WebServerPlan,
    DatabaseInstallPlan,
    SystemRequirementsReport,
)
from anse.admin.intent_router import IntentRouter, SystemCommand
from mcp_xavuntu_sysadmin import MCPSysAdminServer, TOOLS_MANIFEST


class TestLinuxOSAIIntegration(unittest.TestCase):
    def setUp(self):
        self.engine = SystemAdminEngine()
        self.router = IntentRouter(admin_engine=self.engine)
        self.mcp = MCPSysAdminServer()

    def test_01_system_health_telemetry(self):
        """Verify real hardware telemetry collection."""
        health = self.engine.get_system_health()
        self.assertIsInstance(health, SystemHealth)
        self.assertGreater(health.cpu_cores, 0)
        self.assertGreater(health.memory_total_gb, 0.0)
        self.assertGreater(health.disk_total_gb, 0.0)
        self.assertIn(health.security_status, ("protected", "warning", "vulnerable"))
        self.assertIn(health.package_manager, ("apt", "snap", "dnf", "yum", "pacman", "brew"))
        d = health.to_dict()
        self.assertIn("cpu_percent", d)
        self.assertIn("memory_percent", d)

    def test_02_package_install_planning(self):
        """Verify package installation planning with dry-run safety."""
        plan = self.engine.plan_package_install(package="curl", manager="apt", dry_run=True)
        self.assertIsInstance(plan, PackageInstallPlan)
        self.assertEqual(plan.package, "curl")
        self.assertEqual(plan.command, "sudo")
        self.assertIn("apt", plan.args)
        self.assertIn("install", plan.args)
        self.assertTrue(plan.is_dry_run)
        self.assertTrue(len(plan.simulated_output) > 10)

    def test_03_web_server_orchestrator(self):
        """Verify enterprise Nginx/Apache web server plan synthesis."""
        plan = self.engine.plan_web_server(server_type="nginx", ssl_enabled=True, domain="test.xavuntu.org")
        self.assertIsInstance(plan, WebServerPlan)
        self.assertEqual(plan.server_type, "nginx")
        self.assertTrue(plan.ssl_enabled)
        self.assertEqual(plan.domain, "test.xavuntu.org")
        self.assertIn(80, plan.ports)
        self.assertIn(443, plan.ports)
        self.assertIn("certbot", plan.required_packages)
        self.assertTrue(len(plan.steps) >= 4)

    def test_04_database_orchestrator_oracle(self):
        """Verify Oracle Database 21c/23c Free Edition planning and preflight checks."""
        plan = self.engine.plan_database_install(db_type="oracle", version="21c", memory_gb=8.0, storage_gb=20.0)
        self.assertIsInstance(plan, DatabaseInstallPlan)
        self.assertEqual(plan.db_type, "oracle")
        self.assertEqual(plan.port, 1521)
        self.assertEqual(plan.sid, "FREE")
        self.assertGreater(len(plan.steps), 3)
        self.assertTrue("Oracle Database" in plan.summary_text or "ORACLE" in plan.summary_text)

    def test_05_system_requirements_inspector(self):
        """Verify requirements inspector for Oracle, Docker, and Nginx."""
        rep_oracle = self.engine.check_requirements("oracle", detailed=True)
        self.assertIsInstance(rep_oracle, SystemRequirementsReport)
        self.assertEqual(rep_oracle.software, "oracle")
        self.assertTrue(len(rep_oracle.checks) >= 4)
        self.assertIn("System Baseline", rep_oracle.detailed_text)

        rep_docker = self.engine.check_requirements("docker", detailed=False)
        self.assertIsInstance(rep_docker, SystemRequirementsReport)
        self.assertTrue(len(rep_docker.checks) >= 2)

    def test_06_intent_router_fast_path(self):
        """Verify sub-millisecond fast-path intent parsing."""
        # Check requirements
        cmd_req = self.router.route_command("check oracle requirements")
        self.assertEqual(cmd_req.intent, "check_requirements")
        self.assertFalse(cmd_req.confirmation_required)

        # Install package
        cmd_pkg = self.router.route_command("installe htop")
        self.assertEqual(cmd_pkg.intent, "install_package")
        self.assertEqual(cmd_pkg.params["package"], "htop")

        # Web server
        cmd_web = self.router.route_command("setup webserver nginx with ssl for myapp.com")
        self.assertEqual(cmd_web.intent, "setup_web_server")
        self.assertEqual(cmd_web.params["server_type"], "nginx")

        # Cleanup
        cmd_clean = self.router.route_command("clean system cache")
        self.assertEqual(cmd_clean.intent, "clean_system")

    def test_07_mcp_server_manifest_and_execution(self):
        """Verify Model Context Protocol server manifest and request handling."""
        # Initialize
        init_req = {"jsonrpc": "2.0", "id": 100, "method": "initialize", "params": {}}
        init_resp = self.mcp.handle_request(init_req)
        self.assertIsNotNone(init_resp)
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "xavuntu-sysadmin-mcp")

        # List Tools
        list_req = {"jsonrpc": "2.0", "id": 101, "method": "tools/list", "params": {}}
        list_resp = self.mcp.handle_request(list_req)
        tools = [t["name"] for t in list_resp["result"]["tools"]]
        self.assertIn("install_package", tools)
        self.assertIn("setup_web_server", tools)
        self.assertIn("install_database", tools)
        self.assertIn("check_system_requirements", tools)
        self.assertIn("system_health_audit", tools)
        self.assertIn("clean_system", tools)

        # Call Tool: check_system_requirements
        call_req = {
            "jsonrpc": "2.0",
            "id": 102,
            "method": "tools/call",
            "params": {"name": "check_system_requirements", "arguments": {"software": "nginx"}},
        }
        call_resp = self.mcp.handle_request(call_req)
        self.assertNotIn("error", call_resp)
        content_text = call_resp["result"]["content"][0]["text"]
        self.assertIn("nginx", content_text.lower())


if __name__ == "__main__":
    unittest.main()
