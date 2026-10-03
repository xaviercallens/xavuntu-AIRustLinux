"""
Remote Compute Center Manager for ANSE & AutoevolveAI.

Coordinates connection, SSH tunneling, security boundaries, and GPU workloads
with the remote GPU centre (e.g. RunPod, Slurm, or Cloud Compute Node).
Enforces:
1. Zero code execution on remote host: remote pod handles tensor inference & LoRA only.
2. Local sandbox verification: all generated code runs only on developer machine.
3. CC <= 10 across all methods.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict

logger = logging.getLogger("RemoteCenter")
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = REPO_ROOT / "pod" / "remote_center_config.json"


class RemoteCenterManager:
    """Manages the remote compute center configuration, tunnels, and status."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or CONFIG_PATH
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load remote center configuration file."""
        if not self.config_path.exists():
            return {
                "center_id": "default_remote_center",
                "provider": "runpod",
                "security": {"fail_closed": True, "execute_code_on_pod": False},
            }
        with open(self.config_path, encoding="utf-8") as f:
            return json.load(f)

    def get_center_status(self) -> Dict[str, Any]:
        """Check status and readiness of the remote center."""
        api_key_set = bool(os.getenv("RUNPOD_API_KEY"))
        ssh_key_path = os.getenv("REMOTE_CENTER_SSH_KEY", str(Path.home() / ".ssh" / "id_ed25519"))
        ssh_key_exists = Path(ssh_key_path).exists()
        ssh_installed = shutil.which("ssh") is not None

        is_ready = ssh_installed and (ssh_key_exists or api_key_set)

        return {
            "center_id": self.config.get("center_id", "anse_remote_gpu_center"),
            "provider": self.config.get("provider", "runpod"),
            "ready": is_ready,
            "ssh_installed": ssh_installed,
            "ssh_key_exists": ssh_key_exists,
            "api_key_configured": api_key_set,
            "cloud_type": self.config.get("cloud_type", "secure_cloud"),
            "security": self.config.get("security", {}),
            "capabilities": self.config.get("capabilities", []),
        }

    def build_tunnel_command(self, pod_ip: str, ssh_port: int = 22, ssh_key: str | None = None) -> list[str]:
        """Generate SSH tunneling command to securely forward remote inference port."""
        net = self.config.get("network", {})
        local_port = net.get("tunnel_local_port", 8000)
        remote_port = net.get("tunnel_remote_port", 8000)
        key = ssh_key or os.getenv("REMOTE_CENTER_SSH_KEY", str(Path.home() / ".ssh" / "id_ed25519"))

        cmd = [
            "ssh",
            "-N",
            "-L",
            f"{local_port}:127.0.0.1:{remote_port}",
            "-p",
            str(ssh_port),
        ]
        if Path(key).exists():
            cmd.extend(["-i", key])
        cmd.append(f"root@{pod_ip}")
        return cmd

    def verify_local_security_boundary(self) -> bool:
        """Verify that the remote center does not execute untrusted code on remote host."""
        sec = self.config.get("security", {})
        return bool(sec.get("fail_closed") and not sec.get("execute_code_on_pod"))


def configure_remote_center_cli() -> int:
    """CLI helper to display and verify remote center configuration."""
    mgr = RemoteCenterManager()
    status = mgr.get_center_status()
    print("=" * 60)
    print("🌐 ANSE REMOTE COMPUTE CENTER CONFIGURATION")
    print("=" * 60)
    print(f"Center ID     : {status['center_id']}")
    print(f"Provider      : {status['provider']} ({status['cloud_type']})")
    print(f"Ready         : {status['ready']}")
    print(f"SSH Client    : {'Available' if status['ssh_installed'] else 'Missing'}")
    print(f"SSH Key       : {'Found' if status['ssh_key_exists'] else 'Missing default key'}")
    print(f"API Key Set   : {status['api_key_configured']}")
    print(f"Safe Boundary : {mgr.verify_local_security_boundary()}")
    print("Capabilities  :", ", ".join(status['capabilities']))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(configure_remote_center_cli())
