#!/usr/bin/env python3
"""
Architect Fixer - Context-Aware, Spec-Driven Compilation Agent
Designed for 1M+ Token Context Windows (Gemini 1.5 Pro / Advanced Mistral)

This script implements a two-tier AI architecture:
1. The Architect: Reads master specs, analyzes global subsystem context, and creates a "Fix Blueprint".
2. The Coder: Reads the Blueprint and applies precise syntax edits to the modules.
"""

import os
import json
import subprocess
from pathlib import Path

WORKSPACE_DIR = Path(__file__).parent.parent.absolute()
SPECS_DIR = WORKSPACE_DIR / "specifications"
SCENARIO_B_SPECS = WORKSPACE_DIR / "scenario_b_specs"

class ArchitectAgent:
    def __init__(self, model_endpoint="gemini-1.5-pro"):
        self.model = model_endpoint
        self.global_context = self._load_master_specifications()

    def _load_master_specifications(self) -> str:
        """Loads the global vision from the master specifications."""
        print("[Architect] Loading Global Vision from Master Specifications...")
        context = ""
        
        # Load Kernel Types Spec
        kt_spec = SPECS_DIR / "KERNEL_TYPES_SPECIFICATION.md"
        if kt_spec.exists():
            context += f"\n--- KERNEL TYPES SPECIFICATION ---\n{kt_spec.read_text()}\n"
            
        # Load Scenario B Master Plan
        master_spec = SCENARIO_B_SPECS / "SCENARIO_B_MASTER_SPECIFICATION.md"
        if master_spec.exists():
            context += f"\n--- SCENARIO B MASTER PLAN ---\n{master_spec.read_text()}\n"
            
        return context

    def _call_llm(self, prompt: str) -> str:
        """Call Mistral Codestral API"""
        import time
        import requests
        time.sleep(1) # Rate limit protection
        
        api_key = "CQrIoijW25PNLmejFHbMmaRP5oJorLE7"
        
        try:
            url = "https://api.mistral.ai/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            payload = {
                "model": "codestral-latest",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert Rust software architect. Only provide valid output based on the instructions."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.1
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=90, verify=False)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"Error calling Mistral API: {e}")
            return "// LLM Call Failed"

    def analyze_module_and_design_blueprint(self, module_name: str, module_code: str, compiler_errors: str, dependencies: str) -> str:
        """
        The Architect does NOT write code. It evaluates the module against the Global Vision
        and outputs a high-level Design & Fix Blueprint for the Coder agent.
        """
        print(f"[Architect] Designing Blueprint for {module_name}...")
        
        prompt = f"""
        You are the Master Software Architect for a Linux C-to-Rust Kernel Translation.
        
        GLOBAL VISION:
        {self.global_context}
        
        MODULE: {module_name}
        COMPILER ERRORS:
        {compiler_errors}
        
        DEPENDENCY CONTEXT (kernel_types, etc):
        {dependencies}
        
        YOUR TASK:
        Do NOT output code. Output a detailed "Design & Fix Blueprint" for this module.
        Analyze why the module is failing to align with the global vision (e.g., local struct shadowing, FFI mismatches).
        Provide step-by-step logical instructions on how the code must be refactored to conform to the specifications.
        """
        
        return self._call_llm(prompt)

class CoderAgent:
    def __init__(self, model_endpoint="gemini-1.5-pro"):
        self.model = model_endpoint

    def _call_llm(self, prompt: str) -> str:
        """Call Mistral Codestral API for Coding"""
        import time
        import requests
        time.sleep(1) 
        
        api_key = "CQrIoijW25PNLmejFHbMmaRP5oJorLE7"
        
        try:
            url = "https://api.mistral.ai/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            payload = {
                "model": "codestral-latest",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert Rust systems programmer specializing in Linux FFI."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.1
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=90, verify=False)
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            import re
            match = re.search(r'```(?:rust)?\s*(.*?)(?:```|$)', content, re.DOTALL)
            if match and len(match.group(1)) > 50:
                content = match.group(1).strip()
            return content
        except Exception as e:
            print(f"Error calling Mistral API: {e}")
            return "// LLM Call Failed"

    def apply_blueprint(self, module_name: str, module_code: str, blueprint: str) -> str:
        """
        The Coder acts purely as a syntax executor, following the Architect's Blueprint.
        """
        print(f"[Coder] Executing Blueprint for {module_name}...")
        
        prompt = f"""
        You are an expert Rust systems programmer. 
        
        ARCHITECT'S BLUEPRINT:
        {blueprint}
        
        CURRENT MODULE CODE ({module_name}):
        {module_code}
        
        YOUR TASK:
        Return the fully corrected Rust code implementing the Architect's Blueprint exactly.
        Ensure strict #[repr(C)] FFI compliance.
        Return ONLY valid raw Rust code. Do not wrap in markdown ```rust ticks.
        """
        
        return self._call_llm(prompt)


def get_subsystem_modules(subsystem_prefix: str) -> list:
    """Groups files by subsystem (e.g., all 'nf_' netfilter modules together) for global context."""
    crates_dir = WORKSPACE_DIR / "crates"
    return [d for d in crates_dir.iterdir() if d.is_dir() and d.name.startswith(subsystem_prefix)]

def extract_errors(module_name: str) -> str:
    """Run cargo check on the specific module and extract the errors."""
    try:
        result = subprocess.run(
            ["cargo", "check", "-p", module_name],
            cwd=WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return ""
        
        # Keep only the first 2000 chars of errors to avoid blowing up context
        return result.stderr[:2000]
    except Exception as e:
        return f"Compilation failed: {e}"

def main():
    print("Initializing Context-Aware Compilation Pipeline...")
    
    architect = ArchitectAgent()
    coder = CoderAgent()
    
    # Example: Process the entire Netfilter subsystem as a single batch
    subsystems = ["nf_", "ip6_", "tcp"]
    
    for prefix in subsystems:
        modules = get_subsystem_modules(prefix)
        print(f"\nEvaluating Subsystem Batch: '{prefix}' ({len(modules)} modules found)")
        
        for mod_dir in modules:
            lib_rs = mod_dir / "src" / "lib.rs"
            if not lib_rs.exists():
                continue
                
            module_name = mod_dir.name
            
            # Step 1: Gather Errors (Real cargo check)
            print(f"Checking {module_name}...")
            errors = extract_errors(module_name)
            if not errors:
                print(f"✅ {module_name} compiles successfully! Skipping.")
                continue
                
            code = lib_rs.read_text()
            
            # Step 2: Gather Dependency Signatures (Simulated RAG for now)
            deps = "See kernel_types specification for available types."
            
            # Step 3: Architect generates the Design Blueprint
            blueprint = architect.analyze_module_and_design_blueprint(module_name, code, errors, deps)
            
            # Step 4: Coder executes the syntax fixes
            fixed_code = coder.apply_blueprint(module_name, code, blueprint)
            
            if fixed_code and not fixed_code.startswith("// LLM Call Failed"):
                # Step 5: Save fixed code
                lib_rs.write_text(fixed_code)
                print(f"[Success] Module {module_name} updated and ready for recompilation.")
                
                # Check if it compiles now
                new_errors = extract_errors(module_name)
                if not new_errors:
                    print(f"🎉 {module_name} fully fixed!")
                else:
                    print(f"⚠️ {module_name} still has errors after fix.")
            else:
                print(f"❌ Failed to generate fix for {module_name}.")

if __name__ == "__main__":
    main()
