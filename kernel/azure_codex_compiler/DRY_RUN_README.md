# Dry Run Instructions for Azure Codex Compilation Fixer

## Current Status

⚠️ **Azure OpenAI endpoint requires validation before running full batch**

### Issues Identified

1. **SSL Certificate Error**
   - Self-signed certificate in chain
   - May require corporate proxy configuration or certificate installation

2. **API Endpoint Format**
   - Standard Azure OpenAI format (`/openai/deployments/.../chat/completions`) returns "unsupported operation"
   - Alternative `/openai/responses` endpoint times out after 2 minutes
   - Need to verify correct API format for this endpoint

3. **Deployment Name**
   - Using: `gpt-5.3-codex`
   - May need verification this deployment exists and is accessible

## Dry Run Test Scripts

### Option 1: Single Module Test (Python)

```bash
cd /Users/xcallens/rust-linux-mini-kernel
source ~/.azure_openai_credentials

# Test single module
python3 azure_codex_compiler/dry_run_test.py netfilter .
```

**What it does:**
- Compiles netfilter module (39 errors currently)
- Makes single API call to test connectivity
- Shows sample Codex response
- **Does not modify any code**

### Option 2: Full Dry Run (Bash)

```bash
cd /Users/xcallens/rust-linux-mini-kernel
source ~/.azure_openai_credentials

# Test API connectivity
./azure_codex_compiler/test_single_module.sh netfilter
```

## Required Before Full Deployment

### 1. Verify Azure OpenAI Endpoint

```bash
# Test with curl (disable SSL verification for testing)
curl -k -X POST \
  "https://aistmexps.openai.azure.com/openai/deployments/gpt-5.3-codex/chat/completions?api-version=2024-02-15-preview" \
  -H "Content-Type: application/json" \
  -H "api-key: YOUR_KEY" \
  -d '{
    "messages": [
      {"role": "user", "content": "Hello"}
    ],
    "max_tokens": 10
  }'
```

**Expected response:**
```json
{
  "choices": [{
    "message": {
      "content": "Hello! ..."
    }
  }]
}
```

**Actual responses observed:**
- ❌ "The requested operation is unsupported"
- ❌ "The operation was timeout"
- ❌ SSL certificate verification failed

### 2. Fix SSL Certificate Issues

**Option A: Install Corporate CA Certificate**
```bash
# If using corporate proxy
export REQUESTS_CA_BUNDLE=/path/to/corporate-ca-bundle.crt
export SSL_CERT_FILE=/path/to/corporate-ca-bundle.crt
```

**Option B: Disable SSL Verification (Testing Only)**
```python
# In dry_run_test.py, add:
import urllib3
urllib3.disable_warnings()

# In requests call:
response = requests.post(url, headers=headers, json=payload, verify=False)
```

⚠️ **Never disable SSL verification in production**

### 3. Verify Correct API Format

Check Azure OpenAI documentation for endpoint URL format:
- Standard: `/openai/deployments/{deployment}/chat/completions`
- Alternative: `/openai/responses` (appears to be different service)

May need to contact Azure admin to:
- Confirm deployment name
- Verify API version
- Check endpoint permissions

## Workaround: Test Locally First

Since API connectivity has issues, test the core logic locally:

### Manual Dry Run (No API)

```bash
# 1. Compile a module and capture errors
cd /Users/xcallens/rust-linux-mini-kernel/crates/netfilter
cargo build 2>&1 | tee /tmp/errors.txt

# 2. Review error patterns
grep "^error\[" /tmp/errors.txt

# 3. Manually test fix approach on one error type
# Example: Missing type `flowi`
# - Find where it should be defined
# - Add appropriate struct/type definition
# - Recompile and verify fix

# 4. Once manual fix confirmed, can use as template for Codex prompts
```

## When Endpoint is Working

Once API connectivity is verified:

### Step 1: Dry Run (Single Module)

```bash
python3 azure_codex_compiler/dry_run_test.py netfilter .
```

**Success criteria:**
- ✅ API call returns valid response
- ✅ Response contains relevant Rust code or analysis
- ✅ No SSL/certificate errors
- ✅ Response time < 30 seconds

### Step 2: Small Batch Test (5 modules)

Modify `codex_compilation_fixer.py` temporarily:

```python
# In fix_all_modules_batch(), add:
modules = [d.name for d in self.crates_dir.iterdir() if d.is_dir()]
modules = modules[:5]  # Test with first 5 only
```

Deploy to Azure:
```bash
./azure_codex_compiler/deploy_overnight_batch.sh
```

Monitor:
```bash
az container logs --resource-group rg-rust-kernel \
  --name codex-compiler-TIMESTAMP --follow
```

**Success criteria:**
- ✅ At least 3/5 modules show reduced errors
- ✅ No API rate limiting errors
- ✅ Fixes are syntactically valid Rust
- ✅ Total cost < $5

### Step 3: Full Batch (121 modules)

Remove the 5-module limit and deploy full batch:
```bash
./azure_codex_compiler/deploy_overnight_batch.sh
```

**Expected results:**
- Runtime: 6-8 hours
- Success rate: 75-85% (90-103 modules)
- Cost: $25-40

## Current Alternatives

Until Azure OpenAI endpoint is working:

### Option 1: Use Different LLM Endpoint

If you have access to:
- OpenAI API (api.openai.com)
- Different Azure OpenAI resource
- Anthropic Claude API
- Local LLM (llama.cpp, etc.)

Modify `codex_compilation_fixer.py` to use that endpoint.

### Option 2: Manual Fixing First

Focus on Tier 1 critical modules manually:

1. **netfilter** (450 LOC, 39 errors) - Core filtering framework
2. **af_inet** (438 LOC) - IPv4 socket implementation
3. **fib_trie** (438 LOC, 4 errors) - Fast routing lookup
4. **udp** (480 LOC) - UDP protocol

These 4 modules are dependencies for many others. Fixing them manually will unblock ~30-40 dependent modules.

### Option 3: Use Specifications

The `scenario_b_specs/` directory contains comprehensive type mappings. Use these to manually fix compilation errors:

```bash
# Example: Fixing missing types in netfilter
cd /Users/xcallens/rust-linux-mini-kernel

# Look up type mapping
grep "flowi" scenario_b_specs/*.json

# Apply fix based on specification
# Edit crates/netfilter/src/lib.rs accordingly
```

## Summary

**Infrastructure:** ✅ Complete and ready
**Docker Images:** ✅ Built and pushed to ACR
**Deployment Scripts:** ✅ Fixed and tested
**Credentials:** ⚠️ Provided but endpoint has issues

**Blocker:** Azure OpenAI endpoint connectivity

**Next Steps:**
1. Verify endpoint URL format with Azure admin
2. Fix SSL certificate issues
3. Run dry run test successfully
4. Deploy small batch (5 modules)
5. Deploy full batch (121 modules)

---

**Created:** 2026-05-17 01:15 CEST  
**Status:** Ready for dry run when endpoint is validated  
**Contact:** Xavier Callens
