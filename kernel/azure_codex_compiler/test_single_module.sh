#!/bin/bash
#
# Test Azure Codex compilation fixer on a single module
# Usage: ./test_single_module.sh [module_name]
#

set -euo pipefail

MODULE="${1:-netfilter}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     AZURE CODEX COMPILATION FIXER - SINGLE MODULE TEST        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check credentials
if [ -z "${AZURE_OPENAI_ENDPOINT_1:-}" ] || [ -z "${AZURE_OPENAI_KEY_1:-}" ]; then
    echo "❌ Azure OpenAI credentials not set"
    echo ""
    echo "Load credentials with:"
    echo "  source ~/.azure_openai_credentials"
    exit 1
fi

echo "✅ Azure OpenAI credentials configured"
echo "   Endpoint: $AZURE_OPENAI_ENDPOINT_1"
echo "   Deployment: ${AZURE_OPENAI_DEPLOYMENT_1:-gpt-4}"
echo ""

# Check module exists
if [ ! -d "$REPO_ROOT/crates/$MODULE" ]; then
    echo "❌ Module not found: $MODULE"
    echo ""
    echo "Available modules:"
    ls -1 "$REPO_ROOT/crates/" | head -10
    exit 1
fi

echo "✅ Testing module: $MODULE"
echo ""

# Compile to get initial errors
echo "📊 Initial compilation status..."
cd "$REPO_ROOT/crates/$MODULE"
INITIAL_ERRORS=$(cargo build 2>&1 | grep -c "^error" || echo "0")
echo "   Found $INITIAL_ERRORS compilation errors"
echo ""

if [ "$INITIAL_ERRORS" = "0" ]; then
    echo "✅ Module already compiles successfully!"
    exit 0
fi

# Show first few errors
echo "📋 Sample errors:"
cargo build 2>&1 | grep "^error" | head -5
echo ""

# Create test Python script that processes single module
cat > /tmp/test_single_module.py << 'PYTHON_EOF'
#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import re
from pathlib import Path
import requests

def compile_module(module_path):
    """Compile module and capture errors"""
    result = subprocess.run(
        ["cargo", "build"],
        cwd=module_path,
        capture_output=True,
        text=True
    )

    errors = []
    for line in result.stderr.split('\n'):
        if line.startswith('error'):
            errors.append(line)

    return len(errors), result.stderr

def call_codex_api(endpoint, api_key, deployment, prompt):
    """Call Azure OpenAI API"""
    url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version=2024-02-15-preview"

    headers = {
        "Content-Type": "application/json",
        "api-key": api_key
    }

    payload = {
        "messages": [
            {"role": "system", "content": "You are an expert Rust developer fixing compilation errors."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2000,
        "temperature": 0.3
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()['choices'][0]['message']['content']

def main():
    module_name = sys.argv[1] if len(sys.argv) > 1 else "netfilter"
    workspace_root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()

    module_path = workspace_root / "crates" / module_name

    print(f"🔍 Testing module: {module_name}")
    print(f"   Path: {module_path}")
    print()

    # Get initial errors
    error_count, stderr = compile_module(module_path)
    print(f"📊 Initial errors: {error_count}")

    if error_count == 0:
        print("✅ Module already compiles!")
        return

    # Show errors
    print("\n📋 Compilation errors:")
    print(stderr[:1000])  # First 1000 chars
    print("\n" + "="*70)

    # Test API call
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT_1")
    api_key = os.environ.get("AZURE_OPENAI_KEY_1")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_1", "gpt-4")

    print(f"\n🤖 Testing Azure OpenAI API...")
    print(f"   Endpoint: {endpoint}")
    print(f"   Deployment: {deployment}")

    try:
        prompt = f"""Fix these Rust compilation errors:

```
{stderr[:800]}
```

Provide only the fixed code, no explanations."""

        response = call_codex_api(endpoint, api_key, deployment, prompt)
        print(f"\n✅ API call successful!")
        print(f"\n📝 Response preview:")
        print(response[:300])
        print("...")

    except Exception as e:
        print(f"\n❌ API call failed: {e}")
        return 1

if __name__ == "__main__":
    main()
PYTHON_EOF

chmod +x /tmp/test_single_module.py

# Run test
echo "🚀 Running API test..."
python3 /tmp/test_single_module.py "$MODULE" "$REPO_ROOT"

echo ""
echo "✅ Test complete!"
echo ""
echo "To run full batch:"
echo "  cd $SCRIPT_DIR"
echo "  ./deploy_overnight_batch.sh"
