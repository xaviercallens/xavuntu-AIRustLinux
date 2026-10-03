#!/usr/bin/env python3
"""
Automatically fix common Rust compilation issues in kernel modules
Handles C-style syntax, missing FFI markers, and common errors
"""

import os
import re
from pathlib import Path
from typing import List, Tuple


class ModuleFixer:
    """Fixes common compilation issues in Rust kernel modules"""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.fixes_applied = {
            "goto_removed": 0,
            "arrow_fixed": 0,
            "labels_removed": 0,
            "repr_c_added": 0,
            "extern_c_added": 0,
            "no_mangle_added": 0,
            "type_keyword_fixed": 0,
        }

    def fix_goto_statements(self, content: str) -> str:
        """Remove goto statements and labels"""
        # Remove goto statements
        content = re.sub(r'\s*goto\s+\w+;', '', content)
        self.fixes_applied["goto_removed"] += content.count("goto")

        # Remove labels (word followed by colon at start of line)
        lines = content.split('\n')
        fixed_lines = []
        for line in lines:
            if re.match(r'^\s*\w+:\s*$', line):
                self.fixes_applied["labels_removed"] += 1
                continue  # Skip label lines
            fixed_lines.append(line)

        return '\n'.join(fixed_lines)

    def fix_arrow_operator(self, content: str) -> str:
        """Replace -> with proper Rust field access"""
        # Pattern: (*variable).field or variable.field instead of variable->field
        def replace_arrow(match):
            var = match.group(1)
            field = match.group(2)
            self.fixes_applied["arrow_fixed"] += 1
            # If variable name suggests it's already a pointer dereference
            if var.startswith('(*') or not var.startswith('*'):
                return f"(*{var}).{field}"
            return f"{var}.{field}"

        content = re.sub(r'(\w+)->(\w+)', replace_arrow, content)
        return content

    def fix_type_keyword(self, content: str) -> str:
        """Fix usage of 'type' as a field name (Rust keyword)"""
        # Replace .type with .r#type or .type_field
        content = re.sub(r'\.type\b', '.type_field', content)
        self.fixes_applied["type_keyword_fixed"] += content.count(".type_field")
        return content

    def add_ffi_markers(self, content: str) -> Tuple[str, bool]:
        """Add missing FFI compatibility markers"""
        modified = False

        # Add #[repr(C)] to structs without it
        struct_pattern = r'(^|\n)(pub\s+)?struct\s+(\w+)\s*\{'
        structs = re.finditer(struct_pattern, content, re.MULTILINE)

        for match in structs:
            struct_start = match.start()
            # Check if #[repr(C)] is already before this struct
            preceding = content[max(0, struct_start - 100):struct_start]
            if '#[repr(C)]' not in preceding:
                # Insert #[repr(C)] before the struct
                content = (content[:struct_start] +
                          '\n#[repr(C)]\n' +
                          content[struct_start:])
                self.fixes_applied["repr_c_added"] += 1
                modified = True

        # Add #[no_mangle] to pub extern "C" functions without it
        func_pattern = r'(^|\n)(pub\s+)?(unsafe\s+)?extern\s+"C"\s+fn\s+(\w+)'
        functions = re.finditer(func_pattern, content, re.MULTILINE)

        for match in functions:
            func_start = match.start()
            # Check if #[no_mangle] is already before this function
            preceding = content[max(0, func_start - 100):func_start]
            if '#[no_mangle]' not in preceding:
                content = (content[:func_start] +
                          '\n#[no_mangle]\n' +
                          content[func_start:])
                self.fixes_applied["no_mangle_added"] += 1
                modified = True

        return content, modified

    def fix_module(self, module_path: Path) -> bool:
        """Fix a single module's lib.rs file"""
        lib_file = module_path / "src" / "lib.rs"

        if not lib_file.exists():
            return False

        try:
            with open(lib_file, 'r', encoding='utf-8') as f:
                content = f.read()

            original_content = content

            # Apply fixes
            content = self.fix_goto_statements(content)
            content = self.fix_arrow_operator(content)
            content = self.fix_type_keyword(content)
            content, ffi_modified = self.add_ffi_markers(content)

            # Only write if something changed
            if content != original_content:
                with open(lib_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True

        except Exception as e:
            print(f"Error processing {module_path.name}: {e}")
            return False

        return False

    def fix_all_modules(self) -> None:
        """Fix all modules in the workspace"""
        crates_dir = self.workspace_root / "crates"

        if not crates_dir.exists():
            print(f"Error: Crates directory not found at {crates_dir}")
            return

        modules = [d for d in crates_dir.iterdir() if d.is_dir()]
        total = len(modules)
        fixed = 0

        print(f"Found {total} modules to fix")
        print("")

        for module in sorted(modules):
            if self.fix_module(module):
                print(f"✅ Fixed: {module.name}")
                fixed += 1
            else:
                print(f"⚪ Skipped: {module.name}")

        print("")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("SUMMARY")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"Total modules: {total}")
        print(f"Modules fixed: {fixed}")
        print(f"Modules skipped: {total - fixed}")
        print("")
        print("Fixes applied:")
        for fix_type, count in self.fixes_applied.items():
            if count > 0:
                print(f"  - {fix_type.replace('_', ' ').title()}: {count}")
        print("")


def main():
    import sys

    workspace_root = sys.argv[1] if len(sys.argv) > 1 else "/workspace"

    print("╔════════════════════════════════════════════════════════════════╗")
    print("║        RUST KERNEL MODULE AUTOMATIC FIXER                     ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print("")
    print(f"Workspace: {workspace_root}")
    print("")

    fixer = ModuleFixer(workspace_root)
    fixer.fix_all_modules()

    print("✅ Fixing complete!")


if __name__ == '__main__':
    main()
