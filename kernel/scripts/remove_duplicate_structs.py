#!/usr/bin/env python3
import os
import re
import glob

WORKSPACE_DIR = "/Volumes/MacCleanerStorage/xdev/xavux/rust-linux-mini-kernel"
KERNEL_TYPES_FILE = os.path.join(WORKSPACE_DIR, "crates/kernel_types/src/lib.rs")

def get_kernel_structs():
    structs = set()
    with open(KERNEL_TYPES_FILE, 'r') as f:
        for line in f:
            m = re.match(r'^pub\s+(struct|union)\s+([a-zA-Z0-9_]+)', line.strip())
            if m:
                structs.add(m.group(2))
    return structs

def process_file(filepath, kernel_structs):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    new_lines = []
    attr_buffer = []
    deleting = False
    brace_depth = 0
    deleted_count = 0

    for line in lines:
        stripped = line.strip()

        if deleting:
            # count braces to know when struct ends
            brace_depth += line.count('{')
            brace_depth -= line.count('}')
            if brace_depth <= 0:
                deleting = False
            continue

        if stripped.startswith('#['):
            attr_buffer.append(line)
            continue

        m = re.match(r'^pub\s+(struct|union)\s+([a-zA-Z0-9_]+)', stripped)
        if m:
            struct_name = m.group(2)
            if struct_name in kernel_structs:
                # We want to delete this struct
                deleting = True
                brace_depth = line.count('{') - line.count('}')
                attr_buffer = [] # discard buffered attributes
                deleted_count += 1
                
                # If the struct is a single line `pub struct X;` or `pub struct X {}`
                if brace_depth <= 0 and '{' in line and '}' in line:
                    deleting = False
                continue

        # If not deleting and not a struct matching, emit any buffered attributes and the line
        if attr_buffer:
            new_lines.extend(attr_buffer)
            attr_buffer = []
        new_lines.append(line)

    if deleted_count > 0:
        with open(filepath, 'w') as f:
            f.writelines(new_lines)
        print(f"Removed {deleted_count} duplicate structs from {os.path.relpath(filepath, WORKSPACE_DIR)}")
    
    return deleted_count

def main():
    kernel_structs = get_kernel_structs()
    print(f"Found {len(kernel_structs)} shared structs in kernel_types.")

    search_pattern = os.path.join(WORKSPACE_DIR, "crates/*/src/*.rs")
    files = glob.glob(search_pattern)

    total_deleted = 0
    for filepath in files:
        if "kernel_types" in filepath:
            continue
        total_deleted += process_file(filepath, kernel_structs)

    print(f"\nTotal duplicate structs removed: {total_deleted}")

if __name__ == "__main__":
    main()
