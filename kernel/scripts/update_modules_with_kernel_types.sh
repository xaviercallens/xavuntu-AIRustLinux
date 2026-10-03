#!/bin/bash
# Update all crate manifests to include kernel_types dependency
# and add imports to all lib.rs files

set -e

WORKSPACE_ROOT="/Users/xcallens/rust-linux-mini-kernel"
cd "$WORKSPACE_ROOT"

echo "============================================"
echo "Updating all modules with kernel_types"
echo "============================================"

# Step 1: Add dependency to all Cargo.toml files (except kernel_types itself)
echo ""
echo "Step 1: Adding kernel_types dependency to all crates..."
updated_count=0

for manifest in crates/*/Cargo.toml; do
    crate_name=$(basename $(dirname "$manifest"))

    # Skip kernel_types itself
    if [ "$crate_name" = "kernel_types" ]; then
        continue
    fi

    # Check if already has kernel_types dependency
    if ! grep -q "kernel_types" "$manifest"; then
        echo "  - $crate_name"
        echo "" >> "$manifest"
        echo "kernel_types = { path = \"../kernel_types\" }" >> "$manifest"
        ((updated_count++))
    fi
done

echo "✅ Added kernel_types to $updated_count crates"

# Step 2: Add imports to all lib.rs files
echo ""
echo "Step 2: Adding kernel_types imports to all lib.rs files..."
import_count=0

for librs in crates/*/src/lib.rs; do
    crate_name=$(basename $(dirname $(dirname "$librs")))

    # Skip kernel_types itself
    if [ "$crate_name" = "kernel_types" ]; then
        continue
    fi

    # Check if already has kernel_types import
    if ! grep -q "use kernel_types::" "$librs"; then
        echo "  - $crate_name"
        # Create temp file with import at the top
        echo "use kernel_types::*;" > "$librs.tmp"
        echo "" >> "$librs.tmp"
        cat "$librs" >> "$librs.tmp"
        mv "$librs.tmp" "$librs"
        ((import_count++))
    fi
done

echo "✅ Added imports to $import_count lib.rs files"

# Step 3: Verify kernel_types compiles
echo ""
echo "Step 3: Verifying kernel_types crate compiles..."
if cargo check --manifest-path crates/kernel_types/Cargo.toml 2>&1 | grep -q "Finished"; then
    echo "✅ kernel_types compiles successfully"
else
    echo "⚠️  kernel_types has compilation issues (will be fixed by Codex)"
fi

# Step 4: Summary
echo ""
echo "============================================"
echo "Update Complete"
echo "============================================"
echo "Updated: $updated_count Cargo.toml files"
echo "Updated: $import_count lib.rs files"
echo ""
echo "Next step: Test compilation"
echo "  cd $WORKSPACE_ROOT"
echo "  cargo build --workspace 2>&1 | head -50"
