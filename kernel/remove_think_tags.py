#!/usr/bin/env python3
"""
Remove <think>...</think> tags from all Rust source files
"""

import re
from pathlib import Path


def remove_think_blocks(content: str) -> tuple[str, int]:
    """Remove all <think>...</think> blocks including multiline"""

    # Pattern to match <think>...</think> including nested and multiline content
    pattern = r'<think>.*?</think>'

    # Count occurrences
    matches = re.findall(pattern, content, re.DOTALL)
    count = len(matches)

    if count > 0:
        # Remove all thinking tags
        cleaned = re.sub(pattern, '', content, flags=re.DOTALL)

        # Remove extra blank lines (more than 2 consecutive)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        # Remove leading whitespace
        cleaned = cleaned.lstrip()

        return cleaned, count

    return content, 0


def process_directory(root_dir: Path):
    """Process all lib.rs files in the directory"""

    processed = 0
    cleaned = 0
    total_tags = 0

    for lib_file in root_dir.glob('crates/*/src/lib.rs'):
        processed += 1

        try:
            with open(lib_file, 'r', encoding='utf-8') as f:
                original = f.read()

            cleaned_content, tag_count = remove_think_blocks(original)

            if tag_count > 0:
                with open(lib_file, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)

                orig_size = len(original)
                clean_size = len(cleaned_content)
                saved = orig_size - clean_size

                print(f"✅ {lib_file.parent.parent.name}: removed {tag_count} think blocks, saved {saved} bytes")
                cleaned += 1
                total_tags += tag_count

        except Exception as e:
            print(f"❌ Error processing {lib_file}: {e}")

    print(f"\nSummary:")
    print(f"  Processed: {processed} modules")
    print(f"  Cleaned: {cleaned} modules")
    print(f"  Total think blocks removed: {total_tags}")
    print(f"  Already clean: {processed - cleaned} modules")


if __name__ == '__main__':
    root = Path('/Users/xcallens/rust-linux-mini-kernel')
    process_directory(root)
