#!/usr/bin/env bash
# package_zenodo_artifact.sh — Package complete RunuX Lean 4 verification artifact
# for Zenodo DOI archival and open science replication.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist"
ARTIFACT_NAME="runux-lean4-verification-v16.0"
TARBALL="${DIST_DIR}/${ARTIFACT_NAME}.tar.gz"

echo "=== Building Zenodo Archival Package: ${ARTIFACT_NAME} ==="
mkdir -p "${DIST_DIR}"

TMP_DIR="$(mktemp -d)"
STAGE_DIR="${TMP_DIR}/${ARTIFACT_NAME}"
mkdir -p "${STAGE_DIR}"

# 1. Copy publication manuscript and PDF
echo "--> Bundling publication manuscript and compiled PDF..."
mkdir -p "${STAGE_DIR}/paper"
cp -r "${REPO_ROOT}/paper/runux_formal_verification"/* "${STAGE_DIR}/paper/"

# 2. Copy Lean 4 formal specifications
echo "--> Bundling Lean 4 formal specifications..."
mkdir -p "${STAGE_DIR}/specs/lean4"
cp -r "${REPO_ROOT}/sub_projects/rust_linux_mini_kernel/rust-linux-mini-kernel/specs/lean4/MVK" "${STAGE_DIR}/specs/lean4/"
cp "${REPO_ROOT}/sub_projects/rust_linux_mini_kernel/rust-linux-mini-kernel/specs/lean4/lakefile.lean" "${STAGE_DIR}/specs/lean4/"
cp "${REPO_ROOT}/sub_projects/rust_linux_mini_kernel/rust-linux-mini-kernel/specs/lean4/lean-toolchain" "${STAGE_DIR}/specs/lean4/"

# 3. Copy formal documentation and inventory
echo "--> Bundling formal module documentation..."
mkdir -p "${STAGE_DIR}/docs/formal"
cp "${REPO_ROOT}/sub_projects/rust_linux_mini_kernel/rust-linux-mini-kernel/docs/formal"/* "${STAGE_DIR}/docs/formal/"

# 4. Copy metrics snapshot and telemetry
echo "--> Bundling verified metrics and proof tokens..."
mkdir -p "${STAGE_DIR}/metrics"
cp "${REPO_ROOT}/sub_projects/rust_linux_mini_kernel/rust-linux-mini-kernel/docs/roadmap/metrics"/* "${STAGE_DIR}/metrics/"
cp "${REPO_ROOT}/zenodo.json" "${STAGE_DIR}/"

# 5. Create README for archival replication
cat << 'EOF' > "${STAGE_DIR}/README.md"
# RunuX Lean 4 Formal Verification Archival Artifact (Wave 16)

This archive contains the complete, reproducible formal verification artifacts,
specifications, and publication manuscript for the RunuX Minimum Viable Kernel.

## Contents:
- `paper/`: Publication manuscript in LaTeX (`main.tex`), vector figures, references (`references.bib`), and compiled PDF (`main.pdf`).
- `specs/lean4/`: 37 Lean 4 formal specification modules (12,164 LOC), 448 theorems and axioms.
- `docs/formal/`: Comprehensive module-by-module technical documentation and JSON inventory.
- `metrics/`: Check-in metrics snapshot (`metrics.json`, `metrics.md`) confirming 0 stubs, 609 tests, 87 sorrys, and 0.6098 safety ratio.
- `zenodo.json`: Open-access metadata.

## Verification:
To verify the Lean 4 proofs:
```bash
cd specs/lean4
lake build
```
EOF

# 6. Compress tarball
echo "--> Creating compressed tarball: ${TARBALL}..."
tar -czf "${TARBALL}" -C "${TMP_DIR}" "${ARTIFACT_NAME}"
rm -rf "${TMP_DIR}"

SHA256=$(sha256sum "${TARBALL}" | awk '{print $1}')
SIZE=$(du -h "${TARBALL}" | awk '{print $1}')

echo "================================================================"
echo "=== Zenodo Package Ready: ${TARBALL}"
echo "=== Size: ${SIZE} | SHA-256: ${SHA256}"
echo "================================================================"
