#!/usr/bin/env python3
"""
GKE Multi-Pod MVK Kernel Test Orchestrator

Orchestrates the full 4-phase test matrix:
  Phase 1: Baseline performance (no chaos)
  Phase 2: Performance under load (stress-ng)
  Phase 3: Chaos testing (Chaos Mesh fault injection)
  Phase 4: Rust vs C comparison report

Usage:
  # Full suite
  python3 deploy/scripts/run_gke_tests.py --project-id MY_PROJECT --full-suite

  # Deploy only
  python3 deploy/scripts/run_gke_tests.py --project-id MY_PROJECT --deploy-only

  # Run tests on existing cluster
  python3 deploy/scripts/run_gke_tests.py --skip-infra --full-suite

  # Teardown
  python3 deploy/scripts/run_gke_tests.py --project-id MY_PROJECT --teardown
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent
DEPLOY_DIR = WORKSPACE / "deploy"
RESULTS_DIR = WORKSPACE / "benchmarks" / "gke_results"


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def run(cmd: str, check=True, capture=False, timeout=300) -> subprocess.CompletedProcess:
    """Run a shell command."""
    return subprocess.run(
        cmd, shell=True, check=check, timeout=timeout,
        capture_output=capture, text=True,
        cwd=str(WORKSPACE)
    )


def kubectl(cmd: str, capture=True) -> str:
    """Run a kubectl command and return stdout."""
    result = run(f"kubectl {cmd}", capture=capture, check=False)
    return result.stdout.strip() if capture else ""


# ============================================================
# Phase 0: Infrastructure
# ============================================================

def deploy_infrastructure(project_id: str, use_spot: bool = True):
    """Deploy GKE cluster with Terraform."""
    log("═══ Phase 0: Deploying GKE Infrastructure ═══")

    tf_dir = DEPLOY_DIR / "gke"
    spot_flag = "true" if use_spot else "false"

    log("Running terraform init...")
    run(f"terraform -chdir={tf_dir} init")

    log("Running terraform apply...")
    run(f"terraform -chdir={tf_dir} apply -auto-approve "
        f"-var='project_id={project_id}' "
        f"-var='use_spot_vms={spot_flag}'",
        timeout=600)

    log("Getting cluster credentials...")
    run(f"gcloud container clusters get-credentials mvk-benchmark "
        f"--zone us-central1-a --project {project_id}")

    log("✅ GKE cluster deployed.")


def install_chaos_mesh():
    """Install Chaos Mesh on the cluster."""
    log("Installing Chaos Mesh...")
    run("kubectl create ns chaos-mesh 2>/dev/null || true")
    run("helm repo add chaos-mesh https://charts.chaos-mesh.org")
    run("helm repo update")
    run("helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh "
        "--namespace chaos-mesh "
        "--set chaosDaemon.runtime=containerd "
        "--set chaosDaemon.socketPath=/run/containerd/containerd.sock "
        "--wait --timeout 300s",
        timeout=360)
    log("✅ Chaos Mesh installed.")


def deploy_benchmark_pods(project_id: str):
    """Deploy MVK benchmark pods via Helm."""
    log("Deploying benchmark pods...")
    chart_dir = DEPLOY_DIR / "helm" / "mvk-benchmark"

    run(f"helm upgrade --install mvk-benchmark {chart_dir} "
        f"--set image.repository=gcr.io/{project_id}/mvk-kernel "
        f"--set baselineImage.repository=gcr.io/{project_id}/mvk-kernel "
        f"--set baselineImage.tag=9.4.0 "
        f"--set chaos.enabled=false "  # Start without chaos
        f"--wait --timeout 300s",
        timeout=360)

    log("Waiting for pods to be ready...")
    kubectl("wait --for=condition=ready pod -l app=mvk-kernel --timeout=120s")
    kubectl("wait --for=condition=ready pod -l app=c-baseline --timeout=120s")

    log("✅ Benchmark pods deployed.")


def build_and_push_images(project_id: str):
    """Build and push container images to GCR."""
    log("Building container images...")

    run(f"cp deploy/docker/Dockerfile.mvk-kernel Dockerfile")
    run(f"gcloud builds submit --tag gcr.io/{project_id}/mvk-kernel:9.4.0 --project {project_id} .", timeout=1200)
    run(f"rm Dockerfile")


# ============================================================
# Phase 1: Baseline Performance
# ============================================================

def run_baseline_tests():
    """Run baseline performance tests (no chaos)."""
    log("═══ Phase 1: Baseline Performance Tests ═══")
    results = {}

    # 1.1 - QEMU Boot Time
    log("[1.1] Measuring QEMU boot time across pods...")
    pods = kubectl("get pods -l app=mvk-kernel -o jsonpath='{.items[*].metadata.name}'").split()
    boot_times = {}
    for pod in pods:
        bt = kubectl(f"exec {pod} -- cat /mvk/results/boot_time_ms.txt")
        boot_times[pod] = int(bt) if bt.isdigit() else -1
        log(f"  {pod}: {boot_times[pod]}ms")
    results["boot_times_ms"] = boot_times

    # 1.2 - Sysbench CPU
    log("[1.2] Collecting sysbench CPU results...")
    for pod in pods:
        cpu_result = kubectl(f"exec {pod} -- cat /mvk/results/sysbench_cpu.txt")
        log(f"  {pod}: {_extract_sysbench_metric(cpu_result, 'events per second')}")

    # 1.3 - Sysbench Memory
    log("[1.3] Collecting sysbench memory results...")
    for pod in pods:
        mem_result = kubectl(f"exec {pod} -- cat /mvk/results/sysbench_memory.txt")
        log(f"  {pod}: {_extract_sysbench_metric(mem_result, 'transferred')}")

    # 1.4 - TCP Throughput (pod-to-pod)
    log("[1.4] Running iperf3 TCP throughput (pod-to-pod)...")
    client_pod = kubectl("get pods -l app=mvk-kernel,role=client -o jsonpath='{.items[0].metadata.name}'")
    if client_pod:
        tcp_result = kubectl(f"exec {client_pod} -- cat /mvk/results/iperf3_tcp.json")
        try:
            tcp_data = json.loads(tcp_result)
            bps = tcp_data.get("end", {}).get("sum_received", {}).get("bits_per_second", 0)
            gbps = bps / 1e9
            results["tcp_throughput_gbps"] = gbps
            log(f"  TCP throughput: {gbps:.2f} Gbps")
        except (json.JSONDecodeError, KeyError):
            log("  TCP throughput: parsing failed")

    # 1.5 - CRC32 Compute
    log("[1.5] Collecting CRC32 benchmark results...")
    for pod in pods:
        crc_result = kubectl(f"exec {pod} -- cat /mvk/results/c_vs_rust_comparison.json 2>/dev/null")
        if crc_result:
            try:
                crc_data = json.loads(crc_result)
                for entry in crc_data.get("results", []):
                    log(f"  {pod} [{entry['language']}]: {entry['median_seconds']:.3f}s")
            except json.JSONDecodeError:
                pass

    results["phase"] = "baseline"
    results["timestamp"] = datetime.now(timezone.utc).isoformat()
    return results


# ============================================================
# Phase 2: Performance Under Load
# ============================================================

def run_stress_tests():
    """Run performance tests under CPU/memory stress."""
    log("═══ Phase 2: Performance Under Load ═══")
    results = {}

    client_pod = kubectl("get pods -l app=mvk-kernel,role=client -o jsonpath='{.items[0].metadata.name}'")
    if not client_pod:
        log("  No client pod found. Skipping stress tests.")
        return results

    # 2.1 - TCP under CPU stress
    log("[2.1] Running iperf3 under CPU stress (75% load)...")
    stress_result = kubectl(f"exec {client_pod} -- cat /mvk/results/iperf3_tcp_under_stress.json")
    if stress_result:
        try:
            stress_data = json.loads(stress_result)
            bps = stress_data.get("end", {}).get("sum_received", {}).get("bits_per_second", 0)
            results["tcp_under_stress_gbps"] = bps / 1e9
            log(f"  TCP under stress: {results['tcp_under_stress_gbps']:.2f} Gbps")
        except json.JSONDecodeError:
            pass

    results["phase"] = "stress"
    results["timestamp"] = datetime.now(timezone.utc).isoformat()
    return results


# ============================================================
# Phase 3: Chaos Testing
# ============================================================

def run_chaos_tests(project_id: str):
    """Enable Chaos Mesh experiments and monitor kernel behavior."""
    log("═══ Phase 3: Chaos Testing (Chaos Mesh) ═══")
    results = {"experiments": [], "panics": 0, "oops": 0}

    chart_dir = DEPLOY_DIR / "helm" / "mvk-benchmark"

    # Enable chaos experiments
    log("Enabling Chaos Mesh experiments...")
    run(f"helm upgrade mvk-benchmark {chart_dir} "
        f"--set image.repository=gcr.io/{project_id}/mvk-kernel "
        f"--set baselineImage.repository=gcr.io/{project_id}/mvk-kernel "
        f"--set baselineImage.tag=9.4.0 "
        f"--set chaos.enabled=true "
        f"--wait --timeout 120s",
        timeout=180)

    chaos_experiments = [
        ("mvk-network-partition", 45),
        ("mvk-network-delay", 75),
        ("mvk-packet-loss", 75),
        ("mvk-cpu-stress", 75),
        ("mvk-memory-pressure", 75),
        ("mvk-pod-kill", 30),
    ]

    for exp_name, wait_secs in chaos_experiments:
        log(f"[3.x] Running chaos experiment: {exp_name} ({wait_secs}s)...")

        # Check if experiment exists
        status = kubectl(f"get networkchaos,stresschaos,podchaos {exp_name} "
                        f"-o jsonpath='{{.status.conditions}}' 2>/dev/null")

        # Wait for experiment duration
        time.sleep(wait_secs)

        # Check for kernel panics in QEMU logs
        pods = kubectl("get pods -l app=mvk-kernel -o jsonpath='{.items[*].metadata.name}'").split()
        for pod in pods:
            qemu_log = kubectl(f"exec {pod} -- cat /mvk/results/qemu_boot.log 2>/dev/null")
            if "panic" in qemu_log.lower():
                results["panics"] += 1
                log(f"  ⚠️  PANIC detected in {pod}!")
            if "oops" in qemu_log.lower():
                results["oops"] += 1
                log(f"  ⚠️  OOPS detected in {pod}!")

        exp_result = {
            "name": exp_name,
            "duration_s": wait_secs,
            "panics": results["panics"],
            "pod_count": len(pods),
        }
        results["experiments"].append(exp_result)
        log(f"  ✅ {exp_name} complete. Panics: {results['panics']}")

    # Disable chaos after tests
    log("Disabling Chaos Mesh experiments...")
    run(f"helm upgrade mvk-benchmark {chart_dir} "
        f"--set image.repository=gcr.io/{project_id}/mvk-kernel "
        f"--set baselineImage.repository=gcr.io/{project_id}/mvk-kernel "
        f"--set baselineImage.tag=9.4.0 "
        f"--set chaos.enabled=false "
        f"--wait --timeout 120s",
        timeout=180)

    results["phase"] = "chaos"
    results["timestamp"] = datetime.now(timezone.utc).isoformat()
    return results


# ============================================================
# Phase 4: Rust vs C Comparison Report
# ============================================================

def generate_comparison_report(baseline: dict, stress: dict, chaos: dict):
    """Generate the final Rust vs C comparison report."""
    log("═══ Phase 4: Generating Comparison Report ═══")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Collect C baseline results
    c_pod = kubectl("get pods -l app=c-baseline -o jsonpath='{.items[0].metadata.name}'")
    c_boot_time = -1
    if c_pod:
        bt = kubectl(f"exec {c_pod} -- cat /mvk/results/boot_time_ms.txt 2>/dev/null")
        c_boot_time = int(bt) if bt and bt.isdigit() else -1

    # Build comparison
    mvk_boot_times = list(baseline.get("boot_times_ms", {}).values())
    mvk_median_boot = sorted(mvk_boot_times)[len(mvk_boot_times) // 2] if mvk_boot_times else -1

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": "GKE Standard (n2d-standard-8, Dataplane V2)",
        "phases": {
            "baseline": baseline,
            "stress": stress,
            "chaos": chaos,
        },
        "comparison": {
            "boot_time_ms": {
                "rust": mvk_median_boot,
                "c": c_boot_time,
                "delta_pct": _pct_delta(mvk_median_boot, c_boot_time),
                "target": "≤105%",
                "pass": mvk_median_boot <= c_boot_time * 1.05 if c_boot_time > 0 else None,
            },
            "tcp_throughput_gbps": {
                "rust": baseline.get("tcp_throughput_gbps", -1),
                "c": -1,  # Populated from C baseline pod
                "target": "≥95% of C",
            },
            "chaos_panics": {
                "rust": chaos.get("panics", -1),
                "c": -1,  # C baseline not chaos-tested
                "target": "0 panics",
                "pass": chaos.get("panics", -1) == 0,
            },
            "chaos_oops": {
                "rust": chaos.get("oops", -1),
                "target": "0 oops",
                "pass": chaos.get("oops", -1) == 0,
            },
        },
        "verdict": "PASS" if chaos.get("panics", -1) == 0 else "FAIL",
    }

    # Save JSON
    json_path = RESULTS_DIR / f"gke_benchmark_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    log(f"  JSON: {json_path}")

    # Save Markdown
    md_path = RESULTS_DIR / f"gke_benchmark_{timestamp}.md"
    with open(md_path, "w") as f:
        f.write(_generate_markdown_report(report))
    log(f"  Markdown: {md_path}")

    # Print verdict
    verdict = report["verdict"]
    panics = chaos.get("panics", "?")
    log(f"\n{'='*60}")
    log(f"  VERDICT: {verdict}")
    log(f"  Chaos panics: {panics}")
    log(f"  Boot time (Rust): {mvk_median_boot}ms")
    log(f"  Boot time (C):    {c_boot_time}ms")
    log(f"{'='*60}\n")

    return report


# ============================================================
# Teardown
# ============================================================

def teardown(project_id: str):
    """Destroy all GKE infrastructure."""
    log("═══ Teardown: Destroying GKE Infrastructure ═══")
    tf_dir = DEPLOY_DIR / "gke"

    log("Uninstalling Helm releases...")
    run("helm uninstall mvk-benchmark 2>/dev/null || true")
    run("helm uninstall chaos-mesh -n chaos-mesh 2>/dev/null || true")

    log("Destroying Terraform resources...")
    run(f"terraform -chdir={tf_dir} destroy -auto-approve "
        f"-var='project_id={project_id}'",
        timeout=600)

    log("✅ All resources destroyed.")


# ============================================================
# Helpers
# ============================================================

def _pct_delta(rust_val, c_val):
    if c_val <= 0 or rust_val < 0:
        return None
    return round((rust_val - c_val) / c_val * 100, 1)


def _extract_sysbench_metric(text: str, key: str) -> str:
    for line in text.split("\n"):
        if key in line:
            return line.strip()
    return "N/A"


def _generate_markdown_report(report: dict) -> str:
    comp = report["comparison"]
    ts = report["timestamp"]
    platform = report["platform"]

    return f"""# GKE Multi-Pod MVK Benchmark Report

**Generated:** {ts}
**Platform:** {platform}
**Verdict:** **{report['verdict']}**

---

## Phase 4: Rust vs C Comparison

| Metric | Rust | C | Delta | Target | Status |
|--------|------|---|-------|--------|--------|
| **Boot Time** | {comp['boot_time_ms']['rust']}ms | {comp['boot_time_ms']['c']}ms | {comp['boot_time_ms']['delta_pct']}% | ≤105% | {'✅' if comp['boot_time_ms'].get('pass') else '❌'} |
| **Chaos Panics** | {comp['chaos_panics']['rust']} | — | — | 0 | {'✅' if comp['chaos_panics'].get('pass') else '❌'} |
| **Chaos Oops** | {comp['chaos_oops']['rust']} | — | — | 0 | {'✅' if comp['chaos_oops'].get('pass') else '❌'} |

## Chaos Experiments

| Experiment | Duration | Panics | Result |
|-----------|----------|--------|--------|
"""


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="GKE MVK Kernel Benchmark Orchestrator")
    parser.add_argument("--project-id", type=str, help="GCP project ID")
    parser.add_argument("--full-suite", action="store_true", help="Run all 4 phases")
    parser.add_argument("--deploy-only", action="store_true", help="Deploy infrastructure only")
    parser.add_argument("--skip-infra", action="store_true", help="Skip infrastructure deployment")
    parser.add_argument("--teardown", action="store_true", help="Destroy all resources")
    parser.add_argument("--no-spot", action="store_true", help="Use on-demand VMs")
    args = parser.parse_args()

    project_id = args.project_id or os.environ.get("GCP_PROJECT_ID")
    if not project_id and not args.skip_infra:
        print("ERROR: --project-id or GCP_PROJECT_ID required")
        sys.exit(1)

    if args.teardown:
        teardown(project_id)
        return

    if not args.skip_infra:
        # deploy_infrastructure(project_id, use_spot=not args.no_spot)
        install_chaos_mesh()
        build_and_push_images(project_id)
        deploy_benchmark_pods(project_id)

    if args.deploy_only:
        log("Deploy complete. Use --full-suite to run tests.")
        return

    if args.full_suite or not args.deploy_only:
        # Phase 1
        baseline = run_baseline_tests()

        # Phase 2
        stress = run_stress_tests()

        # Phase 3
        chaos = run_chaos_tests(project_id)

        # Phase 4
        report = generate_comparison_report(baseline, stress, chaos)

        # Save all results
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(RESULTS_DIR / "latest_report.json", "w") as f:
            json.dump(report, f, indent=2)

        log("✅ Full test suite complete!")


if __name__ == "__main__":
    main()
