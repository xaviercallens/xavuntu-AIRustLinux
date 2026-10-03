#!/bin/bash
# ============================================================
# MVK Rust Kernel - Pod Entrypoint
# ============================================================
# Modes:
#   benchmark  - Boot kernel in QEMU + run full benchmark suite
#   server     - Boot kernel + start iperf3 server
#   idle       - Boot kernel + wait (for manual testing)
# ============================================================

set -euo pipefail

MODE="${1:-benchmark}"
KERNEL="/mvk/kernel/demo_kernel"
RESULTS_DIR="/mvk/results"
mkdir -p "$RESULTS_DIR"

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] $*"; }

# ----------------------------------------------------------
# Boot the MVK kernel in QEMU
# ----------------------------------------------------------
boot_kernel() {
    local boot_start=$(date +%s%N)

    log "Booting MVK Rust kernel in QEMU..."
    timeout 30 qemu-system-i386 \
        -kernel "$KERNEL" \
        -nographic \
        -no-reboot \
        -m 128M \
        -display none \
        2>&1 | tee "$RESULTS_DIR/qemu_boot.log" &
    QEMU_PID=$!

    # Wait for boot or timeout
    sleep 5

    local boot_end=$(date +%s%N)
    local boot_ms=$(( (boot_end - boot_start) / 1000000 ))
    log "QEMU boot completed in ${boot_ms}ms"
    echo "$boot_ms" > "$RESULTS_DIR/boot_time_ms.txt"
}

# ----------------------------------------------------------
# Run compute benchmarks (inside the pod, not QEMU guest)
# ----------------------------------------------------------
run_compute_benchmarks() {
    log "=== Phase 1: Compute Benchmarks ==="

    # 1.1 - Sysbench CPU
    log "Running sysbench CPU benchmark..."
    sysbench cpu --time=60 --threads=4 run > "$RESULTS_DIR/sysbench_cpu.txt" 2>&1
    grep "events per second" "$RESULTS_DIR/sysbench_cpu.txt" || true

    # 1.2 - Sysbench Memory
    log "Running sysbench memory benchmark..."
    sysbench memory --time=60 --threads=4 run > "$RESULTS_DIR/sysbench_memory.txt" 2>&1
    grep "transferred" "$RESULTS_DIR/sysbench_memory.txt" || true

    # 1.3 - CRC32 (Rust vs C head-to-head)
    log "Running CRC32 C vs Rust benchmark..."
    python3 /mvk/benchmarks/c_vs_rust_perf_report.py \
        --results-dir "$RESULTS_DIR" 2>&1 || log "CRC32 benchmark skipped (build tools missing)"

    log "Compute benchmarks complete."
}

# ----------------------------------------------------------
# Run network benchmarks (iperf3 / netperf)
# ----------------------------------------------------------
run_network_server() {
    log "Starting iperf3 server on port 5201..."
    iperf3 -s -D --logfile "$RESULTS_DIR/iperf3_server.log"

    log "Starting netperf server (netserver)..."
    netserver -D > "$RESULTS_DIR/netperf_server.log" 2>&1 &

    log "Network servers running."
}

run_network_benchmarks() {
    local target="${BENCHMARK_TARGET:-mvk-kernel-server}"

    log "=== Phase 2: Network Benchmarks ==="

    # 2.1 - TCP throughput
    log "Running iperf3 TCP throughput to $target..."
    iperf3 -c "$target" -t 60 -P 4 -J > "$RESULTS_DIR/iperf3_tcp.json" 2>&1 || true

    # 2.2 - UDP throughput
    log "Running iperf3 UDP throughput to $target..."
    iperf3 -c "$target" -u -b 10G -t 60 -J > "$RESULTS_DIR/iperf3_udp.json" 2>&1 || true

    # 2.3 - TCP RR latency
    log "Running netperf TCP_RR latency to $target..."
    netperf -H "$target" -t TCP_RR -l 60 -- \
        -o min_latency,mean_latency,p99_latency,max_latency \
        > "$RESULTS_DIR/netperf_tcp_rr.txt" 2>&1 || true

    log "Network benchmarks complete."
}

# ----------------------------------------------------------
# Run stress tests (for Phase 2: Under Load)
# ----------------------------------------------------------
run_stress_benchmarks() {
    log "=== Phase 2b: Performance Under Load ==="

    # CPU contention + iperf3
    log "Starting stress-ng CPU (75% load)..."
    stress-ng --cpu 6 --cpu-load 75 --timeout 70 &
    STRESS_PID=$!
    sleep 5
    run_network_benchmarks
    kill $STRESS_PID 2>/dev/null || true
    wait $STRESS_PID 2>/dev/null || true

    # Rename results
    mv "$RESULTS_DIR/iperf3_tcp.json" "$RESULTS_DIR/iperf3_tcp_under_stress.json" 2>/dev/null || true

    log "Stress benchmarks complete."
}

# ----------------------------------------------------------
# Collect results summary
# ----------------------------------------------------------
collect_results() {
    log "=== Collecting Results ==="

    cat > "$RESULTS_DIR/summary.json" << EOJSON
{
    "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
    "hostname": "$(hostname)",
    "pod_name": "${HOSTNAME:-unknown}",
    "kernel_type": "mvk-rust",
    "boot_time_ms": $(cat "$RESULTS_DIR/boot_time_ms.txt" 2>/dev/null || echo 0),
    "results_files": $(ls -1 "$RESULTS_DIR" | jq -R -s 'split("\n") | map(select(length > 0))')
}
EOJSON

    log "Results saved to $RESULTS_DIR/"
    ls -la "$RESULTS_DIR/"
}

# ----------------------------------------------------------
# Main
# ----------------------------------------------------------
case "$MODE" in
    benchmark)
        boot_kernel
        run_compute_benchmarks
        run_network_server
        # Wait for orchestrator to trigger network/stress tests
        log "Benchmark pod ready. Waiting for orchestrator..."
        collect_results
        # Keep pod alive for orchestrated tests
        tail -f /dev/null
        ;;
    server)
        boot_kernel
        run_network_server
        log "Server mode active. Waiting..."
        tail -f /dev/null
        ;;
    client)
        boot_kernel
        run_compute_benchmarks
        run_network_benchmarks
        run_stress_benchmarks
        collect_results
        log "Client benchmarks complete."
        tail -f /dev/null
        ;;
    idle)
        boot_kernel
        log "Idle mode. Use 'kubectl exec' to run tests manually."
        tail -f /dev/null
        ;;
    *)
        echo "Usage: $0 {benchmark|server|client|idle}"
        exit 1
        ;;
esac
