#!/usr/bin/env python3
"""
Dry run test for Azure Codex compilation fixer
Tests API connectivity and shows what would be fixed
"""

import os
import sys
import subprocess
from pathlib import Path
import requests
import json

def compile_module(module_path):
    """Compile module and capture errors"""
    result = subprocess.run(
        ["cargo", "build"],
        cwd=module_path,
        capture_output=True,
        text=True
    )

    errors = [line for line in result.stderr.split('\n') if line.startswith('error[')]
    return len(errors), result.stderr

def call_azure_openai(endpoint, api_key, deployment, prompt):
    """Call Azure OpenAI Responses API"""
    # Remove trailing slash and construct URL
    base_url = endpoint.rstrip('/')
    url = f"{base_url}/openai/responses?api-version=2025-04-01-preview"

    headers = {
        "Content-Type": "application/json",
        "api-key": api_key
    }

    # Combine system message with user prompt for Responses API
    full_input = f"""You are an expert Rust systems programmer. Fix compilation errors with minimal changes.

{prompt}"""

    payload = {
        "model": deployment,
        "input": full_input
    }

    print(f"   URL: {url[:80]}...")
    response = requests.post(url, headers=headers, json=payload, timeout=60, verify=False)
    response.raise_for_status()

    result = response.json()
    # Extract text from Responses API format
    if result.get("output") and len(result["output"]) > 0:
        content = result["output"][0].get("content", [])
        if content and len(content) > 0:
            return content[0].get("text", "")

    return "No response content"

def main():
    module_name = sys.argv[1] if len(sys.argv) > 1 else "netfilter"
    workspace_root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()

    print("╔════════════════════════════════════════════════════════════════╗")
    print("║     AZURE CODEX DRY RUN - SINGLE MODULE TEST                  ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print()

    # Get credentials
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT_1")
    api_key = os.environ.get("AZURE_OPENAI_KEY_1")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_1", "gpt-4")

    if not endpoint or not api_key:
        print("❌ Missing credentials:")
        print("   Set AZURE_OPENAI_ENDPOINT_1 and AZURE_OPENAI_KEY_1")
        print()
        print("   source ~/.azure_openai_credentials")
        return 1

    print(f"✅ Credentials loaded")
    print(f"   Endpoint: {endpoint[:50]}...")
    print(f"   Deployment: {deployment}")
    print()

    # Check module
    module_path = workspace_root / "crates" / module_name
    if not module_path.exists():
        print(f"❌ Module not found: {module_path}")
        return 1

    print(f"📦 Testing module: {module_name}")
    print(f"   Path: {module_path}")
    print()

    # Compile
    print("🔨 Compiling module...")
    error_count, stderr = compile_module(module_path)

    if error_count == 0:
        print("✅ Module already compiles successfully!")
        return 0

    print(f"   Found {error_count} errors")
    print()

    # Show sample errors
    print("📋 Sample compilation errors:")
    error_lines = [l for l in stderr.split('\n') if l.startswith('error[')][:5]
    for line in error_lines:
        print(f"   {line}")
    print()

    # Test API call
    print("🤖 Testing Azure OpenAI API...")

    # Extract first error for testing
    first_error = stderr[:800]
    prompt = f"""Analyze these Rust compilation errors and suggest fixes:

```
{first_error}
```

Provide a brief analysis of the error types and recommended fix approach."""

    try:
        response = call_azure_openai(endpoint, api_key, deployment, prompt)

        print()
        print("✅ API call successful!")
        print()
        print("📝 Codex response:")
        print("─" * 70)
        print(response[:500])
        if len(response) > 500:
            print("...")
            print(f"   (truncated, full response is {len(response)} chars)")
        print("─" * 70)
        print()

        print("✅ Dry run successful!")
        print()
        print("Next steps:")
        print("  1. Review the API response quality")
        print("  2. Run full batch: ./deploy_overnight_batch.sh")
        print(f"  3. Expected: Fix {error_count} errors in {module_name}")
        print()

        return 0

    except requests.exceptions.RequestException as e:
        print()
        print(f"❌ API call failed: {e}")
        print()
        if hasattr(e, 'response') and e.response is not None:
            print("Response details:")
            print(f"   Status: {e.response.status_code}")
            print(f"   Body: {e.response.text[:500]}")
        return 1

    except Exception as e:
        print()
        print(f"❌ Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
