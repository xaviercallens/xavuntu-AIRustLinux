#!/bin/bash
#
# Generate Cargo.toml for each crate
#

set -e

cd /Users/xcallens/rust-linux-mini-kernel

for crate_dir in crates/*/; do
    crate_name=$(basename "$crate_dir")

    cat > "$crate_dir/Cargo.toml" << EOF
[package]
name = "$crate_name"
version.workspace = true
edition.workspace = true
authors.workspace = true
license.workspace = true

[lib]
path = "src/lib.rs"
crate-type = ["staticlib", "rlib"]

[dependencies]
libc.workspace = true
EOF

    echo "✅ Created Cargo.toml for $crate_name"
done

echo ""
echo "Generated Cargo.toml for $(ls crates/ | wc -l | tr -d ' ') crates"
