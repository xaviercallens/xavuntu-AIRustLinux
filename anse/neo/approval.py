"""
anse/neo/approval.py — Command Approval Handler for Neo-AI & GWAYA v3.

Enforces zero-trust command execution safety:
1. GWAYA System 1 pre-screening (blocking adversarial commands).
2. Explicit human-in-the-loop approval ([Enter/n]).
3. Configurable auto-approval for non-destructive read-only queries.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("anse.neo.approval")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [NEO-APPROVAL] %(message)s")


@dataclass
class CommandApprovalResult:
    command: str
    approved: bool
    risk_level: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL_BLOCKED"
    reason: str
    screened_by_gwaya_s1: bool
    adversarial_heuristic: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ApprovalHandler:
    """
    Handles user confirmation and security pre-screening before command execution.
    """

    # GWAYA System 1 Adversarial Heuristics (blocks catastrophic or exploitative commands)
    BLOCK_HEURISTICS: List[Tuple[str, str]] = [
        (r"/dev/tcp/\d+\.\d+\.\d+\.\d+", "REVERSE_SHELL_RAW_TCP"),
        (r"bash\s+-i\s+>&", "INTERACTIVE_REVERSE_BASH"),
        (r"nc\s+.*-e\s+/bin/", "NETCAT_REVERSE_EXEC"),
        (r"mkfifo\s+/tmp/.*cat\s+/tmp/", "FIFO_PIPE_EXPLOIT"),
        (r"rm\s+-rf\s+/(?:\s|$)", "ROOT_FILESYSTEM_DESTRUCTION"),
        (r":\(\)\{\s*:\s*\|\s*:\s*&\s*\};:", "FORK_BOMB_RESOURCE_EXHAUSTION"),
        (r"dd\s+if=/dev/zero\s+of=/dev/sd[a-z]", "RAW_BLOCK_OVERWRITE"),
        (r"chmod\s+-R\s+777\s+/(?:etc|boot|sys)", "CRITICAL_SYSTEM_UNPROTECT"),
        (r">\s*/etc/(?:passwd|shadow)", "CREDENTIAL_DATABASE_OVERWRITE"),
    ]

    HIGH_RISK_KEYWORDS = [
        "mkfs", "fdisk", "parted", "wipefs", "reboot", "shutdown", "poweroff", "iptables -F"
    ]

    READ_ONLY_PREFIXES = [
        "ls", "cat", "echo", "pwd", "whoami", "uname", "uptime", "free", "df", "ps", "top", "ss", "ip", "netstat"
    ]

    def __init__(self, require_approval: bool = True, auto_approve_all: bool = False) -> None:
        self.require_approval = require_approval
        self.auto_approve_all = auto_approve_all

    def screen_command(self, command: str) -> Tuple[bool, str, Optional[str]]:
        """
        Evaluate command with GWAYA System 1 Semantic LSM.
        Returns: (is_safe, risk_level, matched_heuristic)
        """
        clean_cmd = command.strip()

        # 1. Check GWAYA Block Heuristics
        for pattern, heuristic_name in self.BLOCK_HEURISTICS:
            if re.search(pattern, clean_cmd, re.IGNORECASE):
                logger.warning(f"GWAYA System 1 BLOCKED adversarial command: {heuristic_name} in '{clean_cmd}'")
                return False, "CRITICAL_BLOCKED", heuristic_name

        # 2. Check High Risk
        for kw in self.HIGH_RISK_KEYWORDS:
            if kw in clean_cmd:
                return True, "HIGH", None

        # 3. Check Read-Only
        first_token = clean_cmd.split()[0] if clean_cmd.split() else ""
        if first_token in self.READ_ONLY_PREFIXES and ">" not in clean_cmd and "|" not in clean_cmd:
            return True, "LOW", None

        return True, "MEDIUM", None

    def request_approval(self, command: str, interactive: bool = True) -> CommandApprovalResult:
        """
        Evaluate safety and request interactive approval if required.
        """
        is_safe, risk_level, heuristic = self.screen_command(command)

        if not is_safe:
            return CommandApprovalResult(
                command=command,
                approved=False,
                risk_level="CRITICAL_BLOCKED",
                reason=f"Blocked by GWAYA System 1 Guard: Detected {heuristic}",
                screened_by_gwaya_s1=True,
                adversarial_heuristic=heuristic,
            )

        # If auto-approval is explicitly enabled
        if self.auto_approve_all or not self.require_approval:
            return CommandApprovalResult(
                command=command,
                approved=True,
                risk_level=risk_level,
                reason="Auto-approved by configuration",
                screened_by_gwaya_s1=True,
            )

        # Interactive human confirmation
        if interactive:
            print(f"\n\033[93mneo >\033[0m \033[1m{command}\033[0m")
            print(f"  \033[94m↳ Risk Level:\033[0m {risk_level} (GWAYA System 1: PASS)")
            try:
                ans = input("  \033[92m↳ Execute this command? [Enter/y/n]: \033[0m").strip().lower()
                if ans in ("", "y", "yes"):
                    return CommandApprovalResult(
                        command=command,
                        approved=True,
                        risk_level=risk_level,
                        reason="Confirmed by user",
                        screened_by_gwaya_s1=True,
                    )
                else:
                    return CommandApprovalResult(
                        command=command,
                        approved=False,
                        risk_level=risk_level,
                        reason="Declined by user",
                        screened_by_gwaya_s1=True,
                    )
            except (KeyboardInterrupt, EOFError):
                print()
                return CommandApprovalResult(
                    command=command,
                    approved=False,
                    risk_level=risk_level,
                    reason="Aborted by user interrupt",
                    screened_by_gwaya_s1=True,
                )
        else:
            # Non-interactive mode without auto-approve defaults to safe refusal
            return CommandApprovalResult(
                command=command,
                approved=False,
                risk_level=risk_level,
                reason="Non-interactive execution requires auto_approve flag",
                screened_by_gwaya_s1=True,
            )
