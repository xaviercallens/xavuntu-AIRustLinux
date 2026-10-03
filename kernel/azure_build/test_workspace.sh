#!/bin/bash
set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              WORKSPACE VERIFICATION TEST                       ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "1. Checking Rust environment..."
rustc --version
cargo --version
echo "✅ Rust OK"
echo ""

echo "2. Checking workspace structure..."
ls -la /workspace/
echo ""

echo "3. Checking Cargo.toml..."
if [ -f "/workspace/Cargo.toml" ]; then
    echo "✅ Cargo.toml found"
    head -20 /workspace/Cargo.toml
else
    echo "❌ Cargo.toml NOT found"
    exit 1
fi
echo ""

echo "4. Checking crates directory..."
CRATE_COUNT=$(ls -d /workspace/crates/*/ 2>/dev/null | wc -l)
echo "Found $CRATE_COUNT crate directories"
ls /workspace/crates/ | head -10
echo "..."
echo ""

echo "5. Checking build scripts..."
ls -la /usr/local/bin/*.sh
echo ""

echo "6. Testing cargo build on one module..."
cd /workspace
cargo build --package netfilter --release 2>&1 | tail -30 || echo "Build had errors (expected for some modules)"
echo ""

echo "✅ Workspace verification complete!"
