#!/usr/bin/env python3
"""
Remove narrative/thinking text from Rust source files
"""

import os
import re
from pathlib import Path


def clean_narrative(content: str) -> str:
    """Remove narrative text that looks like thinking/explanation"""

    lines = content.split('\n')
    cleaned_lines = []
    skip_until_blank = False

    narrative_patterns = [
        r'^Okay, I need to',
        r'^Let\'s start',
        r'^Starting with',
        r'^First,?\s+I',
        r'^Now,?\s+I',
        r'^Next,?\s+I',
        r'^So,?\s+I',
        r'^Then,?\s+I',
        r'^Also,?\s+I',
        r'^Additionally,?\s+I',
        r'^Finally,?\s+I',
        r'^Looking at',
        r'^Reviewing',
        r'^Considering',
        r'^I\'ll need to',
        r'^I\'ll start',
        r'^I should',
        r'^The code\s+',
        r'^This code\s+',
        r'^In C,\s+it\'s',
        r'^In Rust,\s+I',
    ]

    for line in lines:
        stripped = line.strip()

        # Check if this line starts a narrative block
        if any(re.match(pattern, stripped, re.IGNORECASE) for pattern in narrative_patterns):
            skip_until_blank = True
            continue

        # If we're skipping, continue until we hit a blank line or code
        if skip_until_blank:
            if not stripped:  # Blank line
                skip_until_blank = False
                continue
            elif stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                # Comment lines - might be part of narrative
                continue
            elif stripped.startswith('#') or stripped.startswith('use ') or stripped.startswith('pub '):
                # Actual code - stop skipping
                skip_until_blank = False
            else:
                # Still in narrative
                continue

        # Keep this line
        cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)


def process_directory(root_dir: Path):
    """Process all lib.rs files in the directory"""

    processed = 0
    cleaned = 0

    for lib_file in root_dir.glob('crates/*/src/lib.rs'):
        processed += 1

        try:
            with open(lib_file, 'r', encoding='utf-8') as f:
                original = f.read()

            cleaned_content = clean_narrative(original)

            if cleaned_content != original:
                with open(lib_file, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)

                orig_lines = len(original.split('\n'))
                clean_lines = len(cleaned_content.split('\n'))
                removed = orig_lines - clean_lines

                print(f"✅ {lib_file.parent.parent.name}: removed {removed} lines")
                cleaned += 1

        except Exception as e:
            print(f"❌ Error processing {lib_file}: {e}")

    print(f"\nSummary:")
    print(f"  Processed: {processed} modules")
    print(f"  Cleaned: {cleaned} modules")
    print(f"  Already clean: {processed - cleaned} modules")


if __name__ == '__main__':
    root = Path('/Users/xcallens/rust-linux-mini-kernel')
    process_directory(root)
