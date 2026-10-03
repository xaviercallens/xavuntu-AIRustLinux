---
name: qemu-gcp-chaos-verification
description: >-
  Executes headless QEMU kernel boot tests, multi-arch emulation (x86_64 and RISC-V), GKE Chaos Mesh fault injection testing, and GCP bare-metal deployment audits. Use when testing bootloader changes, hypervisor integration, chaos resilience, or deployment verification.
---

# QEMU, GCP Bare Metal & Chaos Engineering Verification Skill

## Overview
This skill provides runbooks and automated verification procedures for testing **RunuX** across virtualized (QEMU), orchestrated (Kubernetes / Chaos Mesh), and physical bare-metal (GCP `c3-metal-85`) environments. It ensures that kernel updates preserve sub-second boot times, zero-panic resilience under sustained fault injection, and hardware driver stability.

---

## Verification Workflows

### 1. Headless QEMU Boot Testing
Run automated QEMU boot tests to verify early kernel initialization, APIC setup, and serial console output:

```bash
# 1. Run automated x86_64 QEMU boot test harness
python3 scripts/qemu_boot_test.py

# 2. Run RISC-V 64-bit QEMU emulation boot test
python3 scripts/qemu_riscv_boot_test.py

# 3. Execute CI headless harness
./scripts/run_qemu_harness.sh --ci
```

#### Expected Boot Sequence Indicators:
* Early printk initialization: `[OK] Early console online`.
* Memory subsystem initialization: `[OK] Buddy allocator initialized`.
* VFS root mount: `[OK] Mounted rootfs`.
* Clean shutdown: `reboot: System halted` or `QEMU execution completed successfully`.

### 2. GKE Chaos Engineering Evaluation
RunuX is verified under continuous fault injection using Chaos Mesh on Google Kubernetes Engine (GKE). When validating chaos resilience, verify:

| Experiment | Fault Type | Duration | Pass Criteria |
| :--- | :--- | :--- | :--- |
| **Network Partition** | Pod-to-pod split-brain | 45s | 0 panics, 0 oopses, TCP reconnects gracefully |
| **Network Delay** | 100ms added latency | 75s | 0 socket leaks, conntrack table stable |
| **Packet Loss** | 50% packet drop | 75s | TCP retransmits cleanly, no buffer starvation |
| **CPU Stress** | 4 cores at 100% | 75s | CFS scheduler maintains vruntime fairness |
| **Memory OOM** | Exhaust host memory | 75s | Fallible allocators return `-ENOMEM`, 0 panics |
| **Pod Evictions** | Sudden SIGKILL/SIGTERM | 30s | Clean resource deallocation via `Drop` |

### 3. GCP Bare Metal (`c3-metal-85`) Deployment
Deploy and validate physical hardware drivers on Google Cloud Platform bare-metal nodes:

```bash
# Execute GCP bare-metal deployment script
./scripts/deploy_gcp_baremetal.sh
```

#### Hardware Driver Checklist:
* **IDPF Network Driver** (`crates/driver_idpf`): Verify zero-copy DMA queue isolation and ring descriptor integrity.
* **Hyperdisk Block Driver** (`crates/driver_nvme`): Confirm asynchronous NVMe command queueing and completion polling without CPU spinlock deadlocks.
* **VPC Networking**: Confirm dual-stack IPv4/IPv6 packet ingress and route table population.

### 4. Performance Benchmark Regressions
Run benchmark suites to ensure performance adheres to target thresholds:
* **CRC32 Throughput**: Must maintain $\ge 4.7\%$ speedup over standard Linux C implementation.
* **Boot Time**: Must complete within $\le 0.05\%$ variance of C baseline (target: ~5004 ms in QEMU).
* **TCP Stress Throughput**: Must achieve $\ge 15.0 \text{ Gbps}$ in local bridge benchmarks.
