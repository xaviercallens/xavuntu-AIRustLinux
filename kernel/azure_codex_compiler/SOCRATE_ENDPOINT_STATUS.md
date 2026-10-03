# Socrate Endpoint Status & Configuration

## Current Status: All Endpoints Stopped ⚠️

### Tested Endpoints (May 17, 2026 01:20 CEST)

| Endpoint | Model | Status | Notes |
|----------|-------|--------|-------|
| socrateassist-orchestrator | Router | ✅ Running | Healthy but backends stopped |
| socrateassist-122b-2xa100-lora | 122B (QUALITY) | ❌ Stopped | Error 404 |
| socrateassist-32b-a100-lora | 32B (BALANCED) | ❌ Stopped | Error 404 |
| socrateassist-qwen3-32b-a100 | Qwen3 32B | ❌ Stopped | No response |
| socrateassist-qwen36-a100-turbo | Qwen3.6 Turbo | ❌ Stopped | No response |
| socrateassist-dsr1-32b-a100 | DSR1 32B | ❌ Stopped | No response |
| socrateassist-7b-t4-lora | 7B (FAST) | ❌ Stopped | No response |

### Recommendation for Rust Compilation Fixing

**Best Model:** socrateassist-122b-2xa100-lora (122B QUALITY)
- **Reason:** Largest model, best for complex code analysis and error fixing
- **Hardware:** 2x A100 GPUs
- **Expected latency:** ~3-5 seconds per request
- **Quality:** Highest accuracy for type inference and error resolution

**Alternative:** socrateassist-32b-a100-lora (32B BALANCED)
- **Reason:** Good balance of speed and quality  
- **Hardware:** 1x A100 GPU
- **Expected latency:** ~1-2 seconds per request
- **Quality:** Very good for most compilation fixes

## How to Start Socrate Endpoints

### Option 1: Azure Portal

1. Navigate to https://portal.azure.com/
2. Go to Resource Group: `politeplant-fa0c5658`
3. Find Container App: `socrateassist-122b-2xa100-lora`
4. Click "Start" or scale replicas from 0 to 1+

### Option 2: Azure CLI

```bash
# Start 122B model (QUALITY)
az containerapp update \
  --name socrateassist-122b-2xa100-lora \
  --resource-group politeplant-fa0c5658 \
  --min-replicas 1 \
  --max-replicas 2

# Or start 32B model (BALANCED)  
az containerapp update \
  --name socrateassist-32b-a100-lora \
  --resource-group politeplant-fa0c5658 \
  --min-replicas 1 \
  --max-replicas 3
```

### Cost Estimates

| Model | GPU | Hourly Cost | Daily (24h) | Per Request |
|-------|-----|-------------|-------------|-------------|
| 122B 2xA100 | 2x A100 80GB | ~$6-8/hr | ~$144-192 | ~$0.005-0.008 |
| 32B A100 | 1x A100 80GB | ~$3-4/hr | ~$72-96 | ~$0.002-0.003 |
| 7B T4 | 1x T4 16GB | ~$0.50/hr | ~$12 | ~$0.0002 |

**For 121 modules × 3 iterations:**
- 122B: ~363 requests × $0.006 = **~$2.18** (inference only)
- 32B: ~363 requests × $0.0025 = **~$0.91** (inference only)
- Plus compute time (6-8 hours): **$36-64** (122B) or **$18-32** (32B)

**Total estimated cost:** $40-65 for 122B, $20-35 for 32B

## Configuration for Codex Fixer

Once endpoint is running, update `~/.azure_openai_credentials`:

```bash
# For 122B QUALITY model
export SOCRATE_ENDPOINT="https://socrateassist-122b-2xa100-lora.politeplant-fa0c5658.swedencentral.azurecontainerapps.io/v1/chat/completions"
export SOCRATE_MODEL="socrateassist-122b"

# For 32B BALANCED model
export SOCRATE_ENDPOINT="https://socrateassist-32b-a100-lora.politeplant-fa0c5658.swedencentral.azurecontainerapps.io/v1/chat/completions"
export SOCRATE_MODEL="socrateassist-si-32b"

# No API key required for internal Socrate endpoints
```

## Test Endpoint Connectivity

### Quick Test (curl)

```bash
# Test 122B endpoint
curl -k -X POST "$SOCRATE_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "socrateassist-122b",
    "messages": [
      {"role": "system", "content": "You are a Rust expert."},
      {"role": "user", "content": "Fix: cannot find type `flowi`"}
    ],
    "max_tokens": 100,
    "temperature": 0.2
  }'
```

**Expected response:**
```json
{
  "choices": [{
    "message": {
      "content": "The type `flowi` is a Linux kernel networking structure..."
    }
  }]
}
```

### Full Dry Run Test

```bash
cd /Users/xcallens/rust-linux-mini-kernel
source ~/.azure_openai_credentials

# Update dry_run_test.py to use Socrate endpoint
python3 azure_codex_compiler/dry_run_test.py netfilter .
```

## Integration Steps

### 1. Update codex_compilation_fixer.py

Replace Azure OpenAI API call with Socrate endpoint:

```python
def call_codex_api(self, endpoint, api_key, deployment, prompt):
    """Call Socrate LLM endpoint"""
    url = endpoint  # Full URL including /v1/chat/completions
    
    headers = {
        "Content-Type": "application/json"
        # No api-key header needed for Socrate
    }
    
    payload = {
        "model": deployment,
        "messages": [
            {
                "role": "system",
                "content": "You are an expert Rust systems programmer fixing compilation errors."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 1500,
        "temperature": 0.2
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=60, verify=False)
    response.raise_for_status()
    
    return response.json()['choices'][0]['message']['content']
```

### 2. Update Environment Variables

```bash
# In ~/.azure_openai_credentials
export AZURE_OPENAI_ENDPOINT_1="https://socrateassist-122b-2xa100-lora.politeplant-fa0c5658.swedencentral.azurecontainerapps.io/v1/chat/completions"
export AZURE_OPENAI_KEY_1=""  # Empty for Socrate
export AZURE_OPENAI_DEPLOYMENT_1="socrateassist-122b"
export AZURE_OPENAI_API_VERSION=""  # Not used for Socrate
```

### 3. Update Deployment Script

No changes needed to `deploy_overnight_batch.sh` - it already passes environment variables.

## Orchestrator Alternative

If you want to use the orchestrator (auto model selection):

```bash
# Orchestrator endpoint
export SOCRATE_ORCHESTRATOR="https://socrateassist-orchestrator.politeplant-fa0c5658.swedencentral.azurecontainerapps.io/v1/completions/analyze"

# Use with custom request format
curl -k -X POST "$SOCRATE_ORCHESTRATOR" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "<rust_code_with_errors>",
    "language": "rust",
    "operation": "fix_compilation",
    "model": "auto"
  }'
```

**Pros:**
- Auto model selection (chooses best model for task)
- Unified interface for all operations
- Built-in retry logic

**Cons:**
- Requires all backend models to be running
- Different API format (not OpenAI-compatible)
- Additional latency from routing layer

## Summary

**Current blocker:** All Socrate LLM endpoints are stopped (scale-to-zero)

**Solution:**
1. Start socrateassist-122b-2xa100-lora (best quality) OR socrateassist-32b-a100-lora (good balance)
2. Update endpoint URL in credentials file
3. Test with dry_run_test.py
4. Run full batch with deploy_overnight_batch.sh

**Estimated time to fix:** 5-10 minutes to start endpoint + verify

**Expected results:**
- 122B model: 80-90% compilation success rate
- 32B model: 75-85% compilation success rate
- Total runtime: 6-8 hours
- Total cost: $40-65 (122B) or $20-35 (32B)

---

**Status:** Ready to deploy once endpoint is started  
**Preferred endpoint:** socrateassist-122b-2xa100-lora (QUALITY)  
**Alternative:** socrateassist-32b-a100-lora (BALANCED)  
**Documentation:** Complete and ready  
**Next step:** Start endpoint via Azure Portal or CLI

