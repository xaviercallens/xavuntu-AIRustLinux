#!/bin/bash
set -e

echo "============================================================"
echo " Executing MVK Pure no_std Hardware Benchmark (C2)          "
echo "============================================================"

source $HOME/.cargo/env

echo "[1] Compiling Pure no_std Rust Harness..."
rustc -C opt-level=3 -C lto=fat -C target-cpu=native -C panic=abort -C link-arg=-nostartfiles harness_nostd.rs -o harness_nostd

echo ""
echo "==================== EXECUTION RESULTS ===================="
./harness_nostd
echo "============================================================"
