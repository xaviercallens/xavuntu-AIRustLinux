#!/usr/bin/env python3
"""
scripts/kal_cyber_guard.py — Standalone Cyber Protection Daemon & CLI for Xavuntu KAL.

Commands:
- status: Print full cyber protection telemetry (ports, threats, hardening, zero-trust).
- harden: Apply kernel sysctl hardening rules immediately.
- lockdown: Engage defensive lockdown.
- daemon: Run continuous security monitoring loop.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

# Ensure repository root is on sys.path
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from anse.cyber.shield import KalCyberShield

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [CYBER-GUARD] %(message)s")
logger = logging.getLogger("kal_cyber_guard")


def cmd_status(shield: KalCyberShield) -> int:
    telemetry = shield.audit()
    print("=" * 60)
    print("🛡️  KAL 9000 // SOVEREIGN CYBER PROTECTION SHIELD TELEMETRY")
    print("=" * 60)
    print(f"Status:                     {telemetry.shield_status}")
    print(f"Zero-Trust Attestation:     {'PASS (Verified)' if telemetry.zero_trust_attestation else 'FAIL'}")
    print(f"Kernel Hardening Score:     {telemetry.kernel_hardening_score * 100:.1f}%")
    print(f"Threat Count:               {telemetry.threat_count}")
    print(f"Active Authorized Ports:    {telemetry.authorized_ports_active}")
    print(f"Unauthorized Ports:         {telemetry.unauthorized_ports}")
    print(f"Blocked IPs:                {telemetry.blocked_ips_count}")
    print(f"Audit Latency:              {telemetry.last_audit_duration_ms:.2f} ms")
    if telemetry.threats:
        print("\n[ACTIVE THREAT DETAILS]")
        for t in telemetry.threats:
            print(f"  • {t}")
    print("=" * 60)
    return 0


def cmd_harden(shield: KalCyberShield) -> int:
    print("Applying sovereign kernel hardening policies...")
    results = shield.apply_hardening()
    for param, ok in results.items():
        print(f"  {'✓' if ok else '✗'} {param}")
    print("Kernel hardening update complete.")
    return 0


def cmd_lockdown(shield: KalCyberShield) -> int:
    shield.engage_defense_lockdown()
    print("DEFENSIVE LOCKDOWN ENGAGED: Non-essential ports monitored, kernel hardened.")
    return 0


def cmd_daemon(shield: KalCyberShield, interval: int = 15) -> None:
    logger.info(f"Starting KAL Cyber Protection Daemon (audit every {interval}s)...")
    while True:
        try:
            telemetry = shield.audit()
            if telemetry.threat_count > 0:
                logger.warning(f"Threat detected! Status={telemetry.shield_status}, Threats={telemetry.threats}")
            else:
                logger.info(f"Shield Heartbeat: {telemetry.shield_status} | Hardening: {telemetry.kernel_hardening_score*100:.0f}% | Ports: {len(telemetry.authorized_ports_active)} OK")
        except Exception as e:
            logger.error(f"Error during cyber audit loop: {e}")
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="KAL Sovereign Cyber Protection Guard")
    parser.add_argument("command", choices=["status", "harden", "lockdown", "daemon", "json"], nargs="?", default="status")
    parser.add_argument("--interval", type=int, default=15, help="Daemon audit interval in seconds")
    args = parser.parse_args()

    shield = KalCyberShield()

    if args.command == "status":
        return cmd_status(shield)
    elif args.command == "json":
        telemetry = shield.audit()
        print(json.dumps(telemetry.__dict__, indent=2))
        return 0
    elif args.command == "harden":
        return cmd_harden(shield)
    elif args.command == "lockdown":
        return cmd_lockdown(shield)
    elif args.command == "daemon":
        cmd_daemon(shield, interval=args.interval)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
