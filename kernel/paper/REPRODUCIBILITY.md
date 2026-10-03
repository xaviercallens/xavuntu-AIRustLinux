# RunuX: Artifact Evaluation & Reproducibility Guide

> **Paper**: *RunuX: A Formally Verified, FFI-Compatible Rust Linux Kernel*  
> **Authors**: Xavier Callens  
> **Artifact DOI**: (to be assigned upon acceptance)

---

## 1. Overview

This document describes the step-by-step procedure to reproduce all experimental results reported in the RunuX paper. The artifact includes:
- **Source code** for all 297 Rust kernel modules.
- **Benchmark harnesses** (C and Rust) for performance comparison.
- **Lean 4 formal specifications** with a `lake` build system.
- **Chaos Mesh YAML manifests** for GKE fault injection.
- **Raw JSON datasets** for all reported metrics.

---

## 2. Prerequisites

| Requirement         | Version         | Notes                               |
|---------------------|-----------------|-------------------------------------|
| Rust (nightly)      | `nightly-2026-05-15` | Required for `no_std` + inline asm |
| Docker Desktop      | ≥ 24.0          | For cross-compilation sandbox       |
| QEMU                | ≥ 7.0           | User-mode emulation (x86_64)       |
| Lean 4 (`elan`)     | v4.29.1         | For formal verification proofs      |
| GKE Cluster         | n2d-standard-8  | For chaos engineering (optional)    |
| Chaos Mesh          | ≥ 2.6           | For fault injection (optional)      |
| Python 3            | ≥ 3.10          | For benchmark scripts               |

---

## 3. Reproducing Compilation (Table I)

```bash
git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git
cd rust-linux-mini-kernel

# Install the exact nightly toolchain
rustup toolchain install nightly-2026-05-15
rustup default nightly-2026-05-15
rustup component add rust-src --toolchain nightly-2026-05-15

# Verify 297/297 modules compile with zero errors
cargo check --workspace 2>&1 | tail -5
# Expected: Finished `dev` profile ... in X.XXs
```

**Expected output**: `Finished` with 0 errors, confirming 297/297 modules.

---

## 4. Reproducing Performance Benchmarks (Table II, Figure 1)

### 4.1 Docker Sandbox Setup
```bash
make -f Makefile.dev build-image
```

### 4.2 CRC32 Checksum Benchmark (C vs. Rust)
```bash
# C Harness (gcc -O3)
make -f Makefile.dev run-c-harness

# Rust std Harness (opt-level=3, LTO)
make -f Makefile.dev run-rs-harness

# Rust no_std Harness (inline assembly)
make -f Makefile.dev run-nostd-harness
```

### 4.3 QEMU Boot Time
```bash
make -f Makefile.dev run-qemu-test
```

**Expected output**: Boot time ≤ 105% of C baseline (~5003ms).

---

## 5. Reproducing Formal Verification (Section IV)

### 5.1 Lean 4 Proofs
```bash
cd specifications
lake build
# Expected: "Build completed successfully (5 jobs)."
```

### 5.2 Verus Integration Check
```bash
make -f Makefile.dev verify
# Expected: Both Lean 4 and Verus checks pass.
```

---

## 6. Reproducing Chaos Engineering (Table III, Figure 2)

### 6.1 Cluster Setup
```bash
# Create a 3-node GKE cluster
gcloud container clusters create runux-eval \
  --machine-type=n2d-standard-8 \
  --num-nodes=3 \
  --zone=us-central1-a

# Install Chaos Mesh
kubectl apply -f https://mirrors.chaos-mesh.org/v2.6.3/install.yaml
```

### 6.2 Deploy RunuX Kernel Pods
```bash
kubectl apply -f deploy/k8s-deployment.yaml
```

### 6.3 Execute Fault Injection
```bash
# Apply each chaos experiment sequentially
kubectl apply -f benchmarks/gke_results/infra/chaos_network_partition.yaml
sleep 50
kubectl apply -f benchmarks/gke_results/infra/chaos_network_delay.yaml
sleep 80
kubectl apply -f benchmarks/gke_results/infra/chaos_packet_loss.yaml
sleep 80
kubectl apply -f benchmarks/gke_results/infra/chaos_cpu_stress.yaml
sleep 80
kubectl apply -f benchmarks/gke_results/infra/chaos_memory_pressure.yaml
sleep 80
kubectl apply -f benchmarks/gke_results/infra/chaos_pod_kill.yaml
sleep 35

# Collect results
kubectl logs -l app=mvk-kernel --tail=1000 | grep -c "panic\|oops"
# Expected: 0
```

### 6.4 Teardown
```bash
gcloud container clusters delete runux-eval --zone=us-central1-a --quiet
```

---

## 7. Reproducing Fuzzing (Section V)

```bash
# Install cargo-fuzz (use stable toolchain for installation)
rustup run stable cargo install cargo-fuzz

# Run fuzzing targets (30 seconds each)
cd fuzz
cargo +nightly-2026-05-15 fuzz run fuzz_packet -- -max_total_time=30
cargo +nightly-2026-05-15 fuzz run fuzz_routing -- -max_total_time=30
```

**Expected output**: No crashes or undefined behavior.

---

## 8. Raw Data

All raw benchmark data is available in machine-readable JSON format:
- `paper/dataset.json` — Consolidated dataset for all tables and figures.
- `benchmarks/gke_results/gke_benchmark_20260521_170733.json` — GKE chaos raw data.
- `benchmarks/results/c_vs_rust_comparison.json` — CRC32 comparison raw data.
- `paper/mvk_chaos_benchmarks.tar.gz` — Full checkpoint archive.

---

## 9. Claims Mapping

| Paper Claim                          | Section | Reproduction Step |
|--------------------------------------|---------|-------------------|
| 297/297 modules compile              | §III    | Step 3            |
| Rust CRC32 4.73% faster than C       | §V      | Step 4.2          |
| Boot time within 0.02% of C          | §V      | Step 4.3          |
| 0 panics under 6 chaos experiments   | §VI     | Step 6            |
| Lean 4 proofs type-check (0 sorry)   | §IV     | Step 5.1          |
| Fuzzing finds 0 crashes              | §V      | Step 7            |
