import os
import json
import glob

def build_master_spec():
    spec_dir = "/Volumes/MacCleanerStorage/xdev/xavux/rust-linux-mini-kernel/scenario_b_specs"
    output_file = os.path.join(spec_dir, "SCENARIO_B_MASTER_SPECIFICATION.md")
    
    json_files = sorted(glob.glob(os.path.join(spec_dir, "*_spec.json")))
    
    type_mappings = {}
    ownership_patterns = {}
    error_paths = []
    modules = {}
    concurrency_notes = []
    invariants = []
    
    for file_path in json_files:
        module_name = os.path.basename(file_path).replace("_spec.json", "").capitalize()
        with open(file_path, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue
            
            # Functions
            funcs = data.get("functions", [])
            if funcs:
                modules[module_name] = funcs
            
            # Types (Deduplicate keeping the most detailed notes)
            for t in data.get("types", []):
                cpp = t.get('cpp', '').strip()
                rust = t.get('rust', '').strip()
                if not cpp or not rust: continue
                
                key = cpp
                if key not in type_mappings or len(t.get('notes', '')) > len(type_mappings[key].get('notes', '')):
                    type_mappings[key] = t
                
            # Ownership patterns
            for o in data.get("ownership", []):
                cpp_pat = o.get('cpp_pattern', '').strip()
                if not cpp_pat: continue
                if cpp_pat not in ownership_patterns or len(o.get('rationale', '')) > len(ownership_patterns[cpp_pat].get('rationale', '')):
                    ownership_patterns[cpp_pat] = o
                
            # Error Paths
            for e in data.get("error_paths", []):
                if e.get("source"):
                    e['module'] = module_name
                    error_paths.append(e)
                
            # Invariants
            inv = data.get("invariants", [])
            if isinstance(inv, list):
                for i in inv:
                    if i.strip():
                        invariants.append(f"**{module_name}**: {i.strip()}")
                    
            # Concurrency
            conc = data.get("concurrency", {})
            if isinstance(conc, dict) and conc:
                safety = conc.get("thread_safety", "").strip()
                shared = [s for s in conc.get("shared_state", []) if s.strip() and s.strip().lower() != 'none']
                if safety or shared:
                    concurrency_notes.append({
                        "module": module_name,
                        "safety": safety,
                        "shared": shared
                    })
                
    with open(output_file, 'w') as out:
        out.write("# Scenario B: Master Pricer - Unified Translation Specification\n\n")
        out.write("This master specification defines the architectural rules, type mappings, and safety invariants for translating the Master Pricer C++ codebase to Rust.\n\n")
        
        out.write("## Table of Contents\n")
        out.write("1. [Type Mappings](#1-type-mappings)\n")
        out.write("2. [Ownership & Lifetime Patterns](#2-ownership--lifetime-patterns)\n")
        out.write("3. [Error Handling (Exceptions -> Results)](#3-error-handling-exceptions---results)\n")
        out.write("4. [Concurrency & Thread Safety](#4-concurrency--thread-safety)\n")
        out.write("5. [System Invariants](#5-system-invariants)\n")
        out.write("6. [Module Function Contracts](#6-module-function-contracts)\n\n")
        
        out.write("## 1. Type Mappings\n")
        out.write("| C++ Type | Rust Type | Ownership | Notes |\n")
        out.write("|----------|-----------|-----------|-------|\n")
        for key in sorted(type_mappings.keys()):
            mapping = type_mappings[key]
            cpp = mapping.get('cpp', '').replace('|', '\\|')
            rust = mapping.get('rust', '').replace('|', '\\|')
            own = mapping.get('ownership', '').replace('|', '\\|')
            notes = mapping.get('notes', '').replace('|', '\\|').replace('\n', ' ').strip()
            out.write(f"| `{cpp}` | `{rust}` | `{own}` | {notes} |\n")
            
        out.write("\n## 2. Ownership & Lifetime Patterns\n")
        out.write("| C++ Pattern | Rust Pattern | Rationale |\n")
        out.write("|-------------|--------------|-----------|\n")
        for key in sorted(ownership_patterns.keys()):
            pattern = ownership_patterns[key]
            cpp = pattern.get('cpp_pattern', '').replace('|', '\\|')
            rust = pattern.get('rust_pattern', '').replace('|', '\\|')
            rat = pattern.get('rationale', '').replace('|', '\\|').replace('\n', ' ').strip()
            out.write(f"| {cpp} | {rust} | {rat} |\n")
            
        out.write("\n## 3. Error Handling (Exceptions -> Results)\n")
        out.write("| Module | Source (C++) | Recovery Strategy | Rust Pattern |\n")
        out.write("|--------|--------------|-------------------|--------------|\n")
        for e in error_paths:
            src = e.get('source', '')
            rec = e.get('recovery', '').replace('\n', ' ').strip()
            rst = e.get('rust', '')
            out.write(f"| **{e['module']}** | `{src}` | {rec} | `{rst}` |\n")
            
        out.write("\n## 4. Concurrency & Thread Safety\n")
        if not concurrency_notes:
            out.write("*No concurrency constraints defined in modules.*\n")
        for c in concurrency_notes:
            out.write(f"### {c['module']}\n")
            if c['safety']:
                out.write(f"- **Thread Safety**: {c['safety']}\n")
            if c['shared']:
                out.write("- **Shared State**: " + ", ".join([f"`{x}`" for x in c['shared']]) + "\n")
            out.write("\n")
            
        out.write("## 5. System Invariants\n")
        if not invariants:
            out.write("*No system invariants defined.*\n")
        for i in invariants:
            out.write(f"- {i}\n")
            
        out.write("\n## 6. Module Function Contracts\n")
        for mod in sorted(modules.keys()):
            funcs = modules[mod]
            out.write(f"### {mod} Module\n")
            for f in funcs:
                out.write(f"#### `{f.get('name', 'Unknown')}`\n")
                comp = f.get('complexity', 'N/A')
                if comp and comp.lower() != 'n/a':
                    out.write(f"- **Complexity**: {comp}\n")
                
                pre = [p for p in f.get('pre', []) if p.strip() and p.lower() != 'none']
                if pre:
                    out.write("- **Preconditions**:\n")
                    for p in pre: out.write(f"  - {p}\n")
                    
                post = [p for p in f.get('post', []) if p.strip() and p.lower() != 'none']
                if post:
                    out.write("- **Postconditions**:\n")
                    for p in post: out.write(f"  - {p}\n")
                    
                side = [s for s in f.get('side_effects', []) if s.strip() and s.lower() != 'none']
                if side:
                    out.write("- **Side Effects**:\n")
                    for s in side: out.write(f"  - {s}\n")
            out.write("\n")

if __name__ == "__main__":
    build_master_spec()
    print("Master specification improved and built successfully.")
