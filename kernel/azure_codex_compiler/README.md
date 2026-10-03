# Azure Codex Compilation Fixer

Automated overnight batch compilation error fixing using Azure OpenAI Codex.

## Quick Start

### 1. Set Up Azure OpenAI Endpoints

```bash
# Required: At least 1 endpoint
export AZURE_OPENAI_ENDPOINT_1="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_KEY_1="your-api-key"

# Optional: Additional endpoints for 3x throughput
export AZURE_OPENAI_ENDPOINT_2="https://your-resource-2.openai.azure.com/"
export AZURE_OPENAI_KEY_2="your-api-key-2"

export AZURE_OPENAI_ENDPOINT_3="https://your-resource-3.openai.azure.com/"
export AZURE_OPENAI_KEY_3="your-api-key-3"
```

### 2. Deploy Overnight Batch

```bash
cd /Users/xcallens/rust-linux-mini-kernel/azure_codex_compiler
chmod +x deploy_overnight_batch.sh codex_compilation_fixer.py
./deploy_overnight_batch.sh
```

### 3. Monitor Progress

```bash
# Get container name from deployment output
CONTAINER_NAME="codex-compiler-YYYYMMDD-HHMMSS"

# Follow logs
az container logs \
    --resource-group rg-rust-kernel \
    --name "$CONTAINER_NAME" \
    --follow

# Check status
az container show \
    --resource-group rg-rust-kernel \
    --name "$CONTAINER_NAME" \
    --query instanceView.state
```

### 4. Review Results (Morning)

Results saved to `/workspace/compilation_fixes/`:
- `checkpoint_*.json` - Progress checkpoints
- `final_report_*.md` - Comprehensive results
- Fixed module source code in `crates/*/src/lib.rs`

## Features

- **Parallel Processing:** 3 endpoints × 60 req/min = 180 req/min
- **Rate Limiting:** Automatic per-endpoint rate control
- **Progress Checkpoints:** Save state every module
- **Iterative Fixing:** Up to 3 attempts per module
- **Smart Prompting:** Context-aware error fixing
- **Comprehensive Reporting:** Detailed success/failure analysis

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Azure Container Instance (4 CPU, 16GB RAM)     │
│                                                  │
│  ┌────────────────────────────────────────┐    │
│  │  Codex Compilation Fixer               │    │
│  │  - Python orchestrator                 │    │
│  │  - ThreadPoolExecutor (3 workers)      │    │
│  │  - Rate limiting per endpoint          │    │
│  └────────────────────────────────────────┘    │
│                    │                             │
│         ┌──────────┼──────────┐                 │
│         ▼          ▼          ▼                 │
│    Endpoint 1  Endpoint 2  Endpoint 3           │
│    60 req/min  60 req/min  60 req/min           │
│         │          │          │                 │
│         └──────────┴──────────┘                 │
│                    │                             │
│                    ▼                             │
│         ┌─────────────────────┐                 │
│         │  Fix → Compile      │                 │
│         │  Check → Iterate    │                 │
│         │  Save → Checkpoint  │                 │
│         └─────────────────────┘                 │
└─────────────────────────────────────────────────┘
```

## Workflow

1. **Analyze:** Read module source, extract compilation errors
2. **Prompt:** Create context-aware fix prompt for Codex
3. **Fix:** Call Azure OpenAI, get fixed code
4. **Apply:** Write fixed code back to module
5. **Verify:** Compile and check errors
6. **Iterate:** Repeat up to 3 times if needed
7. **Report:** Save results and checkpoint

## Expected Results

### Night 1 (6-8 hours)
- **Target:** 75-85% compilation success (90-103 modules)
- **Fixes:** Simple errors, type definitions, macro expansions
- **Cost:** ~$25-40

### Night 2 (6-8 hours, if needed)
- **Target:** 85-95% compilation success (105-115 modules)
- **Fixes:** Complex errors, dependencies, type mismatches
- **Cost:** ~$15-25

### Manual Review (2-4 hours)
- **Target:** 95-99% compilation success (115-120 modules)
- **Focus:** Edge cases, optimization
- **Cost:** $0 (manual)

## Error Types Fixed

1. **Missing Types** - Define Rust equivalents of C types
2. **Macro Expansion** - Convert C macros to Rust
3. **Function Signatures** - Fix unsafe/safe mismatches
4. **Syntax Errors** - Complete truncated code
5. **FFI Compliance** - Add #[repr(C)], #[no_mangle]
6. **No_std Issues** - Add panic handlers

## Rate Limiting

- Per-endpoint: 60 requests/minute (configurable)
- Total throughput: 180 requests/minute (3 endpoints)
- Auto-backoff when limits hit
- Round-robin endpoint selection

## Cost Estimation

**Per Request:**
- Prompt: ~500 tokens
- Response: ~1000 tokens
- Cost: ~$0.015 per fix attempt

**Total for 121 Modules:**
- Attempts: 121 modules × 3 iterations = 363 max
- Successful fixes: ~250-300 attempts
- **Total Cost:** $40-60 for complete fix

## Troubleshooting

### "No valid Azure OpenAI endpoints configured"
Set environment variables with valid credentials.

### "Rate limit exceeded"
Increase sleep time between requests or add more endpoints.

### "Container failed to start"
Check ACR credentials and image availability.

### "Compilation still failing after 3 iterations"
Check final report for persistent issues, may need manual review.

## Files

- `codex_compilation_fixer.py` - Main Python script
- `deploy_overnight_batch.sh` - Azure deployment
- `Dockerfile.codex` - Container image definition
- `README.md` - This file

## Support

See main project documentation:
- [RUST_CODE_ANALYSIS.md](../RUST_CODE_ANALYSIS.md)
- [IMPLEMENTATION_COMPLETE.md](../azure_build/IMPLEMENTATION_COMPLETE.md)
