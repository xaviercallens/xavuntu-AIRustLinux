#!/bin/bash
# Fix kernel_types import placement - must come after doc comments and attributes

WORKSPACE="/Users/xcallens/rust-linux-mini-kernel"
cd "$WORKSPACE"

echo "Fixing kernel_types import placement in all modules..."

for librs in crates/*/src/lib.rs; do
    crate_name=$(basename $(dirname $(dirname "$librs")))

    # Skip kernel_types itself
    if [ "$crate_name" = "kernel_types" ]; then
        continue
    fi

    # Check if file has kernel_types import in wrong place
    if grep -q "^use kernel_types::\*;" "$librs"; then
        echo "  Fixing $crate_name..."

        # Create temp file
        temp_file=$(mktemp)

        # Read the file and reconstruct correctly
        {
            # First, output everything EXCEPT the misplaced kernel_types line
            grep -v "^use kernel_types::\*;" "$librs" | \
            awk '
            # Print everything until we find the first non-doc-comment line
            /^#!\[/ { attrs=1 }
            attrs && /^$/ {
                # After attributes and before first real code, insert the use statement
                if (!inserted) {
                    print ""
                    print "use kernel_types::*;"
                    inserted=1
                }
            }
            { print }
            END {
                # If we never inserted (no attributes), add at end of initial comments
                if (!inserted && !attrs) {
                    print ""
                    print "use kernel_types::*;"
                }
            }
            '
        } > "$temp_file"

        # Only replace if temp file is not empty and different
        if [ -s "$temp_file" ] && ! cmp -s "$librs" "$temp_file"; then
            mv "$temp_file" "$librs"
            echo "    ✓ Fixed $crate_name"
        else
            rm "$temp_file"
            echo "    - Skipped $crate_name (no change needed)"
        fi
    fi
done

echo ""
echo "✅ Import placement fixed"
echo ""
echo "Testing a module..."
cd crates/af_inet && cargo check 2>&1 | head -10
