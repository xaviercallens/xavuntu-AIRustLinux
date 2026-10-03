# Standard Operating Procedure (SOP): MVK Telemetry Reproducibility

**Objective:** This document provides the explicit, step-by-step Standard Operating Procedure (SOP) to reproduce the empirical CPU cycle telemetry published in the MVK `v9.1.0` research paper.

## Prerequisites
1. **Google Cloud SDK:** Ensure `gcloud` CLI is installed and authenticated.
2. **Rust Toolchain:** Native Rust `1.82+` installed locally (for validation) and on the target.
3. **Repository Access:** Clone the `rust-linux-mini-kernel` repository on the `main` branch.

---

## Phase 1: Infrastructure Provisioning
To guarantee reproducible hardware-level results, the benchmarks must be run on a dedicated Compute-Optimized bare-metal GCP instance. Hypervisor emulation will distort the results.

1. **Provision the C2 Instance:**
   ```bash
   gcloud compute instances create benchmark-c2 \
       --project=$(gcloud config get-value project) \
       --zone=us-central1-a \
       --machine-type=c2-standard-4 \
       --image-family=debian-12 \
       --image-project=debian-cloud \
       --boot-disk-size=50GB \
       --metadata=startup-script="#!/bin/bash
       apt-get update
       apt-get install -y build-essential curl
       curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
       source \$HOME/.cargo/env"
   ```
2. **Wait for Initialization:** Allow 2-3 minutes for the startup script to install `gcc` and `rustc`.

## Phase 2: Compiling the Benchmark Harnesses
We provide three benchmark harnesses: `harness.c` (Baseline), `harness.rs` (std library), and `harness_nostd.rs` (strict pure assembly).

1. **Transfer the Harnesses:**
   ```bash
   gcloud compute scp harness.c harness.rs harness_nostd.rs run_nostd_c2_benchmark.sh benchmark-c2:~ --zone=us-central1-a --tunnel-through-iap
   ```
2. **Establish SSH Connection:**
   ```bash
   gcloud compute ssh benchmark-c2 --zone=us-central1-a --tunnel-through-iap
   ```

## Phase 3: Benchmark Execution
Once SSH'd into the `benchmark-c2` node, execute the test scripts to extract the `rdtsc` hardware telemetry.

1. **Execute the Standard/Advanced Baselines:**
   *(Compile `harness.c` with `-O3` and `harness.rs` with `--release`)*.
2. **Execute the Strict `no_std` Telemetry:**
   ```bash
   chmod +x run_nostd_c2_benchmark.sh
   ./run_nostd_c2_benchmark.sh
   ```

**Expected Output:**
```text
==================== EXECUTION RESULTS ====================
Rust Pure no_std - Syscall (getpid) cycles: 755
============================================================
```

## Phase 4: Teardown
To prevent ongoing billing, immediately terminate the instance upon telemetry extraction:
```bash
gcloud compute instances delete benchmark-c2 --zone=us-central1-a --quiet
```

## Phase 5: Paper Compilation
The LaTeX source code is located in the `paper/` directory of the repository.
To compile the PDF using Docker:
```bash
cd paper/
docker run --rm -v $(pwd):/workspace -w /workspace dxjoke/tectonic-docker tectonic mvk_scientific_paper.tex
```
