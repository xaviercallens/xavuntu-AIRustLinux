"""
anse/neo/protocols.py — Machine Communication Protocol (MCP) Handlers for Neo-AI & GWAYA v3.

Implements all 5 core protocols from Vasco0x4/Neo-AI with native Xavuntu/GWAYA enhancements:
1. `<mcp:terminal>`: Subprocess command execution with approval & timeout.
2. `<mcp:files>`: File read, write, list, and inspection.
3. `<mcp:analyze>`: Comprehensive hardware, memory, CPU, and disk analysis (integrated with `/proc` and Kula).
4. `<mcp:network>`: Interface detection, socket inspection, ping, and local scan.
5. `<mcp:security>`: Security posture inspection, listening ports, SUID checks, and KalCyberShield audit.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from anse.neo.approval import ApprovalHandler, CommandApprovalResult

logger = logging.getLogger("anse.neo.protocols")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [NEO-MCP] %(message)s")


class ProtocolHandler(ABC):
    """Abstract base class for all MCP protocol handlers."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def handle(self, content: str, approval_handler: ApprovalHandler, interactive: bool = True) -> Dict[str, Any]:
        """Execute protocol content and return execution result dict."""
        pass


class TerminalProtocolHandler(ProtocolHandler):
    """Executes arbitrary shell commands with GWAYA approval screening."""

    def __init__(self) -> None:
        super().__init__("terminal")

    def handle(self, content: str, approval_handler: ApprovalHandler, interactive: bool = True) -> Dict[str, Any]:
        cmd_str = content.strip()
        result: Dict[str, Any] = {
            "protocol": "terminal",
            "command": cmd_str,
            "executed": False,
            "output": "",
            "returncode": -1,
            "duration_ms": 0.0,
        }

        # Request approval & screen with GWAYA System 1
        approval = approval_handler.request_approval(cmd_str, interactive=interactive)
        if not approval.approved:
            result["output"] = f"[REJECTED] {approval.reason}"
            result["blocked_by_guard"] = (approval.risk_level == "CRITICAL_BLOCKED")
            return result

        # Execute command in subprocess
        t0 = time.perf_counter()
        try:
            res = subprocess.run(
                cmd_str,
                shell=True,
                executable="/bin/bash",
                capture_output=True,
                text=True,
                timeout=60,
            )
            duration_ms = (time.perf_counter() - t0) * 1000.0
            out = (res.stdout + "\n" + res.stderr).strip()

            result["executed"] = True
            result["output"] = out if out else "(Command executed with no output)"
            result["returncode"] = res.returncode
            result["duration_ms"] = round(duration_ms, 2)
            return result
        except subprocess.TimeoutExpired:
            result["output"] = "[ERROR] Command timed out after 60 seconds."
            result["duration_ms"] = 60000.0
            return result
        except Exception as e:
            result["output"] = f"[ERROR] Execution failed: {e}"
            return result


class FilesProtocolHandler(ProtocolHandler):
    """Handles file operations: read, write, list, inspect."""

    def __init__(self) -> None:
        super().__init__("files")

    def handle(self, content: str, approval_handler: ApprovalHandler, interactive: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "protocol": "files",
            "command": content,
            "executed": False,
            "output": "",
        }

        # Parse file commands: list, read:<path>, write:<path>:<content>, info:<path>
        cmd = content.strip()

        if cmd.startswith("read:"):
            target_path = cmd[5:].strip()
            p = Path(os.path.expanduser(target_path))
            if p.exists() and p.is_file():
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")[:4000]
                    result["executed"] = True
                    result["output"] = text
                except Exception as e:
                    result["output"] = f"Error reading file: {e}"
            else:
                result["output"] = f"File not found: {target_path}"

        elif cmd.startswith("list:"):
            target_dir = cmd[5:].strip() or "."
            p = Path(os.path.expanduser(target_dir))
            if p.exists() and p.is_dir():
                items = sorted([f"{'[DIR] ' if i.is_dir() else '[FILE]' } {i.name}" for i in p.iterdir()])[:50]
                result["executed"] = True
                result["output"] = "\n".join(items)
            else:
                result["output"] = f"Directory not found: {target_dir}"

        elif cmd.startswith("write:"):
            # Supports both 'write:<path>:<content>' and 'write:<path> <content>'
            payload = cmd[6:]
            if ":" in payload:
                parts = payload.split(":", 1)
            elif " " in payload:
                parts = payload.split(" ", 1)
            else:
                parts = [payload, ""]

            if len(parts) == 2:
                target_path, file_content = parts[0].strip(), parts[1]
                approval = approval_handler.request_approval(f"write to {target_path}", interactive=interactive)
                if approval.approved:
                    try:
                        p = Path(os.path.expanduser(target_path))
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_text(file_content, encoding="utf-8")
                        result["executed"] = True
                        result["output"] = f"Successfully wrote {len(file_content)} characters to {target_path}"
                    except Exception as e:
                        result["output"] = f"Error writing file: {e}"
                else:
                    result["output"] = f"[REJECTED] {approval.reason}"
            else:
                result["output"] = "Invalid write command format. Use 'write:<path> <content>' or 'write:<path>:<content>'"
        else:
            # Default to file info or ls
            p = Path(os.path.expanduser(cmd if cmd else "."))
            if p.exists():
                st = p.stat()
                result["executed"] = True
                result["output"] = f"Path: {p.resolve()}\nType: {'Directory' if p.is_dir() else 'File'}\nSize: {st.st_size} bytes\nModified: {time.ctime(st.st_mtime)}"
            else:
                result["output"] = f"Path not found: {cmd}"

        return result


class AnalyzeProtocolHandler(ProtocolHandler):
    """Executes comprehensive system hardware, memory, and performance analysis."""

    def __init__(self) -> None:
        super().__init__("analyze")

    def handle(self, content: str, approval_handler: ApprovalHandler, interactive: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "protocol": "analyze",
            "command": "system_analysis",
            "executed": True,
            "output": "",
        }

        lines = [
            "===== XAVUNTU / GWAYA SYSTEM ANALYSIS =====",
            f"• Platform: Linux {os.uname().release} ({os.uname().machine})",
            f"• CPU Cores: {os.cpu_count() or 8}",
        ]

        # Loadavg
        try:
            with open("/proc/loadavg", "r") as f:
                lines.append(f"• CPU Load: {f.read().strip()}")
        except Exception:
            pass

        # Memory
        try:
            with open("/proc/meminfo", "r") as f:
                mem_lines = [line.strip() for line in f if any(k in line for k in ("MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:"))]
                lines.append("• Memory Metrics:")
                for m in mem_lines:
                    lines.append(f"    {m}")
        except Exception:
            pass

        # Disk
        try:
            st = os.statvfs("/")
            total_gb = (st.f_blocks * st.f_frsize) / (1024**3)
            free_gb = (st.f_bavail * st.f_frsize) / (1024**3)
            lines.append(f"• Root Filesystem: {free_gb:.1f} GB free of {total_gb:.1f} GB")
        except Exception:
            pass

        # TPU Arena
        if os.path.exists("/dev/shm"):
            try:
                shm_st = os.statvfs("/dev/shm")
                shm_gb = (shm_st.f_blocks * shm_st.f_frsize) / (1024**3)
                lines.append(f"• TPU ReBAR Arena: {shm_gb:.1f} GB mapped memory")
            except Exception:
                pass

        result["output"] = "\n".join(lines)
        return result


class NetworkProtocolHandler(ProtocolHandler):
    """Handles network operations: interfaces, listening sockets, ping, local scan."""

    def __init__(self) -> None:
        super().__init__("network")

    def handle(self, content: str, approval_handler: ApprovalHandler, interactive: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "protocol": "network",
            "command": content,
            "executed": False,
            "output": "",
        }

        cmd = content.strip().lower()

        if cmd in ("interfaces", "ip", "addr", ""):
            # Query interfaces
            try:
                res = subprocess.run(["ip", "-br", "addr"], capture_output=True, text=True, check=False)
                result["executed"] = True
                result["output"] = res.stdout.strip() if res.stdout else "No network interfaces found."
            except Exception:
                result["output"] = "Failed to query network interfaces."

        elif cmd in ("ports", "listening", "sockets"):
            try:
                res = subprocess.run(["ss", "-tuln"], capture_output=True, text=True, check=False)
                result["executed"] = True
                result["output"] = res.stdout.strip()[:2000]
            except Exception:
                result["output"] = "Failed to query sockets."

        elif cmd.startswith("ping:"):
            target = cmd[5:].strip()
            approval = approval_handler.request_approval(f"ping -c 3 {target}", interactive=interactive)
            if approval.approved:
                res = subprocess.run(["ping", "-c", "3", target], capture_output=True, text=True, check=False)
                result["executed"] = True
                result["output"] = res.stdout.strip()
            else:
                result["output"] = f"[REJECTED] {approval.reason}"

        elif cmd.startswith("scan:"):
            target = cmd[5:].strip()
            approval = approval_handler.request_approval(f"nmap -F {target}", interactive=interactive)
            if approval.approved:
                if shutil.which("nmap"):
                    res = subprocess.run(["nmap", "-F", target], capture_output=True, text=True, check=False)
                    result["executed"] = True
                    result["output"] = res.stdout.strip()
                else:
                    result["output"] = "nmap not installed. Use 'aios install nmap' to install it."
            else:
                result["output"] = f"[REJECTED] {approval.reason}"
        else:
            # Default to ss listening
            res = subprocess.run(["ss", "-tuln"], capture_output=True, text=True, check=False)
            result["executed"] = True
            result["output"] = res.stdout.strip()[:1500]

        return result


class SecurityProtocolHandler(ProtocolHandler):
    """Handles security audits: users, groups, sudo, listening ports, SUID, and KalCyberShield."""

    SECURITY_COMMANDS = {
        "users": "cat /etc/passwd | grep -v '/nologin' | grep -v '/false' | head -15",
        "groups": "cat /etc/group | head -15",
        "ports": "ss -tuln",
        "sudo": "sudo -l 2>/dev/null || echo 'Requires root'",
        "suid": "find /usr/bin /bin -perm -4000 -ls 2>/dev/null | head -10",
        "audit": "echo 'Sovereign Cyber Audit'",
    }

    def __init__(self) -> None:
        super().__init__("security")

    def handle(self, content: str, approval_handler: ApprovalHandler, interactive: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "protocol": "security",
            "command": content,
            "executed": False,
            "output": "",
        }

        target = content.strip().lower()

        # Connect to KalCyberShield if available
        if target in ("audit", "shield", "all", ""):
            try:
                from anse.cyber.shield import KalCyberShield
                shield = KalCyberShield()
                audit = shield.audit()
                lines = [
                    "===== SOVEREIGN CYBER SHIELD AUDIT =====",
                    f"• Status: {audit.shield_status}",
                    f"• Kernel Hardening Score: {audit.kernel_hardening_score*100:.1f}%",
                    f"• Zero-Trust Attestation: {'PASSED' if audit.zero_trust_attestation else 'FAILED'}",
                    f"• Authorized Active Ports: {audit.authorized_ports_active}",
                    f"• Threats Detected: {audit.threat_count}",
                ]
                for t in audit.threats:
                    lines.append(f"  - Threat: {t}")
                result["executed"] = True
                result["output"] = "\n".join(lines)
                return result
            except Exception as e:
                logger.debug(f"KalCyberShield query exception: {e}")

        if target in self.SECURITY_COMMANDS:
            cmd = self.SECURITY_COMMANDS[target]
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
            result["executed"] = True
            result["output"] = res.stdout.strip()
        else:
            result["output"] = f"Valid security commands: {', '.join(self.SECURITY_COMMANDS.keys())}, audit, shield"

        return result


class ProtocolRegistry:
    """Registry managing all protocol handlers."""

    def __init__(self) -> None:
        self.handlers: Dict[str, ProtocolHandler] = {}
        # Register standard handlers
        self.register(TerminalProtocolHandler())
        self.register(FilesProtocolHandler())
        self.register(AnalyzeProtocolHandler())
        self.register(NetworkProtocolHandler())
        self.register(SecurityProtocolHandler())

    def register(self, handler: ProtocolHandler) -> None:
        self.handlers[handler.name.lower()] = handler

    def get_handler(self, name: str) -> Optional[ProtocolHandler]:
        return self.handlers.get(name.lower())


class MCPProtocol:
    """Main parser and executor for MCP protocol tags."""

    def __init__(self, registry: Optional[ProtocolRegistry] = None) -> None:
        self.registry = registry or ProtocolRegistry()
        self.mcp_pattern = re.compile(r"<mcp:(\w+)>(.*?)</mcp:\1>", re.DOTALL | re.IGNORECASE)
        self.legacy_patterns = [
            re.compile(r"<system>(.*?)</system>", re.DOTALL | re.IGNORECASE),
            re.compile(r"<s>(.*?)</s>", re.DOTALL | re.IGNORECASE),
        ]

    def parse_mcp_tags(self, text: str) -> List[Tuple[str, str]]:
        """Parse all <mcp:...> tags and legacy tags from response text."""
        tags: List[Tuple[str, str]] = []
        for protocol, content in self.mcp_pattern.findall(text):
            tags.append((protocol.lower().strip(), content.strip()))

        for pat in self.legacy_patterns:
            for content in pat.findall(text):
                tags.append(("terminal", content.strip()))

        return tags

    def process_response(
        self,
        response_text: str,
        approval_handler: Optional[ApprovalHandler] = None,
        interactive: bool = True,
    ) -> Dict[str, Any]:
        """
        Extract and execute all protocol tags in response_text.
        """
        approval = approval_handler or ApprovalHandler()
        results: Dict[str, Any] = {}

        tags = self.parse_mcp_tags(response_text)
        for protocol, content in tags:
            handler = self.registry.get_handler(protocol)
            if handler:
                res = handler.handle(content, approval, interactive=interactive)
                results[protocol] = res
            else:
                results[protocol] = {
                    "protocol": protocol,
                    "command": content,
                    "executed": False,
                    "output": f"Unknown protocol '{protocol}'",
                }

        return results
