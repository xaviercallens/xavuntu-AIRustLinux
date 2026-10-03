#!/usr/bin/env python3
"""
Gemini Compilation Fixer
Automatically fixes Rust compilation errors using the Gemini API.
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

class GeminiCompilationFixer:
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

    def call_gemini(self, prompt: str, max_tokens: int = 4000) -> Optional[str]:
        """Call Gemini API with built-in rate limiting (sleep)"""
        # Sleep to respect Gemini Free Tier 15 RPM limit (~4 seconds per request)
        time.sleep(4.5)
        
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={self.api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": "You are an expert Rust systems programmer specializing in Linux kernel FFI code. Fix compilation errors while maintaining C FFI compatibility. Always use #[repr(C)] for structs, extern \"C\" for functions, and proper unsafe blocks.\n\n" + prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": max_tokens
                }
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 429:
                print("Rate limited by Gemini API. Sleeping for 30s...")
                time.sleep(30)
                return self.call_gemini(prompt, max_tokens)
                
            response.raise_for_status()
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            if "429" in str(e):
                time.sleep(30)
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

    def apply_gemini_fix(self, module_name: str, source_code: str, errors: List[Dict]) -> Optional[str]:
        error_summary = "\n".join([f"- {err['type']}{err['code']}: {err['message']}" for err in errors[:5]])
        
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
6. Return ONLY the fixed Rust code. Do NOT output markdown formatting like ```rust. Just the raw code.
"""
        fixed_code = self.call_gemini(prompt)
        if not fixed_code: return None
        
        # Clean up markdown if AI included it
        if fixed_code.startswith("```rust"):
            fixed_code = fixed_code[7:]
        if fixed_code.startswith("```"):
            fixed_code = fixed_code[3:]
        if fixed_code.endswith("```"):
            fixed_code = fixed_code[:-3]
            
        return fixed_code.strip()

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

            print(f"Attempting Gemini fix (Iter {iteration+1})...")
            fixed_code = self.apply_gemini_fix(module_name, source_code, errors)
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
        
        print(f"Starting Overnight Gemini Fixer on {len(modules)} modules...")
        
        for module in modules:
            self.stats["attempted_fixes"] += 1
            res = self.fix_module(module)
            self.stats["modules"].append(res)
            
            # Checkpoint
            with open(self.results_dir / "gemini_checkpoint.json", "w") as f:
                json.dump(self.stats, f)

if __name__ == "__main__":
    API_KEY = os.environ.get("GEMINI_API_KEY", "")
    workspace = "/Volumes/MacCleanerStorage/xdev/xavux/rust-linux-mini-kernel"
    fixer = GeminiCompilationFixer(workspace, API_KEY)
    fixer.run_overnight_batch()
    print("Nightly batch complete!")
