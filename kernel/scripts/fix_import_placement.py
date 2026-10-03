#!/usr/bin/env python3
"""
Fix kernel_types import placement in all modules.
Import must come AFTER module doc comments and attributes.
"""

from pathlib import Path
import re

workspace = Path("/Users/xcallens/rust-linux-mini-kernel")
fixed_count = 0

for lib_path in (workspace / "crates").glob("*/src/lib.rs"):
    crate_name = lib_path.parent.parent.name

    # Skip kernel_types itself
    if crate_name == "kernel_types":
        continue

    content = lib_path.read_text()

    # Check if kernel_types import is at the wrong place (before doc comments)
    if not content.startswith("use kernel_types::*;"):
        continue

    print(f"Fixing {crate_name}...")

    # Remove the misplaced import
    content = content.replace("use kernel_types::*;\n\n", "")
    content = content.replace("use kernel_types::*;\n", "")

    # Find where to insert: after attributes (#![...]) and before other code
    lines = content.split('\n')
    insert_pos = 0

    # Find last attribute line or last doc comment line
    for i, line in enumerate(lines):
        if line.startswith('//!') or line.startswith('#!['):
            insert_pos = i + 1
        elif line.strip() == '':
            continue
        elif line.startswith('use ') or line.startswith('pub ') or line.startswith('extern'):
            # Found first code line
            break

    # Skip any blank lines after attributes
    while insert_pos < len(lines) and lines[insert_pos].strip() == '':
        insert_pos += 1

    # Insert the import at correct position
    lines.insert(insert_pos, "")
    lines.insert(insert_pos + 1, "use kernel_types::*;")

    # Write back
    lib_path.write_text('\n'.join(lines))
    fixed_count += 1
    print(f"  ✓ Fixed {crate_name}")

print(f"\n✅ Fixed {fixed_count} modules")
