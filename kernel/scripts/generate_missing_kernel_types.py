import json
import re
import os

cargo_out = "cargo_stderr.txt"
kernel_types_file = "crates/kernel_types/src/lib.rs"

missing_funcs = set()
with open(cargo_out, "r") as f:
    content = f.read()
    
# Extract E0425 errors for functions
pattern = r"cannot find function `([^`]+)` in this scope"
matches = re.findall(pattern, content)
for m in matches:
    missing_funcs.add(m)

print(f"Found {len(missing_funcs)} missing functions.")

extern_block = "\n// Auto-generated missing function stubs\nextern \"C\" {\n"
for func in sorted(missing_funcs):
    if func == "request_module":
        extern_block += f"    pub fn {func}(fmt: *const c_char, ...);\n"
    else:
        # Default mock signature
        extern_block += f"    pub fn {func}(...);\n"
extern_block += "}\n"

with open(kernel_types_file, "a") as f:
    f.write(extern_block)

print(f"Appended {len(missing_funcs)} stubs to {kernel_types_file}")
