#!/usr/bin/env python3
"""
scripts/neo_ai_cli.py — Sovereign Neo-AI Terminal Interface for Xavuntu AI & GWAYA v3.

Provides a cyberpunk interactive shell and one-shot CLI execution for Neo-AI:
- Runs locally against open-weights models (gwaya-qwen:14b-t4 in TPU ReBAR memory).
- Pre-screens commands through GWAYA System 1 zero-trust LSM filter.
- Injects durable AttentionMatter Redis LTM context.
- Dispatches MCP protocol tags (terminal, files, analyze, network, security).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from anse.neo.core import NeoAI, NeoConfig

# ANSI Styling for Cyberpunk Neon Aesthetics
CYAN = "\033[38;5;51m"
MAGENTA = "\033[38;5;198m"
GREEN = "\033[38;5;48m"
YELLOW = "\033[38;5;220m"
RED = "\033[38;5;196m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

BANNER = f"""{CYAN}{BOLD}
 ███╗   ██╗███████╗ ██████╗       █████╗ ██╗
 ████╗  ██║██╔════╝██╔═══██╗     ██╔══██╗██║
 ██╔██╗ ██║█████╗  ██║   ██║     ███████║██║
 ██║╚██╗██║██╔══╝  ██║   ██║     ██╔══██║██║
 ██║ ╚████║███████╗╚██████╔╝     ██║  ██║██║
 ╚═╝  ╚═══╝╚══════╝ ╚═════╝      ╚═╝  ╚═╝╚═╝{MAGENTA}  SOVEREIGN LINUX AI{RESET}
{DIM}═══════════════════════════════════════════════════════════════════════{RESET}
  {GREEN}Local Engine:{RESET}   Ollama TPU ReBAR (127.0.0.1:11434)
  {GREEN}Model Fleet:{RESET}    Qwen 14B Doctoral Reasoner / 3.8 Quant
  {GREEN}Memory Grid:{RESET}    AttentionMatter Redis LTM (Port 6379)
  {GREEN}Zero-Trust:{RESET}     GWAYA System 1 Semantic LSM Pre-Screening
  {GREEN}Protocols:{RESET}      <mcp:terminal>, <mcp:files>, <mcp:analyze>, <mcp:network>, <mcp:security>
{DIM}═══════════════════════════════════════════════════════════════════════{RESET}
"""


def load_config(config_path: Optional[str] = None) -> NeoConfig:
    """Load configuration from YAML file or return defaults."""
    default_paths = [
        config_path,
        str(PROJECT_ROOT / "config" / "neo_config.yaml"),
        "/etc/neo/config.yaml",
        os.path.expanduser("~/.config/neo/config.yaml"),
    ]

    for p in default_paths:
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return NeoConfig.from_dict(data)
            except Exception as e:
                print(f"{YELLOW}[WARN] Failed to parse config {p}: {e}{RESET}")

    return NeoConfig()


def print_status(neo: NeoAI) -> None:
    """Prints diagnostic status of local inference, Redis LTM, and security."""
    print(f"\n{BOLD}{CYAN}=== Neo-AI Sovereign Diagnostics ==={RESET}")
    status = neo.check_ollama_status()
    if status.get("online"):
        print(f"  {GREEN}● Ollama Status:{RESET} ONLINE ({status.get('url')})")
        print(f"  {GREEN}● Available Models:{RESET} {', '.join(status.get('models', []))}")
        print(f"  {GREEN}● Active Target:{RESET} {status.get('active_model')}")
    else:
        print(f"  {RED}✖ Ollama Status:{RESET} OFFLINE ({status.get('error')})")

    if neo.memory_manager:
        connected = neo.memory_manager.is_redis_connected
        state = f"{GREEN}ONLINE (Connected){RESET}" if connected else f"{YELLOW}IN-MEMORY (Redis offline){RESET}"
        print(f"  {GREEN}● AttentionMatter LTM:{RESET} {state}")
        all_facts = neo.memory_manager.get_all_facts()
        print(f"  {GREEN}● Durable Facts:{RESET} {len(all_facts)} stored")
    else:
        print(f"  {YELLOW}● AttentionMatter LTM:{RESET} Disabled")

    print(f"  {GREEN}● GWAYA System 1 Guard:{RESET} ENABLED (Zero-Trust Heuristics Active)")
    print(f"  {GREEN}● Approval Required:{RESET} {neo.config.require_approval}")
    print()


def interactive_repl(neo: NeoAI, stream_tokens: bool = True) -> None:
    """Interactive Cyberpunk REPL for continuous terminal interaction."""
    print(BANNER)
    print(f"{DIM}Type your question, task, or command. Use {CYAN}/status{DIM}, {CYAN}/reset{DIM}, {CYAN}/help{DIM}, or {CYAN}/exit{DIM}.{RESET}\n")

    while True:
        try:
            prompt_str = f"{CYAN}{BOLD}neo{MAGENTA}[ai]{RESET} {BOLD}>{RESET} "
            user_input = input(prompt_str).strip()

            if not user_input:
                continue

            # Command handling
            if user_input in ("/exit", "exit", "quit", ":q"):
                print(f"{MAGENTA}Exiting Neo-AI. Sovereign session terminated.{RESET}")
                break
            elif user_input == "/status":
                print_status(neo)
                continue
            elif user_input == "/reset":
                neo.reset_session()
                print(f"{GREEN}Session history and STM context cleared.{RESET}")
                continue
            elif user_input.startswith("/model"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    neo.config.model = parts[1].strip()
                    print(f"{GREEN}Active model set to '{neo.config.model}'.{RESET}")
                else:
                    print(f"{YELLOW}Current model: {neo.config.model}{RESET}")
                continue
            elif user_input == "/help":
                print(f"\n{BOLD}Neo-AI Command Guide:{RESET}")
                print("  Ask plain English tasks: 'Check disk space', 'List open ports', 'Analyze system'")
                print("  Built-in Slash Commands:")
                print("    /status       - Show Ollama, models, and Redis LTM status")
                print("    /reset        - Clear active conversation history")
                print("    /model <name> - Switch target model")
                print("    /help         - Display this help message")
                print("    /exit         - Quit session\n")
                continue

            # Execute query
            print(f"{DIM}Consulting sovereign reasoner...{RESET}")
            if stream_tokens:
                print(f"{MAGENTA}{BOLD}Neo:{RESET} ", end="", flush=True)

                def token_cb(token: str) -> None:
                    sys.stdout.write(token)
                    sys.stdout.flush()

                res = neo.query(
                    user_prompt=user_input,
                    interactive=True,
                    stream=True,
                    on_chunk=token_cb,
                )
                print()  # Final newline
            else:
                res = neo.query(
                    user_prompt=user_input,
                    interactive=True,
                    stream=False,
                )
                print(f"{MAGENTA}{BOLD}Neo:{RESET} {res['response']}")

            # Summary stats
            lat = res.get("latency_ms", 0.0)
            tok_saved = res.get("tokens_saved", 0)
            print(f"{DIM}[Model: {res.get('model')} | Latency: {lat}ms | LTM Saved: {tok_saved} tokens]{RESET}\n")

        except KeyboardInterrupt:
            print(f"\n{YELLOW}(Interrupt received. Use /exit or Ctrl+D to exit){RESET}\n")
        except EOFError:
            print(f"\n{MAGENTA}Session terminated.{RESET}")
            break
        except Exception as e:
            print(f"\n{RED}[ERROR] Query failed: {e}{RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Neo-AI Sovereign Terminal Assistant for Xavuntu AI & GWAYA v3")
    parser.add_argument("-q", "--query", type=str, help="Single query to execute non-interactively")
    parser.add_argument("-m", "--model", type=str, help="Override target LLM model")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve commands without interactive confirmation")
    parser.add_argument("--no-stream", action="store_true", help="Disable token streaming output")
    parser.add_argument("-c", "--config", type=str, help="Path to custom config YAML")
    parser.add_argument("--status", action="store_true", help="Print system status and exit")

    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.model:
        cfg.model = args.model
    if args.yes:
        cfg.auto_approve_all = True
        cfg.require_approval = False

    neo = NeoAI(config=cfg)

    if args.status:
        print_status(neo)
        return

    if args.query:
        # Non-interactive one-shot query
        stream = not args.no_stream
        if stream:
            def token_cb(token: str) -> None:
                sys.stdout.write(token)
                sys.stdout.flush()
            res = neo.query(args.query, interactive=not args.yes, stream=True, on_chunk=token_cb)
            print()
        else:
            res = neo.query(args.query, interactive=not args.yes, stream=False)
            print(res["response"])
    else:
        # Interactive REPL
        interactive_repl(neo, stream_tokens=not args.no_stream)


if __name__ == "__main__":
    main()
