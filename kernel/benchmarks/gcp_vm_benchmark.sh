#!/bin/bash
set -euo pipefail

# ============================================================
# GCP VM Benchmark Runner for MVK v9.4.0
# Provisions a compute-optimized VM, runs compilation + runtime
# benchmarks, collects results, and tears down the instance.
# ============================================================

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:?Please set GCP_PROJECT_ID}"
ZONE="${GCP_ZONE:-us-central1-a}"
MACHINE_TYPE="${GCP_MACHINE_TYPE:-c2d-standard-8}"
IMAGE_FAMILY="debian-12"
IMAGE_PROJECT="debian-cloud"
VM_NAME="mvk-bench-$(date +%s)"
RESULTS_DIR="$(dirname "$0")/results/gcp_$(date +%Y%m%d_%H%M%S)"
REPO_URL="https://github.com/xaviercallens/rust-linux-mini-kernel.git"
REPO_BRANCH="${MVK_BRANCH:-main}"

mkdir -p "${RESULTS_DIR}"

echo "============================================================"
echo " MVK v9.4.0 GCP Benchmark Suite"
echo "============================================================"
echo " Project:  ${PROJECT_ID}"
echo " Zone:     ${ZONE}"
echo " Machine:  ${MACHINE_TYPE}"
echo " VM Name:  ${VM_NAME}"
echo " Results:  ${RESULTS_DIR}"
echo "============================================================"

# --------------------------------------------------
# Phase 1: Provision VM
# --------------------------------------------------
echo ""
echo ">>> Phase 1: Creating GCP VM..."

gcloud compute instances create "${VM_NAME}" \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    --machine-type="${MACHINE_TYPE}" \
    --image-family="${IMAGE_FAMILY}" \
    --image-project="${IMAGE_PROJECT}" \
    --boot-disk-size=100GB \
    --boot-disk-type=pd-ssd \
    --scopes=default \
    --tags=benchmark

echo "    VM created. Waiting 30s for boot..."
sleep 30

# --------------------------------------------------
# Phase 2: Install Toolchains
# --------------------------------------------------
echo ""
echo ">>> Phase 2: Installing toolchains on ${VM_NAME}..."

gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" -- bash -s <<'SETUP_EOF'
set -euo pipefail

echo "[SETUP] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    build-essential gcc git python3 python3-pip \
    qemu-system-x86 iperf3 linux-perf time jq

echo "[SETUP] Installing Rust nightly toolchain..."
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain nightly-2026-05-15
source "$HOME/.cargo/env"

rustup target add i686-unknown-linux-gnu
rustup component add llvm-tools-preview
cargo install cargo-pgo

echo "[SETUP] Cloning repository..."
cd /tmp
git clone --depth 1 --branch main https://github.com/xaviercallens/rust-linux-mini-kernel.git
cd rust-linux-mini-kernel

echo "[SETUP] Setup complete."
SETUP_EOF

# --------------------------------------------------
# Phase 3: Compilation Benchmarks
# --------------------------------------------------
echo ""
echo ">>> Phase 3: Running compilation benchmarks..."

gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" -- bash -s <<'COMPILE_EOF'
set -euo pipefail
source "$HOME/.cargo/env"
cd /tmp/rust-linux-mini-kernel

RESULTS="/tmp/benchmark_results"
mkdir -p "${RESULTS}"

echo "=== Benchmark 1: cargo check --workspace ==="
{ time cargo check --workspace 2>&1; } 2> "${RESULTS}/time_check.txt" | tee "${RESULTS}/check.log"

echo "=== Benchmark 2: cargo build --workspace --release ==="
{ time cargo build --workspace --release 2>&1; } 2> "${RESULTS}/time_build_release.txt" | tee "${RESULTS}/build_release.log"

echo "=== Benchmark 3: Incremental rebuild (touch 1 file) ==="
touch crates/kernel_types/src/lib.rs
{ time cargo build --workspace --release 2>&1; } 2> "${RESULTS}/time_incremental.txt" | tee "${RESULTS}/incremental.log"

echo "=== Benchmark 4: Release binary sizes ==="
ls -la target/release/lib*.rlib 2>/dev/null | head -30 > "${RESULTS}/binary_sizes.txt" || echo "No .rlib files found" > "${RESULTS}/binary_sizes.txt"
du -sh target/release/ > "${RESULTS}/total_release_size.txt"

echo "=== Benchmark 5: Compilation unit count ==="
find crates/ -name "*.rs" | wc -l > "${RESULTS}/source_file_count.txt"
find crates/ -name "Cargo.toml" | wc -l > "${RESULTS}/crate_count.txt"

echo "[COMPILE] All compilation benchmarks complete."
COMPILE_EOF

# --------------------------------------------------
# Phase 4: QEMU Boot Benchmark
# --------------------------------------------------
echo ""
echo ">>> Phase 4: Running QEMU boot benchmark..."

gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" -- bash -s <<'QEMU_EOF'
set -euo pipefail
source "$HOME/.cargo/env"
cd /tmp/rust-linux-mini-kernel

RESULTS="/tmp/benchmark_results"

echo "=== Building 32-bit Multiboot 1 Kernel ==="
cargo build --manifest-path examples/demo_kernel/Cargo.toml --target i686-unknown-linux-gnu

echo "=== QEMU Boot Smoke Test (5 iterations) ==="
for i in 1 2 3 4 5; do
    echo "--- Iteration ${i} ---"
    { time python3 scripts/qemu_boot_test.py \
        --kernel target/i686-unknown-linux-gnu/debug/demo_kernel \
        --timeout 15.0 2>&1; } 2>> "${RESULTS}/qemu_boot_times.txt" | tail -1
done

echo "[QEMU] Boot benchmarks complete."
QEMU_EOF

# --------------------------------------------------
# Phase 5: PGO Optimization Benchmark
# --------------------------------------------------
echo ""
echo ">>> Phase 5: Running PGO optimization benchmark..."

gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" -- bash -s <<'PGO_EOF'
set -euo pipefail
source "$HOME/.cargo/env"
cd /tmp/rust-linux-mini-kernel

RESULTS="/tmp/benchmark_results"

echo "=== PGO: Instrumented build ==="
{ time cargo pgo build 2>&1; } 2> "${RESULTS}/time_pgo_instrument.txt" | tee "${RESULTS}/pgo_instrument.log"

echo "=== PGO: Gather profiles (workspace tests) ==="
cargo pgo test 2>&1 | tee "${RESULTS}/pgo_profile.log" || echo "PGO profiling: some tests may have failed (expected for no_std crates)"

echo "=== PGO: Optimized rebuild ==="
{ time cargo pgo optimize 2>&1; } 2> "${RESULTS}/time_pgo_optimize.txt" | tee "${RESULTS}/pgo_optimize.log"

echo "=== PGO: Size comparison ==="
echo "--- Before PGO ---" > "${RESULTS}/pgo_size_comparison.txt"
du -sh target/release/ >> "${RESULTS}/pgo_size_comparison.txt"
echo "--- After PGO ---" >> "${RESULTS}/pgo_size_comparison.txt"
du -sh target/x86_64-unknown-linux-gnu/release/ 2>/dev/null >> "${RESULTS}/pgo_size_comparison.txt" || echo "PGO target dir not found" >> "${RESULTS}/pgo_size_comparison.txt"

echo "[PGO] Optimization benchmarks complete."
PGO_EOF

# --------------------------------------------------
# Phase 6: C vs Rust Microbenchmark Comparison
# --------------------------------------------------
echo ""
echo ">>> Phase 6: Running C vs Rust microbenchmarks..."

gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" -- bash -s <<'MICRO_EOF'
set -euo pipefail
source "$HOME/.cargo/env"
cd /tmp/rust-linux-mini-kernel

RESULTS="/tmp/benchmark_results"

echo "=== Microbenchmark: CRC32 (Rust vs C) ==="

# --- C baseline ---
cat > /tmp/crc32_bench_c.c << 'C_CODE'
#include <stdio.h>
#include <stdint.h>
#include <time.h>

static uint32_t crc32_table[256];

void crc32_init(void) {
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t crc = i;
        for (int j = 0; j < 8; j++)
            crc = (crc >> 1) ^ (0xEDB88320 & (-(crc & 1)));
        crc32_table[i] = crc;
    }
}

uint32_t crc32(const uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; i++)
        crc = (crc >> 8) ^ crc32_table[(crc ^ data[i]) & 0xFF];
    return ~crc;
}

int main(void) {
    crc32_init();
    uint8_t buf[4096];
    for (int i = 0; i < 4096; i++) buf[i] = (uint8_t)(i & 0xFF);

    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);

    volatile uint32_t result = 0;
    for (int i = 0; i < 1000000; i++)
        result = crc32(buf, 4096);

    clock_gettime(CLOCK_MONOTONIC, &end);
    double elapsed = (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;
    printf("C CRC32: %u, Time: %.4f seconds (1M iterations x 4KB)\n", result, elapsed);
    return 0;
}
C_CODE

gcc -O3 -march=native -o /tmp/crc32_bench_c /tmp/crc32_bench_c.c
echo "--- C CRC32 Benchmark ---" > "${RESULTS}/microbench_crc32.txt"
/tmp/crc32_bench_c >> "${RESULTS}/microbench_crc32.txt"
/tmp/crc32_bench_c >> "${RESULTS}/microbench_crc32.txt"
/tmp/crc32_bench_c >> "${RESULTS}/microbench_crc32.txt"

# --- Rust equivalent ---
mkdir -p /tmp/crc32_rust/src
cat > /tmp/crc32_rust/Cargo.toml << 'RTOML'
[package]
name = "crc32_bench"
version = "0.1.0"
edition = "2021"
[profile.release]
opt-level = 3
lto = "fat"
codegen-units = 1
strip = true
RTOML

cat > /tmp/crc32_rust/src/main.rs << 'RCODE'
use std::time::Instant;

fn crc32_init() -> [u32; 256] {
    let mut table = [0u32; 256];
    for i in 0..256u32 {
        let mut crc = i;
        for _ in 0..8 {
            crc = if crc & 1 != 0 {
                (crc >> 1) ^ 0xEDB88320
            } else {
                crc >> 1
            };
        }
        table[i as usize] = crc;
    }
    table
}

fn crc32(table: &[u32; 256], data: &[u8]) -> u32 {
    let mut crc = 0xFFFFFFFFu32;
    for &byte in data {
        crc = (crc >> 8) ^ table[((crc ^ byte as u32) & 0xFF) as usize];
    }
    !crc
}

fn main() {
    let table = crc32_init();
    let buf: Vec<u8> = (0..4096).map(|i| (i & 0xFF) as u8).collect();

    let start = Instant::now();
    let mut result = 0u32;
    for _ in 0..1_000_000 {
        result = crc32(&table, &buf);
        std::hint::black_box(result);
    }
    let elapsed = start.elapsed().as_secs_f64();
    println!("Rust CRC32: {}, Time: {:.4} seconds (1M iterations x 4KB)", result, elapsed);
}
RCODE

cd /tmp/crc32_rust
cargo build --release 2>/dev/null
echo "--- Rust CRC32 Benchmark ---" >> "${RESULTS}/microbench_crc32.txt"
./target/release/crc32_bench >> "${RESULTS}/microbench_crc32.txt"
./target/release/crc32_bench >> "${RESULTS}/microbench_crc32.txt"
./target/release/crc32_bench >> "${RESULTS}/microbench_crc32.txt"

echo ""
echo "=== Microbenchmark: Memory Allocation Throughput ==="

cat > /tmp/alloc_bench_c.c << 'C_ALLOC'
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

int main(void) {
    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);

    for (int i = 0; i < 10000000; i++) {
        void *p = malloc(64);
        if (p) free(p);
    }

    clock_gettime(CLOCK_MONOTONIC, &end);
    double elapsed = (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;
    printf("C malloc/free: %.4f seconds (10M iterations x 64B)\n", elapsed);
    return 0;
}
C_ALLOC

gcc -O3 -march=native -o /tmp/alloc_bench_c /tmp/alloc_bench_c.c
echo "--- C Allocation Benchmark ---" > "${RESULTS}/microbench_alloc.txt"
/tmp/alloc_bench_c >> "${RESULTS}/microbench_alloc.txt"
/tmp/alloc_bench_c >> "${RESULTS}/microbench_alloc.txt"
/tmp/alloc_bench_c >> "${RESULTS}/microbench_alloc.txt"

mkdir -p /tmp/alloc_rust/src
cat > /tmp/alloc_rust/Cargo.toml << 'RTOML2'
[package]
name = "alloc_bench"
version = "0.1.0"
edition = "2021"
[profile.release]
opt-level = 3
lto = "fat"
codegen-units = 1
RTOML2

cat > /tmp/alloc_rust/src/main.rs << 'RALLOC'
use std::time::Instant;

fn main() {
    let start = Instant::now();
    for _ in 0..10_000_000 {
        let v = Box::new([0u8; 64]);
        std::hint::black_box(v);
    }
    let elapsed = start.elapsed().as_secs_f64();
    println!("Rust Box::new/drop: {:.4} seconds (10M iterations x 64B)", elapsed);
}
RALLOC

cd /tmp/alloc_rust
cargo build --release 2>/dev/null
echo "--- Rust Allocation Benchmark ---" >> "${RESULTS}/microbench_alloc.txt"
./target/release/alloc_bench >> "${RESULTS}/microbench_alloc.txt"
./target/release/alloc_bench >> "${RESULTS}/microbench_alloc.txt"
./target/release/alloc_bench >> "${RESULTS}/microbench_alloc.txt"

echo "[MICRO] Microbenchmarks complete."
MICRO_EOF

# --------------------------------------------------
# Phase 7: Collect Results
# --------------------------------------------------
echo ""
echo ">>> Phase 7: Collecting results from VM..."

gcloud compute scp --recurse \
    "${VM_NAME}":/tmp/benchmark_results/* \
    "${RESULTS_DIR}/" \
    --zone="${ZONE}" --project="${PROJECT_ID}"

# --------------------------------------------------
# Phase 8: Generate Summary Report
# --------------------------------------------------
echo ""
echo ">>> Phase 8: Generating summary report..."

gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" -- bash -s <<'REPORT_EOF'
RESULTS="/tmp/benchmark_results"
echo "============================================================"
echo " MVK v9.4.0 GCP Benchmark Summary"
echo "============================================================"
echo ""
echo "--- Compilation Times ---"
cat "${RESULTS}/time_check.txt" 2>/dev/null || echo "N/A"
cat "${RESULTS}/time_build_release.txt" 2>/dev/null || echo "N/A"
echo ""
echo "--- Incremental Build ---"
cat "${RESULTS}/time_incremental.txt" 2>/dev/null || echo "N/A"
echo ""
echo "--- QEMU Boot Times ---"
cat "${RESULTS}/qemu_boot_times.txt" 2>/dev/null || echo "N/A"
echo ""
echo "--- CRC32 Microbenchmark ---"
cat "${RESULTS}/microbench_crc32.txt" 2>/dev/null || echo "N/A"
echo ""
echo "--- Allocation Microbenchmark ---"
cat "${RESULTS}/microbench_alloc.txt" 2>/dev/null || echo "N/A"
echo ""
echo "--- Release Binary Size ---"
cat "${RESULTS}/total_release_size.txt" 2>/dev/null || echo "N/A"
echo ""
echo "--- Source Statistics ---"
echo "Source files: $(cat ${RESULTS}/source_file_count.txt 2>/dev/null || echo N/A)"
echo "Crate count: $(cat ${RESULTS}/crate_count.txt 2>/dev/null || echo N/A)"
echo "============================================================"
REPORT_EOF

# --------------------------------------------------
# Phase 9: Teardown
# --------------------------------------------------
echo ""
echo ">>> Phase 9: Tearing down VM..."

gcloud compute instances delete "${VM_NAME}" \
    --zone="${ZONE}" --project="${PROJECT_ID}" --quiet

echo ""
echo "============================================================"
echo " Benchmark complete! Results saved to:"
echo "   ${RESULTS_DIR}/"
echo "============================================================"
