#!/bin/bash
set -e

echo "============================================================"
echo " Starting MVK vs Linux Advanced Hardware Benchmark (C2)     "
echo " (Testing IPC, Page Faults, and I/O Streams)                "
echo "============================================================"

echo ""
echo "[1] Compiling C-Kernel Advanced Harness..."
gcc -O3 -pthread harness_advanced.c -o harness_advanced_c

echo "[2] Compiling Rust MVK Advanced Benchmark Harness..."
if [ ! -d "harness_advanced_rs" ]; then
    cargo new harness_advanced_rs --bin >/dev/null 2>&1
    cp harness_advanced.rs harness_advanced_rs/src/main.rs
    cd harness_advanced_rs
    cargo add libc >/dev/null 2>&1
    cd ..
fi

cd harness_advanced_rs
cargo build --release >/dev/null 2>&1
cd ..

echo ""
echo "==================== EXECUTION RESULTS ===================="
echo ""
echo "--- Linux C-Kernel Baseline ---"
./harness_advanced_c

echo ""
echo "--- Rust MVK Architecture Equivalent ---"
./harness_advanced_rs/target/release/harness_advanced_rs

echo ""
echo "============================================================"
echo " Advanced Benchmark Execution Complete on C2 Hardware!"
echo "============================================================"
