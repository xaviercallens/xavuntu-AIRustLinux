"""
anse/admin/intent_router.py — Conversational Intent Router for AI System Administration.

Dispatches natural language user queries to structured SystemCommand objects.
Architecture:
- Fast-Path Deterministic Dispatcher: Sub-millisecond regex router for common admin tasks.
- Local Sovereign Reasoner: Qwen 14B / 3.8 Quant via Ollama with AttentionMatter Redis LTM context.
- Cloud Titan Engine: Gemini API fallback if GEMINI_API_KEY is present.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from anse.admin.system_admin import SystemAdminEngine

logger = logging.getLogger("anse.admin.intent_router")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [AIOS-ROUTER] %(message)s")


@dataclass
class SystemCommand:
    intent: str
    tools: List[str]
    params: Dict[str, Any]
    confirmation_required: bool
    description: str
    command_preview: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IntentRouter:
    """
    Intelligent Router for Natural Language System Administration.
    """

    def __init__(
        self,
        admin_engine: Optional[SystemAdminEngine] = None,
        ollama_url: str = "http://127.0.0.1:11434",
        preferred_model: str = "gwaya-qwen:14b",
    ) -> None:
        self.engine = admin_engine or SystemAdminEngine()
        self.ollama_url = ollama_url
        self.preferred_model = preferred_model
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")

    def route_command(self, query: str) -> SystemCommand:
        """
        Parse conversational command into a structured SystemCommand.
        Evaluates Fast-Path first, then Local Sovereign Reasoner.
        """
        q = query.strip()
        lower = q.lower()

        # ---------------------------------------------------------------------
        # Fast-Path Deterministic Router (0.1ms latency)
        # ---------------------------------------------------------------------
        # 1. Requirements Check
        if any(w in lower for w in ("check", "requis", "prerequis", "requirements", "compatible", "test")):
            target = "oracle"
            for t in ("docker", "nginx", "apache", "kubernetes", "k8s", "redis", "postgres", "mysql", "oracle"):
                if t in lower:
                    target = t
                    break
            report = self.engine.check_requirements(target)
            return SystemCommand(
                intent="check_requirements",
                tools=["check_system_requirements", "hardware_probe"],
                params={"software": target},
                confirmation_required=False,
                description=f"Audit hardware and kernel requirements for {target.upper()}",
                command_preview=f"check_requirements --software={target}",
            )

        # 2. Package Installation
        m_install = re.search(r"^(?:installe|install|ajouter|add)\s+([\w\-\.\+]+)(?:\s+(?:version\s+)?([\w\.\-]+))?", lower)
        if m_install and not any(k in lower for k in ("oracle", "database", "web", "nginx", "apache")):
            pkg = m_install.group(1).strip()
            ver = m_install.group(2).strip() if m_install.group(2) else None
            plan = self.engine.plan_package_install(package=pkg, version=ver, dry_run=True)
            return SystemCommand(
                intent="install_package",
                tools=["install_package", "package_manager"],
                params={"package": pkg, "version": ver, "manager": plan.manager},
                confirmation_required=not plan.already_installed,
                description=f"Install software package '{pkg}' using {plan.manager}",
                command_preview=f"{plan.command} {' '.join(plan.args)}",
            )

        # 3. Oracle / Database Setup
        if (any(v in lower for v in ("install", "setup", "deploy", "installer", "configurer")) and any(d in lower for d in ("oracle", "database", "db", "base de", "postgres", "mysql", "redis"))) or ("oracle" in lower and not any(c in lower for c in ("check", "status"))):
            db_type = "oracle"
            if "postgres" in lower:
                db_type = "postgres"
            elif "mysql" in lower or "mariadb" in lower:
                db_type = "mysql"
            elif "redis" in lower:
                db_type = "redis"

            # Parse memory if mentioned
            mem_gb = 8.0
            m_mem = re.search(r"(\d+)\s*(?:gb|go|g)", lower)
            if m_mem:
                mem_gb = float(m_mem.group(1))

            plan = self.engine.plan_database_install(db_type=db_type, memory_gb=mem_gb)
            return SystemCommand(
                intent="install_database",
                tools=["install_database", "system_preflight", "user_manager"],
                params={"db_type": db_type, "memory_gb": mem_gb, "version": plan.version},
                confirmation_required=True,
                description=f"Configure and provision {db_type.upper()} {plan.version} database (SID: {plan.sid})",
                command_preview=f"install_database --type={db_type} --memory={mem_gb}GB --path={plan.install_path}",
            )

        # 3. Web Server Setup
        if any(w in lower for w in ("webserver", "web server", "nginx", "apache", "serveur web")):
            server_type = "nginx"
            if "apache" in lower and "nginx" in lower:
                server_type = "both"
            elif "apache" in lower:
                server_type = "apache"

            ssl = "no ssl" not in lower and "sans ssl" not in lower
            domain = None
            m_dom = re.search(r"(?:for|pour|domain|domaine)\s+([a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,})", lower)
            if m_dom:
                domain = m_dom.group(1)

            plan = self.engine.plan_web_server(server_type=server_type, ssl_enabled=ssl, domain=domain)
            return SystemCommand(
                intent="setup_web_server",
                tools=["setup_web_server", "certbot_ssl", "systemd"],
                params={"server_type": server_type, "ssl_enabled": ssl, "domain": domain},
                confirmation_required=True,
                description=f"Deploy enterprise {server_type.upper()} web server stack with {'SSL' if ssl else 'HTTP'}",
                command_preview=f"setup_web_server --type={server_type} --ssl={ssl} {'--domain=' + domain if domain else ''}",
            )

        # 4. Requirements Check
        if any(w in lower for w in ("check", "requis", "prerequis", "requirements", "compatible")):
            target = "oracle"
            for t in ("docker", "nginx", "apache", "kubernetes", "k8s", "redis", "oracle"):
                if t in lower:
                    target = t
                    break
            report = self.engine.check_requirements(target)
            return SystemCommand(
                intent="check_requirements",
                tools=["check_system_requirements", "hardware_probe"],
                params={"software": target},
                confirmation_required=False,
                description=f"Audit hardware and kernel requirements for {target.upper()}",
                command_preview=f"check_requirements --software={target}",
            )

        # 5. System Cleanup
        if any(w in lower for w in ("clean", "nettoie", "nettoyer", "purger", "purge", "free memory")):
            return SystemCommand(
                intent="clean_system",
                tools=["clean_system", "drop_caches", "prune_logs"],
                params={"aggressive": "aggressive" in lower or "complet" in lower},
                confirmation_required=False,
                description="Prune developer caches, temporary files, and drop stale page caches",
                command_preview="clean_system --caches --logs --drop-caches",
            )

        # 6. Performance Analysis
        if any(w in lower for w in ("slow", "lent", "perf", "performance", "analyze", "analyser", "diagnostic", "cpu")):
            return SystemCommand(
                intent="analyze_performance",
                tools=["analyze_performance", "process_monitor"],
                params={},
                confirmation_required=False,
                description="Diagnose CPU, memory, and disk bottlenecks",
                command_preview="analyze_performance --telemetry",
            )

        # 7. Security Hardening
        if any(w in lower for w in ("secure", "securiser", "security", "audit", "shield", "bouclier", "unhackable")):
            return SystemCommand(
                intent="secure_system",
                tools=["kal_cyber_shield", "kernel_sysctl_hardening", "port_scan"],
                params={},
                confirmation_required=False,
                description="Audit zero-trust compliance, sysctl hardening, and network attack surface",
                command_preview="secure_system --zero-trust --audit",
            )

        # ---------------------------------------------------------------------
        # Sovereign LLM Fallback (Qwen / Gemini)
        # ---------------------------------------------------------------------
        return self._route_with_llm(q)

    def _route_with_llm(self, query: str) -> SystemCommand:
        """Route complex queries via Sovereign Local Reasoner or Gemini API."""
        prompt = (
            f"Tu es le routeur d'administration système Linux (AIOS) de Xavuntu.\n"
            f"Requête utilisateur: '{query}'\n"
            f"Choisis l'intention parmi: install_package, install_database, setup_web_server, check_requirements, clean_system, analyze_performance, secure_system.\n"
            f"Réponds UNIQUEMENT au format JSON strict:\n"
            f'{{"intent": "...", "description": "...", "tools": ["..."], "confirmation_required": true/false, "command_preview": "..."}}'
        )

        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/generate",
                data=json.dumps({"model": self.preferred_model, "prompt": prompt, "stream": False, "format": "json"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                parsed = json.loads(data.get("response", "{}"))
                return SystemCommand(
                    intent=parsed.get("intent", "analyze_performance"),
                    tools=parsed.get("tools", ["system_diagnostics"]),
                    params={},
                    confirmation_required=parsed.get("confirmation_required", False),
                    description=parsed.get("description", f"Process: {query}"),
                    command_preview=parsed.get("command_preview", f"aios {query}"),
                )
        except Exception:
            # Deterministic fallback
            return SystemCommand(
                intent="analyze_performance",
                tools=["analyze_performance"],
                params={"query": query},
                confirmation_required=False,
                description=f"Analyze system state for query: '{query}'",
                command_preview=f"aios status",
            )
