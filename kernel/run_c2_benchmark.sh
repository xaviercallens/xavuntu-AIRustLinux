#!/bin/bash
set -e

echo "============================================================"
echo " Starting MVK vs Linux C-Baseline Hardware Benchmark (C2)"
echo "============================================================"

# Install dependencies if missing
sudo apt-get update -qq
sudo apt-get install -y -qq build-essential curl libc6-dev >/dev/null 2>&1

# Install rustup if missing
if ! command -v rustc &> /dev/null; then
    echo "Installing Rust toolchain..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y >/dev/null 2>&1
    source $HOME/.cargo/env
fi

echo ""
echo "[1] Compiling C-Kernel Baseline Harness..."
gcc -O3 -pthread harness.c -o harness_c

echo "[2] Compiling Rust MVK Benchmark Harness..."
# Initialize a temporary crate to compile with libc dependency
if [ ! -d "harness_rs" ]; then
    cargo new harness_rs --bin >/dev/null 2>&1
    cp harness.rs harness_rs/src/main.rs
    cd harness_rs
    cargo add libc >/dev/null 2>&1
    cd ..
fi

cd harness_rs
cargo build --release >/dev/null 2>&1
cd ..

echo ""
echo "==================== EXECUTION RESULTS ===================="
echo ""
echo "--- Linux C-Kernel Baseline ---"
./harness_c

echo ""
echo "--- Rust MVK Architecture Equivalent ---"
./harness_rs/target/release/harness_rs

echo ""
echo "============================================================"
echo " Benchmark Execution Complete on C2 Hardware!"
echo "============================================================"
