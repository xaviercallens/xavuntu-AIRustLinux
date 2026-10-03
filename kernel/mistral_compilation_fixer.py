#!/usr/bin/env python3
"""
Mistral Compilation Fixer
Automatically fixes Rust compilation errors using the Mistral API (Codestral).
Runs continuously overnight.
"""

import os
import json
import time
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class MistralCompilationFixer:
    def __init__(self, workspace_root: str, api_key: str):
        self.workspace_root = Path(workspace_root)
        self.crates_dir = self.workspace_root / "crates"
        self.results_dir = self.workspace_root / "compilation_fixes"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key

        self.stats = {
            "total_modules": 0,
            "attempted_fixes": 0,
            "successful_fixes": 0,
            "failed_fixes": 0,
            "compilation_errors_fixed": 0,
            "start_time": datetime.now().isoformat(),
            "modules": []
        }

    def call_mistral(self, prompt: str) -> Optional[str]:
        """Call Mistral Codestral API"""
        time.sleep(1) # Simple rate limit protection
        
        try:
            url = "https://api.mistral.ai/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            payload = {
                "model": "codestral-latest",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert Rust systems programmer specializing in Linux kernel FFI code. Fix compilation errors while maintaining C FFI compatibility. Fix invalid 'goto' statements by rewriting them into proper Rust control flow (like match, loop, or early return). Fix duplicate struct definitions by keeping only one. Always use #[repr(C)] for structs, extern \"C\" for functions, and proper unsafe blocks. Return ONLY valid raw Rust code. Do not wrap in markdown ```rust ticks."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.1
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=90, verify=False)
            if response.status_code == 429:
                print("Rate limited by Mistral API. Sleeping for 20s...")
                time.sleep(20)
                return self.call_mistral(prompt)
                
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"Error calling Mistral API: {e}")
            if "429" in str(e):
                time.sleep(20)
            return None

    def compile_module(self, module_name: str) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                ["cargo", "build", "--package", module_name],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr
        except Exception as e:
            return False, f"Compilation error: {str(e)}"

    def extract_compilation_errors(self, error_output: str) -> List[Dict]:
        errors = []
        current_error = None

        for line in error_output.split('\n'):
            error_match = re.match(r'error(\[E\d+\])?: (.+)', line)
            if error_match:
                if current_error:
                    errors.append(current_error)
                current_error = {"type": "error", "code": error_match.group(1) or "E0000", "message": error_match.group(2), "location": "", "context": []}
                continue

            location_match = re.match(r'\s+-->\s+(.+):(\d+):(\d+)', line)
            if location_match and current_error:
                current_error["location"] = {"file": location_match.group(1), "line": int(location_match.group(2)), "column": int(location_match.group(3))}
                continue

            if current_error and line.strip():
                current_error["context"].append(line)

        if current_error:
            errors.append(current_error)
        return errors

    def read_module_source(self, module_name: str) -> str:
        lib_file = self.crates_dir / module_name / "src" / "lib.rs"
        try:
            return lib_file.read_text()
        except:
            return ""

    def write_module_source(self, module_name: str, content: str) -> bool:
        lib_file = self.crates_dir / module_name / "src" / "lib.rs"
        try:
            lib_file.write_text(content)
            return True
        except:
            return False

    def apply_mistral_fix(self, module_name: str, source_code: str, errors: List[Dict]) -> Optional[str]:
        error_summary = "\n".join([f"- {err['type']}{err['code']}: {err['message']}" for err in errors[:10]]) # Give up to 10 errors
        
        # Load formal constraints
        try:
            kernel_types = Path("/Volumes/MacCleanerStorage/xdev/xavux/rust-linux-mini-kernel/crates/kernel_types/src/lib.rs").read_text()[:4000]
        except:
            kernel_types = ""
            
        try:
            scenario_spec = Path("/Volumes/MacCleanerStorage/xdev/xavux/rust-linux-mini-kernel/specifications/KERNEL_TYPES_SPECIFICATION.md").read_text()[:6000]
        except:
            scenario_spec = ""
        
        prompt = f"""Fix the following Rust compilation errors in the Linux kernel FFI module '{module_name}'.

Compilation errors:
{error_summary}

Relevant code section:
```rust
{source_code}
```

Requirements:
1. Fix ALL compilation errors
2. Maintain C FFI compatibility (use #[repr(C)], extern "C", #[no_mangle])
3. Keep unsafe blocks where needed
4. Don't add unnecessary features
5. Preserve the original structure and logic. Ensure proper no_std compatibility.
6. Fix duplicate definitions. Fix bad pointer casts. Fix goto statements by using Rust idioms.
7. Return ONLY the fixed Rust code. Do NOT output markdown formatting like ```rust. Just the raw code.
8. CRITICAL: The workspace now includes a shared `kernel_types` crate. Ensure you do NOT redefine kernel types (like sk_buff, flowi, inet_sock). Assume `use kernel_types::*;` brings them into scope!

Formal Mathematical & Translation Constraints (Use these patterns where applicable):
---
KERNEL SHARED TYPES AVAILABLE (Do not redefine these):
{kernel_types}
---
TRANSLATION SPEC CONTEXT:
{scenario_spec}
"""
        fixed_code = self.call_mistral(prompt)
        if not fixed_code: return None
        
        # Extract code block using regex in case of conversational prefix
        import re
        match = re.search(r'```(?:rust)?\s*(.*?)(?:```|$)', fixed_code, re.DOTALL)
        if match and len(match.group(1)) > 50:
            fixed_code = match.group(1).strip()
        else:
            fixed_code = fixed_code.strip()
            
        return fixed_code

    def fix_module(self, module_name: str):
        print(f"\nProcessing: {module_name}")
        result = {"module": module_name, "success": False, "iterations": []}

        success, error_output = self.compile_module(module_name)
        if success:
            print(f"✅ {module_name} already compiles")
            result["success"] = True
            return result

        errors = self.extract_compilation_errors(error_output)
        result["initial_errors"] = len(errors)
        print(f"Found {len(errors)} errors in {module_name}")

        for iteration in range(3): # max 3 attempts
            source_code = self.read_module_source(module_name)
            if not source_code: break

            print(f"Attempting Mistral fix (Iter {iteration+1})...")
            fixed_code = self.apply_mistral_fix(module_name, source_code, errors)
            if not fixed_code: break

            self.write_module_source(module_name, fixed_code)
            success, error_output = self.compile_module(module_name)
            
            if success:
                print(f"✅ {module_name} fixed!")
                result["success"] = True
                self.stats["successful_fixes"] += 1
                break
            else:
                errors = self.extract_compilation_errors(error_output)
                print(f"Still failing with {len(errors)} errors")
                
        if not result.get("success"):
            self.stats["failed_fixes"] += 1
        return result

    def run_overnight_batch(self):
        modules = [d.name for d in self.crates_dir.iterdir() if d.is_dir() and (d / "src" / "lib.rs").exists()]
        self.stats["total_modules"] = len(modules)
        
        print(f"Starting Mistral Codestral Fixer on {len(modules)} modules...")
        
        for module in modules:
            self.stats["attempted_fixes"] += 1
            res = self.fix_module(module)
            self.stats["modules"].append(res)
            
            # Checkpoint
            with open(self.results_dir / "mistral_checkpoint.json", "w") as f:
                json.dump(self.stats, f)

if __name__ == "__main__":
    API_KEY = "CQrIoijW25PNLmejFHbMmaRP5oJorLE7"
    workspace = "/Volumes/MacCleanerStorage/xdev/xavux/rust-linux-mini-kernel"
    fixer = MistralCompilationFixer(workspace, API_KEY)
    fixer.run_overnight_batch()
    print("Nightly batch complete!")
