#!/usr/bin/env python3
import os
import re
import subprocess

WORKSPACE_DIR = "/Volumes/MacCleanerStorage/xdev/xavux/rust-linux-mini-kernel"
KERNEL_TYPES_FILE = os.path.join(WORKSPACE_DIR, "crates/kernel_types/src/lib.rs")

def main():
    print("Running cargo check to gather missing symbols...")
    # Run cargo check and capture stderr
    result = subprocess.run(
        ["cargo", "check", "--workspace"],
        cwd=WORKSPACE_DIR,
        capture_output=True,
        text=True
    )
    output = result.stderr

    # Regex to find missing functions and values (E0425)
    func_pattern = r"cannot find function `([^`]+)` in this scope"
    val_pattern = r"cannot find value `([^`]+)` in this scope"
    
    missing_funcs = set(re.findall(func_pattern, output))
    missing_vals = set(re.findall(val_pattern, output))

    # Remove overlaps (if something is both, prefer func)
    missing_vals = missing_vals - missing_funcs

    print(f"Found {len(missing_funcs)} missing functions.")
    print(f"Found {len(missing_vals)} missing values.")

    if not missing_funcs and not missing_vals:
        print("No missing symbols found. Exiting.")
        return

    # Read existing kernel_types to avoid duplicates
    with open(KERNEL_TYPES_FILE, "r") as f:
        existing_code = f.read()

    new_stubs = "\n// ============================================================================\n"
    new_stubs += "// Auto-generated Mock Stubs (Alternative to AI Fixer)\n"
    new_stubs += "// ============================================================================\n\n"

    added_funcs = 0
    for func in sorted(missing_funcs):
        # Check if macro already exists
        if f"macro_rules! {func}" in existing_code:
            continue
        # Generate a macro that accepts any arguments and returns 0 / null
        # This handles both 0 args and variadic args without strictly typechecking
        new_stubs += f"#[macro_export]\nmacro_rules! {func} {{\n"
        new_stubs += f"    ($($arg:tt)*) => {{ 0 }}\n"
        new_stubs += f"}}\n\n"
        added_funcs += 1

    added_vals = 0
    for val in sorted(missing_vals):
        if f"pub static mut {val}" in existing_code or f"pub const {val}" in existing_code:
            continue
        # Generate a dummy static value
        new_stubs += f"pub static mut {val}: *mut core::ffi::c_void = core::ptr::null_mut();\n"
        added_vals += 1

    if added_funcs > 0 or added_vals > 0:
        with open(KERNEL_TYPES_FILE, "a") as f:
            f.write(new_stubs)
        print(f"Successfully appended {added_funcs} macro stubs and {added_vals} value stubs to kernel_types/src/lib.rs")
    else:
        print("All missing symbols already mocked in kernel_types.")

if __name__ == "__main__":
    main()
