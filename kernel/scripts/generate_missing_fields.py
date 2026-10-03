#!/usr/bin/env python3
import os
import re
import subprocess
from collections import defaultdict

WORKSPACE_DIR = "/Volumes/MacCleanerStorage/xdev/xavux/rust-linux-mini-kernel"
KERNEL_TYPES_FILE = os.path.join(WORKSPACE_DIR, "crates/kernel_types/src/lib.rs")

def main():
    print("Running cargo check to gather missing fields...")
    # Run cargo check and capture stderr
    result = subprocess.run(
        ["cargo", "check", "--workspace"],
        cwd=WORKSPACE_DIR,
        capture_output=True,
        text=True
    )
    output = result.stderr

    # Regex to find missing fields (E0609)
    # format: error[E0609]: no field `sk_v6_rcv_saddr` on type `kernel_types::sock`
    pattern = r"no field `([^`]+)` on type `([^`]+)`"
    matches = re.findall(pattern, output)

    missing_fields = defaultdict(set)
    for field_name, raw_type_name in matches:
        # Clean up the type name
        type_name = raw_type_name.replace("kernel_types::", "")
        type_name = type_name.replace("*mut ", "")
        type_name = type_name.replace("*const ", "")
        type_name = type_name.replace("&mut ", "")
        type_name = type_name.replace("&", "")
        type_name = type_name.strip()
        
        missing_fields[type_name].add(field_name)

    if not missing_fields:
        print("No missing fields found. Exiting.")
        return

    print(f"Found {sum(len(fields) for fields in missing_fields.values())} missing fields across {len(missing_fields)} structs.")

    # Read existing kernel_types
    with open(KERNEL_TYPES_FILE, "r") as f:
        lines = f.readlines()

    added_fields = 0
    
    # Process each struct
    for struct_name, fields in missing_fields.items():
        # Find the start of the struct definition
        struct_start_idx = -1
        for i, line in enumerate(lines):
            # Matches pub struct name { or pub union name {
            if re.match(rf"^pub (struct|union) {struct_name}\b.*{{", line.strip()):
                struct_start_idx = i
                break
                
        if struct_start_idx == -1:
            print(f"Warning: Could not find struct/union definition for '{struct_name}' in kernel_types.")
            continue

        # Find the end of the struct
        struct_end_idx = -1
        for i in range(struct_start_idx + 1, len(lines)):
            if lines[i].strip() == "}":
                struct_end_idx = i
                break

        if struct_end_idx == -1:
            print(f"Warning: Could not find end of struct '{struct_name}'.")
            continue
            
        # Check existing fields to avoid duplicates
        existing_struct_content = "".join(lines[struct_start_idx:struct_end_idx])
        
        # Prepare fields to inject
        fields_to_inject = []
        for field in fields:
            if f"pub {field}:" not in existing_struct_content:
                fields_to_inject.append(f"    pub {field}: *mut core::ffi::c_void, // Auto-generated mock field\n")
                added_fields += 1

        if fields_to_inject:
            # Inject fields before the closing brace
            lines = lines[:struct_end_idx] + fields_to_inject + lines[struct_end_idx:]

    if added_fields > 0:
        with open(KERNEL_TYPES_FILE, "w") as f:
            f.writelines(lines)
        print(f"Successfully injected {added_fields} mock fields into kernel_types/src/lib.rs")
    else:
        print("All missing fields already mocked in kernel_types.")

if __name__ == "__main__":
    main()
