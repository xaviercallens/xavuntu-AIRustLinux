#!/usr/bin/env python3
"""
scripts/setup_ai_coding.py — Configure Continue.dev (VS Code) and Aider CLI for Xavuntu AI.

Enables seamless local AI coding with zero cloud dependencies:
1. Configures Continue.dev (~/.continue/config.json) to use Xavuntu Qwen TPU models for chat and autocomplete.
2. Generates the `xavuntu-aider` CLI launcher linking Aider directly to our OpenAI-compatible gateway.
3. Verifies endpoint connectivity and displays developer instructions.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

DEFAULT_GATEWAY_URL = os.environ.get("OPENAI_API_BASE", "http://127.0.0.1:5000/v1")


def generate_continue_config(gateway_url: str = DEFAULT_GATEWAY_URL) -> Path:
    """Creates or updates ~/.continue/config.json for VS Code."""
    continue_dir = Path.home() / ".continue"
    continue_dir.mkdir(parents=True, exist_ok=True)
    config_file = continue_dir / "config.json"

    config_data: Dict[str, Any] = {
        "models": [
            {
                "title": "Xavuntu Qwen 14B TPU Reasoner",
                "provider": "openai",
                "model": "gwaya-qwen:14b-t4",
                "apiBase": gateway_url,
                "apiKey": "xavuntu-sovereign",
                "contextLength": 4096,
                "completionOptions": {
                    "temperature": 0.7,
                },
            },
            {
                "title": "Xavuntu Qwen 3.8 Quant (Fast Reflex)",
                "provider": "openai",
                "model": "gwaya-qwen:3.8-quant",
                "apiBase": gateway_url,
                "apiKey": "xavuntu-sovereign",
                "contextLength": 4096,
            },
            {
                "title": "Qwen 2.5 Coder 1.5B",
                "provider": "openai",
                "model": "qwen2.5-coder:1.5b",
                "apiBase": gateway_url,
                "apiKey": "xavuntu-sovereign",
                "contextLength": 4096,
            },
        ],
        "tabAutocompleteModel": {
            "title": "Qwen 2.5 Coder Autocomplete",
            "provider": "openai",
            "model": "qwen2.5-coder:1.5b",
            "apiBase": gateway_url,
            "apiKey": "xavuntu-sovereign",
        },
        "customCommands": [
            {
                "name": "shield",
                "prompt": "Audit this code against KalCyberShield zero-trust security standards and point out any vulnerabilities:\n{{{ input }}}",
                "description": "Run KalCyberShield security audit",
            },
            {
                "name": "tpu-opt",
                "prompt": "Optimize this algorithm for Google TPU ReBAR memory alignment and systolic hardware tiling:\n{{{ input }}}",
                "description": "Optimize for TPU systolic architecture",
            },
            {
                "name": "rust-kernel",
                "prompt": "Convert this routine to memory-safe, no_std Rust kernel code:\n{{{ input }}}",
                "description": "Port to RunuX Rust Kernel",
            },
        ],
        "allowAnonymousTelemetry": False,
        "docs": [],
    }

    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)

    return config_file


def generate_aider_launcher(gateway_url: str = DEFAULT_GATEWAY_URL, target_bin: str = "/usr/local/bin/xavuntu-aider") -> Path:
    """Creates a convenient launcher for Aider CLI pointing to Xavuntu."""
    dest = Path(target_bin)
    content = f"""#!/bin/bash
# xavuntu-aider — Launch Aider CLI with local Xavuntu Qwen TPU models
export OPENAI_API_BASE="{gateway_url}"
export OPENAI_API_KEY="xavuntu-sovereign"

MODEL="${{1:-openai/gwaya-qwen:14b-t4}}"
shift 2>/dev/null || true

if ! command -v aider &>/dev/null; then
    echo "Aider CLI is not installed. Install with: pip install aider-chat"
    exit 1
fi

exec aider --model "$MODEL" --openai-api-base "{gateway_url}" --no-auto-commits "$@"
"""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        dest.chmod(0o755)
    except PermissionError:
        # Fallback to local user bin
        dest = Path.home() / ".local" / "bin" / "xavuntu-aider"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        dest.chmod(0o755)

    return dest


def check_status(gateway_url: str = DEFAULT_GATEWAY_URL) -> None:
    """Verifies that the gateway is responding to OpenAI standard queries."""
    import urllib.request
    print(f"\n\033[1;36m=== Xavuntu AI Coding Integration Status ===\033[0m")
    print(f"  • Gateway URL: {gateway_url}")

    try:
        req = urllib.request.Request(f"{gateway_url}/models")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id") for m in data.get("data", [])]
            print(f"  • \033[1;32mGateway Online:\033[0m Available Models: {', '.join(models)}")
    except Exception as e:
        print(f"  • \033[1;33mGateway Check:\033[0m {e} (Ensure web/server.py or gwaya_v3_daemon.py is running)")

    cont_file = Path.home() / ".continue" / "config.json"
    if cont_file.exists():
        print(f"  • \033[1;32mContinue.dev Config:\033[0m {cont_file}")
    else:
        print(f"  • \033[1;33mContinue.dev Config:\033[0m Not yet configured (run with --continue)")

    aider_bin = shutil.which("xavuntu-aider") or (Path.home() / ".local" / "bin" / "xavuntu-aider")
    if os.path.exists(str(aider_bin)):
        print(f"  • \033[1;32mAider Launcher:\033[0m {aider_bin}")
    else:
        print(f"  • \033[1;33mAider Launcher:\033[0m Not yet configured (run with --aider)")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure Continue.dev and Aider for Xavuntu AI")
    parser.add_argument("--url", type=str, default=DEFAULT_GATEWAY_URL, help="Gateway URL (e.g. http://127.0.0.1:5000/v1)")
    parser.add_argument("--continue-config", action="store_true", help="Generate Continue.dev config")
    parser.add_argument("--aider", action="store_true", help="Generate Aider CLI launcher")
    parser.add_argument("--all", action="store_true", help="Generate all configurations")
    parser.add_argument("--status", action="store_true", help="Check gateway and configuration status")

    args = parser.parse_args()

    if args.status:
        check_status(args.url)
        return

    run_all = args.all or (not args.continue_config and not args.aider)

    if run_all or args.continue_config:
        cfg = generate_continue_config(args.url)
        print(f"✓ Continue.dev configured: {cfg}")

    if run_all or args.aider:
        ldr = generate_aider_launcher(args.url)
        print(f"✓ Aider launcher generated: {ldr}")

    print("\n\033[1;32m🎉 AI Coding Setup Complete!\033[0m")
    print(f"  1. In VS Code: Install the 'Continue' extension (it will automatically use {Path.home() / '.continue' / 'config.json'})")
    print(f"  2. In Terminal: Use 'xavuntu-aider' to pair-program with local Qwen models on your git repos.")


if __name__ == "__main__":
    main()
