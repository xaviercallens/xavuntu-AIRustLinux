#!/bin/bash
#
# Clean thinking tags from all Rust modules
#

set -e

echo "Cleaning thinking tags from all modules..."

CLEANED=0
TOTAL=0

for lib_file in crates/*/src/lib.rs; do
    TOTAL=$((TOTAL + 1))

    if grep -q "^Okay, I need to\|^Let's\|^Starting with\|^First,\|^Now,\|^Next," "$lib_file" 2>/dev/null; then
        echo "Cleaning: $lib_file"

        # Remove thinking tags (lines starting with common thinking patterns)
        sed -i '' '/^Okay, I need to/,/^$/d' "$lib_file"
        sed -i '' '/^Let'\''s start/,/^$/d' "$lib_file"
        sed -i '' '/^Starting with/,/^$/d' "$lib_file"
        sed -i '' '/^First,/,/^$/d' "$lib_file"
        sed -i '' '/^Now,/,/^$/d' "$lib_file"
        sed -i '' '/^Next,/,/^$/d' "$lib_file"
        sed -i '' '/^So,/,/^$/d' "$lib_file"
        sed -i '' '/^Then,/,/^$/d' "$lib_file"
        sed -i '' '/^Also,/,/^$/d' "$lib_file"
        sed -i '' '/^Additionally,/,/^$/d' "$lib_file"
        sed -i '' '/^Finally,/,/^$/d' "$lib_file"
        sed -i '' '/^Looking at/,/^$/d' "$lib_file"
        sed -i '' '/^Reviewing/,/^$/d' "$lib_file"
        sed -i '' '/^Considering/,/^$/d' "$lib_file"
        sed -i '' '/^I'\''ll need to/,/^$/d' "$lib_file"
        sed -i '' '/^I'\''ll start/,/^$/d' "$lib_file"
        sed -i '' '/^I should/,/^$/d' "$lib_file"
        sed -i '' '/^The code/,/^$/d' "$lib_file"
        sed -i '' '/^This code/,/^$/d' "$lib_file"

        CLEANED=$((CLEANED + 1))
    fi
done

echo ""
echo "Summary:"
echo "  Total modules: $TOTAL"
echo "  Modules cleaned: $CLEANED"
echo "  Clean modules: $((TOTAL - CLEANED))"
echo ""
echo "Done!"
