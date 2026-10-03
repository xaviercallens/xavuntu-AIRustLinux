# C to Rust Compilation Benchmark

Automated benchmarking system for evaluating C to Rust translation quality in Linux kernel modules.

## Overview

This benchmark compares:
- **Compilation success rate**: C vs Rust
- **Compilation time**: Performance overhead  
- **Binary size**: Memory overhead
- **Error types**: Common translation issues
- **Fix effectiveness**: AI-powered error reduction

## Components

### 1. Benchmark Script

**File:** `c_to_rust_compilation_benchmark.py`

**Usage:**
```bash
# Run on all modules
python3 benchmarks/c_to_rust_compilation_benchmark.py

# Run on specific modules
python3 benchmarks/c_to_rust_compilation_benchmark.py \
  /path/to/workspace \
  netfilter,af_inet,fib_trie,udp
```

**Output:**
- `benchmarks/results/benchmark_YYYYMMDD_HHMMSS.json` - Machine-readable results
- `benchmarks/results/benchmark_YYYYMMDD_HHMMSS.md` - Human-readable report

### 2. Azure Function

**Directory:** `benchmarks/azure_function_benchmark/`

Deploy as HTTP-triggered Azure Function for CI/CD integration.

**Endpoints:**

```http
GET /api/benchmark?modules=netfilter,af_inet&format=json
GET /api/benchmark?format=markdown
POST /api/benchmark
```

**Parameters:**
- `modules` - Comma-separated list of modules (optional)
- `workspace` - Workspace path (default: /workspace)
- `format` - `json` or `markdown` (default: json)

**Response Format (JSON):**
```json
{
  "status": "success",
  "metrics": {
    "total_modules": 121,
    "rust_success_count": 92,
    "translation_accuracy": 76.0,
    "error_reduction": 68.5,
    "performance_ratio": 1.45,
    "size_ratio": 1.23
  },
  "summary": {
    "translation_accuracy": "76.0%",
    "rust_success": "92/121",
    "error_reduction": "68.5%",
    "benchmark_passed": true
  }
}
```

## Deployment

### Local Testing

```bash
cd /Users/xcallens/rust-linux-mini-kernel

# Install dependencies
pip3 install -r benchmarks/requirements.txt

# Run benchmark
python3 benchmarks/c_to_rust_compilation_benchmark.py
```

### Azure Function Deployment

**Prerequisites:**
- Azure Functions Core Tools
- Azure CLI
- Azure subscription

**Steps:**

1. **Create Function App:**
```bash
az functionapp create \
  --name rust-benchmark-func \
  --resource-group rg-rust-kernel \
  --storage-account ruststore64044 \
  --consumption-plan-location swedencentral \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --os-type Linux
```

2. **Deploy Function:**
```bash
cd /Users/xcallens/rust-linux-mini-kernel/benchmarks

func azure functionapp publish rust-benchmark-func
```

3. **Test Deployment:**
```bash
# Get function URL
FUNC_URL=$(az functionapp function show \
  --name rust-benchmark-func \
  --resource-group rg-rust-kernel \
  --function-name benchmark \
  --query "invokeUrlTemplate" -o tsv)

# Test endpoint
curl "$FUNC_URL?modules=netfilter,af_inet&format=json"
```

### CI/CD Integration

**GitHub Actions Workflow:**

```yaml
name: Benchmark C to Rust Translation

on:
  push:
    branches: [main, master]
    paths:
      - 'crates/**/*.rs'
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install Rust
        uses: actions-rust-lang/setup-rust-toolchain@v1

      - name: Run Benchmark
        run: |
          cd benchmarks
          python3 c_to_rust_compilation_benchmark.py

      - name: Upload Results
        uses: actions/upload-artifact@v3
        with:
          name: benchmark-results
          path: benchmarks/results/

      - name: Check Pass/Fail
        run: |
          ACCURACY=$(jq -r '.metrics.translation_accuracy' benchmarks/results/benchmark_*.json | tail -1)
          if (( $(echo "$ACCURACY < 75" | bc -l) )); then
            echo "❌ Benchmark failed: accuracy $ACCURACY% < 75%"
            exit 1
          fi
          echo "✅ Benchmark passed: accuracy $ACCURACY%"
```

## Metrics

### Translation Accuracy

**Formula:** `(Rust modules compiling / Total modules) × 100%`

**Target:** ≥75%

**Interpretation:**
- 90-100%: Excellent - production ready
- 75-89%: Good - minor fixes needed
- 50-74%: Fair - significant work required
- <50%: Poor - review translation approach

### Error Reduction

**Formula:** `((Initial errors - Final errors) / Initial errors) × 100%`

**Target:** ≥50%

**Interpretation:**
- 80-100%: AI fixes highly effective
- 50-79%: AI fixes moderately effective
- <50%: Manual intervention needed

### Performance Ratio

**Formula:** `Rust compile time / C compile time`

**Target:** <2.0x

**Expected:**
- 1.0-1.5x: Excellent - comparable to C
- 1.5-2.0x: Good - acceptable overhead
- 2.0-3.0x: Fair - optimization opportunity
- >3.0x: Poor - investigate build config

### Size Ratio

**Formula:** `Rust binary size / C binary size`

**Target:** <1.5x

**Expected:**
- 1.0-1.2x: Excellent - minimal overhead
- 1.2-1.5x: Good - acceptable
- 1.5-2.0x: Fair - review safety overhead
- >2.0x: Poor - investigate binary bloat

## Example Output

### Console Output

```
================================================================================
C to Rust Compilation Benchmark
================================================================================

Testing 8 modules...
Benchmarking: netfilter
Benchmarking: af_inet
Benchmarking: fib_trie
Benchmarking: udp
Benchmarking: tcp
Benchmarking: route
Benchmarking: arp
Benchmarking: core

✅ Results saved:
   JSON: benchmarks/results/benchmark_20260517_084500.json
   Markdown: benchmarks/results/benchmark_20260517_084500.md

================================================================================
BENCHMARK SUMMARY
================================================================================
Translation Accuracy: 75.0%
Rust Modules Compiling: 6/8
Error Reduction: 68.4%
Performance Ratio: 1.45x
Size Ratio: 1.23x

✅ BENCHMARK PASSED
```

### Markdown Report Preview

```markdown
# C to Rust Compilation Benchmark Report

**Generated:** 2026-05-17 08:45:00
**Total Modules:** 8

## Executive Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| **Translation Accuracy** | 75.0% | ≥75% | ✅ PASS |
| **Rust Modules Compiling** | 6/8 | - | - |
| **Error Reduction** | 68.4% | ≥50% | ✅ PASS |

### Performance Comparison

| Metric | C | Rust | Ratio |
|--------|---|------|-------|
| **Avg Compile Time** | 250ms | 363ms | 1.45x |
| **Avg Binary Size** | 45.2KB | 55.6KB | 1.23x |
```

## Cost Analysis

### Azure Function Costs

**Pricing Model:** Consumption Plan

**Resources:**
- Memory: 1536 MB
- Execution time: ~2-3 minutes per benchmark
- Invocations: Daily (30/month)

**Monthly Cost Estimate:**
- Executions: 30 × $0.000001 = $0.00003
- Compute: 30 × 3min × 1.5GB × $0.000016 = $0.00216
- **Total: ~$0.0022/month ($0.03/year)**

### Local Execution

**Resources:**
- Laptop/Desktop: No cost
- CI/CD runner: Included in GitHub free tier
- **Total: $0**

**Recommendation:** Run locally or in CI/CD for cost efficiency

## Monitoring & Alerts

### Azure Application Insights

```bash
# Enable Application Insights
az monitor app-insights component create \
  --app rust-benchmark-insights \
  --location swedencentral \
  --resource-group rg-rust-kernel

# Link to Function App
az functionapp config appsettings set \
  --name rust-benchmark-func \
  --resource-group rg-rust-kernel \
  --settings "APPINSIGHTS_INSTRUMENTATIONKEY=<key>"
```

### Alert Rules

**Translation Accuracy Drop:**
```bash
az monitor metrics alert create \
  --name benchmark-accuracy-alert \
  --resource-group rg-rust-kernel \
  --scopes /subscriptions/.../rust-benchmark-func \
  --condition "avg translation_accuracy < 70" \
  --description "Alert when translation accuracy drops below 70%"
```

## Troubleshooting

### Common Issues

**Issue:** "gcc: command not found"
- **Fix:** Install GCC: `apt-get install gcc` or `yum install gcc`

**Issue:** "Linux headers not found"
- **Fix:** Install headers: `apt-get install linux-headers-$(uname -r)`

**Issue:** "cargo: command not found"  
- **Fix:** Install Rust: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`

**Issue:** Timeout after 120s
- **Fix:** Increase timeout in function.json or skip large modules

**Issue:** Out of memory
- **Fix:** Increase Azure Function memory allocation to 2048 MB

### Debug Mode

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Run benchmark with debug output
benchmark = CToRustBenchmark(workspace)
benchmark.debug = True  # Add debug flag
```

## Roadmap

### Planned Features

- [ ] **Runtime benchmarks** - Compare execution performance (not just compilation)
- [ ] **Memory safety analysis** - Miri integration for UB detection
- [ ] **Regression tracking** - Historical trend analysis
- [ ] **Diff-based benchmarks** - Only test changed modules
- [ ] **Parallel compilation** - Speed up benchmark execution
- [ ] **Custom metrics** - User-defined quality criteria

### Integration Opportunities

- **SocrateAssist Orchestrator** - Use as translation quality gate
- **GitHub PR comments** - Auto-comment benchmark results
- **Slack notifications** - Alert team on failures
- **Grafana dashboards** - Visualize trends over time

## Support

**Issues:** https://github.com/xaviercallens/rust-linux-mini-kernel/issues
**Documentation:** This file
**Contact:** Xavier Callens

---

**Created:** 2026-05-17
**Version:** 1.0
**License:** GPL-2.0 (matching kernel license)
