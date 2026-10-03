#!/usr/bin/env bash
set -e

# Usage: ./run_fuzzing.sh <fuzz_target> <duration_seconds>
TARGET=${1:-fuzz_packet}
DURATION=${2:-30}

echo "[INFO] Setting up Rust Nightly toolchain for fuzzing..."
rustup toolchain install nightly
rustup default nightly

if ! command -v cargo-fuzz &> /dev/null; then
    echo "[INFO] Installing cargo-fuzz..."
    rustup toolchain install stable
    cargo +stable install cargo-fuzz
fi

cd fuzz
echo "[INFO] Running fuzzer on target: ${TARGET} for ${DURATION} seconds..."
cargo +nightly fuzz run ${TARGET} -- -max_total_time=${DURATION}

echo "[SUCCESS] Fuzzing complete for ${TARGET}."
# Revert to stable
rustup default stable
