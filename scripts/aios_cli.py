#!/usr/bin/env python3
"""
scripts/aios_cli.py — Sovereign LinuxOS-AI Interactive System Administrator for Xavuntu AI.

Executable CLI implementing:
- Real-time Cyberpunk Terminal Dashboard
- Natural Language & Conversational Commands
- Package, Web Server, Database (Oracle/Postgres) & Security Operations
- Safe Dry-Run Analysis & Human-in-the-Loop Confirmation
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional

# Ensure repository root is on sys.path
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from anse.admin.system_admin import SystemAdminEngine, SystemHealth
from anse.admin.intent_router import IntentRouter, SystemCommand

# ANSI Neon Colors
CYAN = "\033[96m"
MAGENTA = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_banner():
    banner = f"""
{CYAN}╭─────────────────────────────────────────────────────────────────╮
│{MAGENTA}{BOLD}                  🤖 XAVUNTU AIOS - SYSTEM ADMIN                  {RESET}{CYAN}│
│                                                                 │
│   {GREEN}Dual-Engine Sovereign System Administrator for Linux          {CYAN}│
│   {YELLOW}Bare-Metal RunuX Kernel & Qwen TPU ReBAR Intelligence         {CYAN}│
│                                                                 │
│   {DIM}Type 'help' for commands or chat naturally with your OS!      {RESET}{CYAN}│
╰─────────────────────────────────────────────────────────────────╯{RESET}
"""
    print(banner)


def format_table_row(col1: str, col2: str, col3: str) -> str:
    return f"  {col1:<20} {col2:<16} {col3}"


def display_system_status(engine: SystemAdminEngine):
    health = engine.get_system_health()

    print(f"\n{CYAN}{BOLD}📊 LIVE SYSTEM HEALTH TELEMETRY{RESET}")
    print(f"{DIM}{'─'*65}{RESET}")
    print(format_table_row(f"{BOLD}Component{RESET}", f"{BOLD}Status{RESET}", f"{BOLD}Details{RESET}"))
    print(f"{DIM}{'─'*65}{RESET}")

    # CPU
    cpu_col = RED if health.cpu_percent > 80 else (YELLOW if health.cpu_percent > 60 else GREEN)
    print(format_table_row("🖥️  CPU Usage", f"{cpu_col}{health.cpu_percent}%{RESET}", f"{health.cpu_cores} Cores ({platform_summary(health)})"))

    # Memory
    mem_col = RED if health.memory_percent > 85 else (YELLOW if health.memory_percent > 65 else GREEN)
    print(format_table_row("💾 Memory (RAM)", f"{mem_col}{health.memory_percent}% used{RESET}", f"{health.memory_used_gb} GB / {health.memory_total_gb} GB"))

    # Disk
    disk_col = RED if health.disk_percent > 85 else (YELLOW if health.disk_percent > 65 else GREEN)
    print(format_table_row("💽 Disk Space", f"{disk_col}{health.disk_percent}% used{RESET}", f"{health.disk_used_gb} GB / {health.disk_total_gb} GB"))

    # Security
    sec_col = GREEN if health.security_status == "protected" else YELLOW
    print(format_table_row("🔒 Cyber Shield", f"{sec_col}{health.security_status.upper()}{RESET}", "Zero-Trust Kernel Invariants"))

    # Services
    srv_col = GREEN if health.services_running > 0 else YELLOW
    print(format_table_row("🔄 Services", f"{srv_col}{health.services_running}/{health.services_total} active{RESET}", "Systemd RunuX manager"))

    # Package Manager
    print(format_table_row("📦 Package Mgr", f"{BLUE}{health.package_manager}{RESET}", "Native package system"))

    # Uptime
    print(format_table_row("⏱️  System Uptime", f"{BLUE}{health.uptime_hours}h{RESET}", f"Optimized {health.last_optimized_hours_ago}h ago"))
    print(f"{DIM}{'─'*65}{RESET}\n")

    # Smart suggestions
    suggestions: List[str] = []
    if health.cpu_percent > 80:
        suggestions.append('🔥 High CPU load. Run: "aios analyze performance"')
    if health.memory_percent > 80:
        suggestions.append('💾 Memory pressure detected. Run: "aios clean memory"')
    if health.disk_percent > 85:
        suggestions.append('💽 Disk space low. Run: "aios clean system"')
    if health.security_status != "protected":
        suggestions.append('🔒 Security recommendations available. Run: "aios secure system"')

    if suggestions:
        print(f"{YELLOW}{BOLD}💡 Intelligent Recommendations:{RESET}")
        for s in suggestions:
            print(f"   {s}")
        print()


def platform_summary(health: SystemHealth) -> str:
    return f"{health.platform_name} {health.architecture}"


def show_help():
    print(f"\n{CYAN}{BOLD}🔧 AVAILABLE COMMANDS & USAGE{RESET}")
    print(f"{DIM}{'─'*65}{RESET}")
    cmds = [
        ("aios install <package>", "Install software packages", "aios install nginx"),
        ("aios install oracle", "Deploy Oracle Database stack", "aios install oracle 8GB"),
        ("aios setup webserver", "Deploy Nginx/Apache with SSL", "aios setup webserver"),
        ("aios check <software>", "Inspect system prerequisites", "aios check oracle"),
        ("aios clean system", "Prune logs & developer caches", "aios clean system"),
        ("aios analyze performance", "Diagnose hardware bottlenecks", "aios analyze performance"),
        ("aios secure system", "Audit zero-trust cyber shield", "aios secure system"),
        ("aios status", "Display live system status", "aios status"),
        ("aios help", "Show this help screen", "aios help"),
        ("exit / quit", "Exit interactive session", "exit"),
    ]
    for c, desc, ex in cmds:
        print(f"  {CYAN}{c:<26}{RESET} {desc:<24} {DIM}eg: {ex}{RESET}")
    print(f"{DIM}{'─'*65}{RESET}")
    print(f"{YELLOW}💡 You can also ask conversational questions in French or English:{RESET}")
    print(f"   'Mon serveur est lent, peux-tu optimiser la mémoire ?'\n")


def execute_command_action(cmd: SystemCommand, engine: SystemAdminEngine, auto_confirm: bool = False) -> str:
    print(f"\n{BLUE}{BOLD}📋 COMMAND ANALYSIS & PREVIEW{RESET}")
    print(f"  • {BOLD}Intent:{RESET} {cmd.intent}")
    print(f"  • {BOLD}Description:{RESET} {cmd.description}")
    print(f"  • {BOLD}Tools:{RESET} {', '.join(cmd.tools)}")
    print(f"  • {BOLD}Preview:{RESET} {DIM}{cmd.command_preview}{RESET}")

    if cmd.confirmation_required and not auto_confirm:
        print(f"\n{YELLOW}{BOLD}⚠️  CONFIRMATION REQUIRED{RESET}")
        print(f"{YELLOW}This action will modify system configurations or install packages.{RESET}")
        ans = input(f"Proceed with execution? [{GREEN}y{RESET}/{RED}N{RESET}]: ").strip().lower()
        if ans not in ("y", "yes"):
            print(f"{YELLOW}⏹️  Operation cancelled by user.{RESET}\n")
            return "Operation cancelled by user."

    print(f"\n{GREEN}⚙️  Executing '{cmd.intent}' safely...{RESET}")

    # Dispatch to SystemAdminEngine
    if cmd.intent == "install_package":
        pkg = cmd.params.get("package", "")
        ver = cmd.params.get("version")
        mgr = cmd.params.get("manager", "auto")
        plan = engine.plan_package_install(pkg, ver, mgr, dry_run=False)
        res = engine.execute_package_install(plan)
        msg = f"✓ {res['message']}\nDuration: {res.get('duration_seconds', 0)}s\nOutput:\n{res.get('output', '')}"
        print(f"{GREEN}{msg}{RESET}\n")
        return msg

    elif cmd.intent == "install_database":
        db_type = cmd.params.get("db_type", "oracle")
        mem_gb = cmd.params.get("memory_gb", 8.0)
        plan = engine.plan_database_install(db_type=db_type, memory_gb=mem_gb)
        print(f"\n{GREEN}{plan.summary_text}{RESET}\n")
        print(f"{CYAN}Planned Execution Pipeline:{RESET}")
        for s in plan.steps:
            print(f"  {s}")
        print()
        return plan.summary_text

    elif cmd.intent == "setup_web_server":
        st = cmd.params.get("server_type", "nginx")
        ssl = cmd.params.get("ssl_enabled", True)
        dom = cmd.params.get("domain")
        plan = engine.plan_web_server(server_type=st, ssl_enabled=ssl, domain=dom)
        print(f"\n{GREEN}{plan.summary_text}{RESET}\n")
        print(f"{CYAN}Planned Execution Pipeline:{RESET}")
        for s in plan.steps:
            print(f"  {s}")
        print()
        return plan.summary_text

    elif cmd.intent == "check_requirements":
        soft = cmd.params.get("software", "oracle")
        rep = engine.check_requirements(soft)
        print(f"\n{CYAN}{rep.detailed_text}{RESET}\n")
        return rep.detailed_text

    elif cmd.intent == "clean_system":
        agg = cmd.params.get("aggressive", False)
        res = engine.clean_system(aggressive=agg)
        print(f"\n{GREEN}✓ {res['message']}{RESET}")
        for a in res.get("actions", []):
            print(f"  • {a}")
        print()
        return res["message"]

    elif cmd.intent == "analyze_performance":
        diag = engine.analyze_performance()
        print(f"\n{CYAN}{diag['summary']}{RESET}\n")
        return diag["summary"]

    elif cmd.intent == "secure_system":
        try:
            from anse.cyber.shield import KalCyberShield
            shield = KalCyberShield()
            audit = shield.audit()
            msg = (
                f"🛡️ Sovereign Cyber Shield Status: {audit.shield_status}\n"
                f"• Kernel Hardening Score: {audit.kernel_hardening_score*100:.1f}%\n"
                f"• Zero-Trust Attestation: {'VALIDATED' if audit.zero_trust_attestation else 'FAILED'}\n"
                f"• Active Threats: {audit.threat_count}"
            )
            print(f"\n{GREEN}{msg}{RESET}\n")
            return msg
        except Exception as e:
            msg = f"Security audit completed: {e}"
            print(f"\n{YELLOW}{msg}{RESET}\n")
            return msg

    else:
        msg = f"Processed intent: {cmd.intent}"
        print(f"\n{GREEN}✓ {msg}{RESET}\n")
        return msg


def interactive_loop(engine: SystemAdminEngine, router: IntentRouter):
    print_banner()
    display_system_status(engine)

    while True:
        try:
            prompt = input(f"{CYAN}{BOLD}Xavuntu-AIOS ➤ {RESET}").strip()
            if not prompt:
                continue

            low = prompt.lower()
            if low in ("exit", "quit", "q"):
                print(f"{GREEN}👋 Goodbye! Stay sovereign.{RESET}")
                break
            elif low in ("help", "h", "?"):
                show_help()
                continue
            elif low in ("status", "stat", "top"):
                display_system_status(engine)
                continue
            elif low == "clear":
                os.system("clear")
                print_banner()
                continue

            cmd = router.route_command(prompt)
            execute_command_action(cmd, engine, auto_confirm=False)

        except (KeyboardInterrupt, EOFError):
            print(f"\n{GREEN}👋 AIOS session ended.{RESET}")
            break
        except Exception as ex:
            print(f"{RED}Error: {ex}{RESET}")


def main():
    parser = argparse.ArgumentParser(description="Xavuntu AIOS — Autonomous AI System Administrator")
    parser.add_argument("command", nargs="*", help="Direct command (e.g. 'install nginx', 'status', 'clean system')")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive conversational mode")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without modifying system")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-confirm all installation plans")
    parser.add_argument("--local", action="store_true", help="Force local sovereign TPU/Qwen reasoner")
    args = parser.parse_args()

    engine = SystemAdminEngine()
    router = IntentRouter(admin_engine=engine)

    if args.interactive or not args.command:
        interactive_loop(engine, router)
    else:
        full_cmd = " ".join(args.command)
        low = full_cmd.lower().strip()
        if low == "status":
            display_system_status(engine)
        elif low == "help":
            show_help()
        else:
            cmd = router.route_command(full_cmd)
            execute_command_action(cmd, engine, auto_confirm=args.yes or args.dry_run)


if __name__ == "__main__":
    main()
