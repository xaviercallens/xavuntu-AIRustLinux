#!/usr/bin/env python3
"""
Azure Codex Compilation Fixer
Automatically fixes Rust compilation errors using Azure OpenAI Codex endpoint
Runs in batch mode overnight with rate limiting and multiple endpoints
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse

class AzureCodexCompilationFixer:
    def __init__(self, workspace_root: str, endpoints: List[Dict], max_workers: int = 3):
        self.workspace_root = Path(workspace_root)
        self.crates_dir = self.workspace_root / "crates"
        self.results_dir = self.workspace_root / "compilation_fixes"
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Azure OpenAI Codex endpoints
        self.endpoints = endpoints
        self.current_endpoint_idx = 0
        self.max_workers = min(max_workers, len(endpoints))

        # Rate limiting (requests per minute per endpoint)
        self.rpm_limit = 60
        self.last_request_times = {i: [] for i in range(len(endpoints))}

        # Statistics
        self.stats = {
            "total_modules": 0,
            "attempted_fixes": 0,
            "successful_fixes": 0,
            "failed_fixes": 0,
            "compilation_errors_fixed": 0,
            "start_time": datetime.now().isoformat(),
            "modules": []
        }

    def get_next_endpoint(self) -> Tuple[int, Dict]:
        """Get next available endpoint with rate limiting"""
        for _ in range(len(self.endpoints)):
            idx = self.current_endpoint_idx
            self.current_endpoint_idx = (self.current_endpoint_idx + 1) % len(self.endpoints)

            # Clean old request times (older than 1 minute)
            current_time = time.time()
            self.last_request_times[idx] = [
                t for t in self.last_request_times[idx]
                if current_time - t < 60
            ]

            # Check if we can make a request
            if len(self.last_request_times[idx]) < self.rpm_limit:
                self.last_request_times[idx].append(current_time)
                return idx, self.endpoints[idx]

        # If all endpoints are rate limited, wait and retry
        time.sleep(1)
        return self.get_next_endpoint()

    def call_codex(self, prompt: str, max_tokens: int = 2000) -> Optional[str]:
        """Call Azure OpenAI Codex endpoint with rate limiting"""
        idx, endpoint = self.get_next_endpoint()

        try:
            headers = {
                "Content-Type": "application/json",
                "api-key": endpoint["api_key"]
            }

            # Prepend system instructions to the prompt for Responses API
            full_prompt = f"""You are an expert Rust systems programmer specializing in Linux kernel FFI code. Fix compilation errors while maintaining C FFI compatibility. Always use #[repr(C)] for structs, extern "C" for functions, and proper unsafe blocks.

{prompt}"""

            payload = {
                "model": endpoint["deployment"],
                "input": full_prompt
                # Note: Responses API doesn't support max_tokens, temperature, top_p
            }

            response = requests.post(
                f"{endpoint['endpoint']}/openai/responses?api-version=2025-04-01-preview",
                headers=headers,
                json=payload,
                timeout=120,
                verify=False  # Disable SSL verification for corporate proxy
            )

            response.raise_for_status()
            result = response.json()

            # Extract text from Responses API format
            if result.get("output") and len(result["output"]) > 0:
                content = result["output"][0].get("content", [])
                if content and len(content) > 0:
                    return content[0].get("text", "")

            print(f"❌ Unexpected response format from endpoint {idx}")
            return None

        except Exception as e:
            print(f"Error calling Codex endpoint {idx}: {e}")
            return None

    def compile_module(self, module_name: str) -> Tuple[bool, str]:
        """Compile a single module and return success status and error output"""
        try:
            result = subprocess.run(
                ["cargo", "build", "--package", module_name, "--release"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                return True, ""
            else:
                return False, result.stderr

        except subprocess.TimeoutExpired:
            return False, "Compilation timeout (120s)"
        except Exception as e:
            return False, f"Compilation error: {str(e)}"

    def extract_compilation_errors(self, error_output: str) -> List[Dict]:
        """Parse cargo error output into structured errors"""
        errors = []
        current_error = None

        for line in error_output.split('\n'):
            # Match error lines
            error_match = re.match(r'error(\[E\d+\])?: (.+)', line)
            if error_match:
                if current_error:
                    errors.append(current_error)
                current_error = {
                    "type": "error",
                    "code": error_match.group(1) if error_match.group(1) else "E0000",
                    "message": error_match.group(2),
                    "location": "",
                    "context": []
                }
                continue

            # Match location lines
            location_match = re.match(r'\s+-->\s+(.+):(\d+):(\d+)', line)
            if location_match and current_error:
                current_error["location"] = {
                    "file": location_match.group(1),
                    "line": int(location_match.group(2)),
                    "column": int(location_match.group(3))
                }
                continue

            # Add context lines
            if current_error and line.strip():
                current_error["context"].append(line)

        if current_error:
            errors.append(current_error)

        return errors

    def read_module_source(self, module_name: str) -> str:
        """Read the source code of a module"""
        lib_file = self.crates_dir / module_name / "src" / "lib.rs"
        try:
            return lib_file.read_text()
        except Exception as e:
            print(f"Error reading {module_name}: {e}")
            return ""

    def write_module_source(self, module_name: str, content: str) -> bool:
        """Write fixed source code back to module"""
        lib_file = self.crates_dir / module_name / "src" / "lib.rs"
        try:
            lib_file.write_text(content)
            return True
        except Exception as e:
            print(f"Error writing {module_name}: {e}")
            return False

    def create_fix_prompt(self, module_name: str, source_code: str, errors: List[Dict]) -> str:
        """Create a prompt for Codex to fix compilation errors"""
        error_summary = "\n".join([
            f"- {err['type']}{err['code']}: {err['message']}"
            for err in errors[:5]  # Limit to first 5 errors
        ])

        # Extract relevant code section (around first error)
        code_section = source_code
        if errors and errors[0].get("location"):
            line_num = errors[0]["location"]["line"]
            lines = source_code.split('\n')
            start = max(0, line_num - 20)
            end = min(len(lines), line_num + 20)
            code_section = '\n'.join(lines[start:end])

        prompt = f"""Fix the following Rust compilation errors in the Linux kernel FFI module '{module_name}'.

Compilation errors:
{error_summary}

Relevant code section:
```rust
{code_section}
```

Requirements:
1. Fix ALL compilation errors
2. Maintain C FFI compatibility (use #[repr(C)], extern "C", #[no_mangle])
3. Keep unsafe blocks where needed
4. Don't add unnecessary features
5. Preserve the original structure and logic

Provide ONLY the fixed code section as a complete, valid Rust code block."""

        return prompt

    def apply_codex_fix(self, module_name: str, source_code: str, errors: List[Dict]) -> Optional[str]:
        """Use Codex to fix compilation errors"""
        prompt = self.create_fix_prompt(module_name, source_code, errors)
        fixed_code = self.call_codex(prompt)

        if not fixed_code:
            return None

        # Extract code from markdown code blocks if present
        code_match = re.search(r'```rust\n(.*?)\n```', fixed_code, re.DOTALL)
        if code_match:
            fixed_code = code_match.group(1)

        return fixed_code

    def fix_module(self, module_name: str) -> Dict:
        """Attempt to fix a single module's compilation errors"""
        print(f"\n{'='*70}")
        print(f"Processing: {module_name}")
        print(f"{'='*70}")

        result = {
            "module": module_name,
            "initial_errors": 0,
            "fix_attempts": 0,
            "final_errors": 0,
            "success": False,
            "iterations": []
        }

        # Initial compilation check
        success, error_output = self.compile_module(module_name)
        if success:
            print(f"✅ {module_name} already compiles successfully")
            result["success"] = True
            return result

        errors = self.extract_compilation_errors(error_output)
        result["initial_errors"] = len(errors)
        print(f"Found {len(errors)} compilation errors")

        # Try up to 3 fix iterations
        max_iterations = 3
        for iteration in range(max_iterations):
            print(f"\nIteration {iteration + 1}/{max_iterations}")

            # Read current source
            source_code = self.read_module_source(module_name)
            if not source_code:
                break

            # Use Codex to fix errors
            print(f"Calling Azure Codex to fix errors...")
            fixed_code = self.apply_codex_fix(module_name, source_code, errors)

            if not fixed_code:
                print(f"❌ Codex failed to generate fix")
                break

            # Write fixed code
            if not self.write_module_source(module_name, fixed_code):
                print(f"❌ Failed to write fixed code")
                break

            result["fix_attempts"] += 1

            # Test compilation
            print(f"Testing fixed code...")
            success, error_output = self.compile_module(module_name)

            if success:
                print(f"✅ {module_name} now compiles successfully!")
                result["success"] = True
                result["final_errors"] = 0
                self.stats["successful_fixes"] += 1
                self.stats["compilation_errors_fixed"] += result["initial_errors"]
                break
            else:
                new_errors = self.extract_compilation_errors(error_output)
                result["final_errors"] = len(new_errors)
                print(f"Still has {len(new_errors)} errors")

                # Check if we made progress
                if len(new_errors) >= len(errors):
                    print(f"No progress made, stopping iterations")
                    break

                errors = new_errors

            result["iterations"].append({
                "iteration": iteration + 1,
                "errors_before": len(errors),
                "errors_after": result["final_errors"],
                "fixed": success
            })

        if not result["success"]:
            self.stats["failed_fixes"] += 1
            print(f"❌ {module_name} still has {result['final_errors']} errors after {result['fix_attempts']} attempts")

        return result

    def fix_all_modules_batch(self) -> None:
        """Fix all modules in parallel using ThreadPoolExecutor"""
        # Get all module names
        modules = [d.name for d in self.crates_dir.iterdir() if d.is_dir()]
        self.stats["total_modules"] = len(modules)

        print(f"\n{'='*70}")
        print(f"BATCH COMPILATION FIX - {len(modules)} modules")
        print(f"Endpoints: {self.max_workers}")
        print(f"Rate limit: {self.rpm_limit} RPM per endpoint")
        print(f"{'='*70}\n")

        # Process modules in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.fix_module, module): module for module in modules}

            for future in as_completed(futures):
                module = futures[future]
                try:
                    result = future.result()
                    self.stats["modules"].append(result)
                    self.stats["attempted_fixes"] += 1

                    # Save progress checkpoint
                    self.save_checkpoint()

                except Exception as e:
                    print(f"Error processing {module}: {e}")
                    self.stats["modules"].append({
                        "module": module,
                        "success": False,
                        "error": str(e)
                    })

    def save_checkpoint(self) -> None:
        """Save current progress to checkpoint file"""
        checkpoint_file = self.results_dir / f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        self.stats["end_time"] = datetime.now().isoformat()
        self.stats["success_rate"] = (
            self.stats["successful_fixes"] / self.stats["attempted_fixes"] * 100
            if self.stats["attempted_fixes"] > 0 else 0
        )

        with open(checkpoint_file, 'w') as f:
            json.dump(self.stats, f, indent=2)

    def generate_final_report(self) -> str:
        """Generate comprehensive final report"""
        self.stats["end_time"] = datetime.now().isoformat()

        report = f"""
╔════════════════════════════════════════════════════════════════╗
║        AZURE CODEX COMPILATION FIX - FINAL REPORT             ║
╚════════════════════════════════════════════════════════════════╝

Execution Summary:
------------------
Start Time: {self.stats['start_time']}
End Time: {self.stats['end_time']}
Total Modules: {self.stats['total_modules']}
Attempted Fixes: {self.stats['attempted_fixes']}

Results:
--------
✅ Successful Fixes: {self.stats['successful_fixes']}
❌ Failed Fixes: {self.stats['failed_fixes']}
📊 Success Rate: {self.stats['successful_fixes'] / self.stats['attempted_fixes'] * 100:.1f}%
🐛 Total Errors Fixed: {self.stats['compilation_errors_fixed']}

Top Fixed Modules:
------------------
"""

        # Sort by initial errors (most complex fixes first)
        sorted_modules = sorted(
            [m for m in self.stats["modules"] if m.get("success")],
            key=lambda x: x.get("initial_errors", 0),
            reverse=True
        )[:10]

        for i, module in enumerate(sorted_modules, 1):
            report += f"{i}. {module['module']}: Fixed {module['initial_errors']} errors in {module['fix_attempts']} iterations\n"

        report += f"\n\nStill Failing Modules ({self.stats['failed_fixes']}):\n"
        report += "------------------\n"

        failed_modules = [m for m in self.stats["modules"] if not m.get("success")]
        for module in failed_modules[:20]:
            report += f"- {module['module']}: {module.get('final_errors', 'unknown')} errors remaining\n"

        report += f"\n\nDetailed results saved to: {self.results_dir}/\n"

        return report


def main():
    parser = argparse.ArgumentParser(description="Azure Codex Compilation Fixer")
    parser.add_argument("--workspace", default=os.environ.get("WORKSPACE_ROOT", "/Users/xcallens/rust-linux-mini-kernel"),
                       help="Path to Rust workspace")
    parser.add_argument("--workers", type=int, default=3,
                       help="Number of parallel workers (endpoints)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Test without actually fixing code")

    args = parser.parse_args()

    # Azure OpenAI endpoints configuration
    endpoints = [
        {
            "name": "endpoint-1",
            "endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT_1", ""),
            "api_key": os.environ.get("AZURE_OPENAI_KEY_1", ""),
            "deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT_1", "gpt-4")
        },
        {
            "name": "endpoint-2",
            "endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT_2", ""),
            "api_key": os.environ.get("AZURE_OPENAI_KEY_2", ""),
            "deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT_2", "gpt-4")
        },
        {
            "name": "endpoint-3",
            "endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT_3", ""),
            "api_key": os.environ.get("AZURE_OPENAI_KEY_3", ""),
            "deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT_3", "gpt-4")
        }
    ]

    # Validate endpoints
    endpoints = [ep for ep in endpoints if ep["endpoint"] and ep["api_key"]]
    if not endpoints:
        print("❌ No valid Azure OpenAI endpoints configured")
        print("Set environment variables: AZURE_OPENAI_ENDPOINT_N and AZURE_OPENAI_KEY_N")
        return

    print(f"Using {len(endpoints)} Azure OpenAI endpoint(s)")

    # Initialize fixer
    fixer = AzureCodexCompilationFixer(args.workspace, endpoints, args.workers)

    # Run batch compilation fixes
    fixer.fix_all_modules_batch()

    # Generate and save final report
    report = fixer.generate_final_report()
    print(report)

    report_file = fixer.results_dir / f"final_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(report_file, 'w') as f:
        f.write(report)

    print(f"\n✅ Final report saved to: {report_file}")


if __name__ == "__main__":
    main()
