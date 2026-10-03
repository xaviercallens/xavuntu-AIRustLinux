#!/usr/bin/env python3
"""
Import consolidation script for Rust code.
Consolidates multiple use statements from the same module into a single line.
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

def consolidate_imports_in_file(file_path):
    """Consolidate imports in a single file."""
    with open(file_path, 'r') as f:
        lines = f.readlines()

    # Track changes
    changes = 0

    # Find all import groups to consolidate
    i = 0
    while i < len(lines):
        # Check for core:: imports
        if lines[i].strip().startswith('use core::'):
            # Find all consecutive core:: imports
            core_imports = defaultdict(list)
            start_idx = i

            while i < len(lines) and lines[i].strip().startswith('use core::'):
                line = lines[i].strip()
                # Parse: use core::module::item;
                match = re.match(r'use core::([^:]+)::\{?([^}]+)\}?;', line)
                if match:
                    module = match.group(1)
                    items = match.group(2)
                    # Split on comma if multiple items
                    for item in items.split(','):
                        core_imports[module].append(item.strip())
                else:
                    # Single item import: use core::module;
                    match = re.match(r'use core::([^;]+);', line)
                    if match:
                        path = match.group(1)
                        if '::' in path:
                            parts = path.split('::')
                            module = parts[0]
                            item = '::'.join(parts[1:])
                            core_imports[module].append(item)
                        else:
                            core_imports[path].append('')
                i += 1

            # Consolidate if we found multiple imports
            if len(core_imports) > 1 or any(len(items) > 1 for items in core_imports.values()):
                # Build consolidated imports
                new_lines = []
                for module in sorted(core_imports.keys()):
                    items = core_imports[module]
                    if all(item == '' for item in items):
                        # Just module import
                        new_lines.append(f'use core::{module};\n')
                    else:
                        # Filter out empty items
                        items = [item for item in items if item]
                        if items:
                            if len(items) == 1:
                                new_lines.append(f'use core::{module}::{items[0]};\n')
                            else:
                                # Sort items
                                items = sorted(set(items))
                                items_str = ', '.join(items)
                                if len(f'use core::{module}::{{{items_str}}};') <= 100:
                                    new_lines.append(f'use core::{module}::{{{items_str}}};\n')
                                else:
                                    # Too long, keep separate
                                    for item in items:
                                        new_lines.append(f'use core::{module}::{item};\n')

                # Replace old lines with new consolidated ones
                saved = (i - start_idx) - len(new_lines)
                if saved > 0:
                    lines[start_idx:i] = new_lines
                    changes += saved
                    i = start_idx + len(new_lines)
        else:
            i += 1

    # Write back if changes were made
    if changes > 0:
        with open(file_path, 'w') as f:
            f.writelines(lines)
        return changes
    return 0

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: consolidate_imports.py <directory>")
        sys.exit(1)

    base_dir = Path(sys.argv[1])
    total_saved = 0
    files_changed = 0

    # Find all Rust files
    for rs_file in base_dir.rglob('*.rs'):
        saved = consolidate_imports_in_file(rs_file)
        if saved > 0:
            files_changed += 1
            total_saved += saved
            print(f"✓ {rs_file.relative_to(base_dir)}: -{saved} lines")

    print(f"\nTotal: {files_changed} files changed, {total_saved} lines saved")

if __name__ == '__main__':
    main()
