# Azure Build, Test, and Benchmark Deployment Guide

Complete guide for deploying and using the Azure-based Rust kernel module validation infrastructure.

## 🎯 Overview

This system provides comprehensive Azure-based CI/CD for the Rust Linux Mini Kernel project, including:

- **Automated compilation** of all 121 Rust FFI modules
- **Comprehensive testing** (unit tests, clippy, FFI validation)
- **Performance benchmarking** (C vs Rust comparison)
- **Automatic issue fixing** (C-style syntax, missing FFI markers)

## 📋 Prerequisites

### Required Tools

```bash
# Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Docker
sudo apt-get install docker.io  # Linux
# or
brew install docker  # macOS

# jq (JSON processor)
sudo apt-get install jq  # Linux
brew install jq  # macOS
```

### Azure Requirements

- Active Azure subscription
- Permission to create:
  - Resource Groups
  - Container Registry
  - Storage Accounts
  - Container Apps

## 🚀 Quick Start (5 Steps)

### Step 1: Clone Repository

```bash
git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git
cd rust-linux-mini-kernel/azure_build
```

### Step 2: Login to Azure

```bash
az login
az account set --subscription "YOUR_SUBSCRIPTION_ID"
```

### Step 3: Deploy Infrastructure

```bash
# Set environment variables (optional, defaults provided)
export RESOURCE_GROUP=rg-rust-kernel
export LOCATION=swedencentral
export ACR_NAME=rustkernel
export STORAGE_ACCOUNT=rustkernelstore

# Deploy (takes ~10-15 minutes)
./deploy_to_azure.sh
```

This creates:
- ✅ Resource Group (`rg-rust-kernel`)
- ✅ Container Registry (`rustkernel.azurecr.io`)
- ✅ Storage Account (150 GB capacity)
- ✅ Container Apps Environment
- ✅ Container App (4 cores, 8 GB RAM)

### Step 4: Run Full Pipeline

```bash
# Execute complete validation cycle
./run_full_pipeline.sh
```

This runs:
1. **Fix common issues** (5 min) - Automatic C-style syntax fixes
2. **Build all modules** (15-20 min) - Compile 121 modules in parallel
3. **Run tests** (10-15 min) - Unit tests, clippy, FFI checks
4. **Execute benchmarks** (5-10 min) - C vs Rust performance comparison

**Total time:** 45-60 minutes

### Step 5: Review Results

```bash
# Results are in: pipeline_results_YYYYMMDD_HHMMSS/
ls -la pipeline_results_*/

# View comprehensive report
cat pipeline_results_*/PIPELINE_REPORT.md

# View JSON results
jq '.' pipeline_results_*/build_results.json
jq '.' pipeline_results_*/test_results.json
jq '.' pipeline_results_*/benchmark_results.json
```

## 🔧 Individual Operations

### Build Only

```bash
./run_azure_build.sh
```

**Output:** `build_results.json`

```json
{
  "total_modules": 121,
  "successful_builds": 95,
  "failed_builds": 26,
  "warnings": 342,
  "build_time_seconds": 900,
  "modules": [...]
}
```

**Expected Results:**
- Success rate: 75-85%
- Duration: 15-20 minutes
- Common failures: C-style syntax, missing dependencies

### Test Only

```bash
./run_azure_tests.sh
```

**Output:** `test_results.json`

```json
{
  "total_modules": 121,
  "passed_tests": 85,
  "failed_tests": 10,
  "skipped_tests": 26,
  "test_time_seconds": 900,
  "modules": [...]
}
```

**Expected Results:**
- Pass rate: 70-80%
- Duration: 10-15 minutes
- Tests skipped: Modules without test coverage

### Benchmark Only

```bash
# Default: 10,000 iterations
./run_azure_benchmarks.sh

# Custom iterations
ITERATIONS=100000 ./run_azure_benchmarks.sh
```

**Output:** `benchmark_results.json`

```json
{
  "benchmarks": [
    {
      "name": "Socket Buffer Allocation",
      "c_time_seconds": 0.125,
      "rust_time_seconds": 0.118,
      "speedup": 1.059,
      "winner": "rust"
    }
  ]
}
```

**Expected Results:**
- Duration: 5-10 minutes
- Speedup: 0.9x - 1.2x (Rust vs C)
- Winner: Depends on optimization level

## 📊 Understanding Results

### Build Results Analysis

**View summary:**
```bash
jq '{total: .total_modules, success: .successful_builds, failed: .failed_builds, rate: ((.successful_builds / .total_modules * 100) | floor)}' build_results.json
```

**List failed modules:**
```bash
jq -r '.modules[] | select(.status == "failed") | .name' build_results.json
```

**View errors for specific module:**
```bash
jq '.modules[] | select(.name == "af_inet") | .errors[]' build_results.json
```

**Common Build Issues:**

| Issue | Cause | Fix |
|-------|-------|-----|
| `goto` statements | C-style control flow | Automatic fixer removes |
| `->` operator | Pointer dereference | Fixed to `(*ptr).field` |
| `type` keyword | Rust reserved word | Renamed to `type_field` |
| Missing `#[repr(C)]` | FFI incompatibility | Auto-added by fixer |

### Test Results Analysis

**View summary:**
```bash
jq '{passed: .passed_tests, failed: .failed_tests, skipped: .skipped_tests}' test_results.json
```

**FFI compatibility issues:**
```bash
jq -r '.modules[] | select(.ffi_compatibility != "passed") | "\(.name): \(.ffi_compatibility)"' test_results.json
```

**Clippy warnings:**
```bash
jq '[.modules[].clippy_warnings] | add' test_results.json
```

**Common Test Issues:**

| Issue | Cause | Fix |
|-------|-------|-----|
| No tests found | Module lacks test coverage | Add `#[cfg(test)]` module |
| Clippy warnings | Code style issues | Run `cargo clippy --fix` |
| FFI check fails | Missing markers | Run automatic fixer |

### Benchmark Results Analysis

**View all benchmarks:**
```bash
jq -r '.benchmarks[] | "\(.name): \(.speedup)x (\(.winner) wins)"' benchmark_results.json
```

**Calculate statistics:**
```bash
# Average speedup
jq '[.benchmarks[].speedup] | add / length' benchmark_results.json

# Rust wins
jq '[.benchmarks[] | select(.winner == "rust")] | length' benchmark_results.json

# C wins
jq '[.benchmarks[] | select(.winner == "c")] | length' benchmark_results.json
```

**Interpreting Results:**

| Speedup | Interpretation |
|---------|----------------|
| > 1.1x | Rust significantly faster |
| 0.9x - 1.1x | Rust competitive with C |
| < 0.9x | Rust slower (may need optimization) |

## 🔍 Troubleshooting

### Deployment Issues

**Error: Resource Group already exists**
```bash
# Use existing or delete
az group delete --name rg-rust-kernel --yes
```

**Error: ACR name not available**
```bash
# Use different name
export ACR_NAME=rustkernel$(date +%s)
```

**Error: Storage account name not available**
```bash
# Use different name
export STORAGE_ACCOUNT=ruststore$(date +%s)
```

### Build Issues

**Error: Job timeout**
```bash
# Increase timeout in script (default: 3600s)
# Edit run_azure_build.sh, line with --replica-timeout
```

**Error: Out of memory**
```bash
# Reduce parallel jobs
# In build_all.sh, set PARALLEL_JOBS=2
```

**Error: Module compilation fails**
```bash
# Run fixer first
python3 fix_common_issues.py /workspace

# Or check specific module locally
cd crates/MODULE_NAME
cargo build 2>&1 | less
```

### Test Issues

**Error: Tests hang**
```bash
# Check for infinite loops
# Review module's test section
```

**Error: FFI compatibility failures**
```bash
# Run fixer to add markers
python3 fix_common_issues.py /workspace
```

### Benchmark Issues

**Error: C compilation fails**
```bash
# Check gcc is installed in container
docker run rustkernel.azurecr.io/rust-kernel-builder:latest gcc --version
```

**Error: High variance in results**
```bash
# Increase iterations
ITERATIONS=100000 ./run_azure_benchmarks.sh
```

## 💰 Cost Optimization

### Current Costs (Estimated)

**Per Build Run:**
- Container Apps: ~$0.20-0.30 (45-60 min)
- Storage transactions: ~$0.01
- **Total per run:** ~$0.25-0.35

**Monthly (Daily Builds):**
- Container Apps: ~$7.50-10.50
- Storage: ~$5-10 (150 GB)
- Container Registry: ~$5
- **Total monthly:** ~$17.50-25.50

### Optimization Tips

1. **Use scale-to-zero:** Already configured (min replicas: 0)
2. **Reduce parallel jobs:** Less CPU usage
3. **Use spot instances:** Not available for Container Apps yet
4. **Archive old results:** Delete old storage files
5. **Run less frequently:** Only on PRs/main branch

## 📈 Performance Tuning

### Faster Builds

**Increase parallel jobs:**
```bash
# In build_all.sh
export PARALLEL_JOBS=8  # Requires more CPU/RAM
```

**Use caching:**
```bash
# Add volume mount for Cargo cache
# Already configured in deployment
```

**Reduce logging:**
```bash
# Less verbose output = faster
export RUST_BACKTRACE=0
```

### Better Benchmarks

**More iterations:**
```bash
ITERATIONS=100000 ./run_azure_benchmarks.sh
```

**Dedicated cores:**
```bash
# In benchmark job, isolate CPU cores
# Requires VM-based deployment (not Container Apps)
```

**Disable turbo boost:**
```bash
# For consistent results
# Requires host system access
```

## 🔄 CI/CD Integration

### GitHub Actions

```yaml
name: Azure Build and Test

on:
  push:
    branches: [main]
  pull_request:

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Azure Login
        uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Run Pipeline
        run: |
          cd azure_build
          ./run_full_pipeline.sh

      - name: Upload Results
        uses: actions/upload-artifact@v3
        with:
          name: validation-results
          path: azure_build/pipeline_results_*

      - name: Comment PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const results = fs.readFileSync('azure_build/pipeline_results_*/PIPELINE_REPORT.md', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.name,
              body: results
            });
```

### Azure DevOps

```yaml
trigger:
  - main

pool:
  vmImage: 'ubuntu-latest'

steps:
  - task: AzureCLI@2
    displayName: 'Run Build Pipeline'
    inputs:
      azureSubscription: 'Rust-Kernel-Connection'
      scriptType: 'bash'
      scriptLocation: 'scriptPath'
      scriptPath: 'azure_build/run_full_pipeline.sh'

  - task: PublishBuildArtifacts@1
    displayName: 'Publish Results'
    inputs:
      pathToPublish: 'azure_build/pipeline_results_*'
      artifactName: 'validation-results'
```

## 📚 Advanced Usage

### Custom Docker Image

```bash
# Add custom tools to Dockerfile
cd azure_build
vim Dockerfile  # Add your dependencies

# Rebuild and push
docker build -t rustkernel.azurecr.io/rust-kernel-builder:custom .
docker push rustkernel.azurecr.io/rust-kernel-builder:custom

# Update Container App to use new image
az containerapp update \
  --name rust-kernel-builder \
  --resource-group rg-rust-kernel \
  --image rustkernel.azurecr.io/rust-kernel-builder:custom
```

### Custom Benchmarks

```bash
# Edit benchmark_suite.sh to add new benchmarks
cd azure_build
vim benchmark_suite.sh

# Add new C and Rust implementations
# Follow existing pattern:
# 1. Write C version
# 2. Write Rust version
# 3. Compile both
# 4. Run and compare
```

### Remote Debugging

```bash
# Connect to running container
az containerapp exec \
  --name rust-kernel-builder \
  --resource-group rg-rust-kernel \
  --command /bin/bash

# Inside container:
cd /workspace
cargo build --package MODULE_NAME
```

## 🔐 Security

### Secrets Management

```bash
# Store GitHub token for private repos
az containerapp secret set \
  --name rust-kernel-builder \
  --resource-group rg-rust-kernel \
  --secrets github-token=$GITHUB_TOKEN

# Use in environment
az containerapp update \
  --name rust-kernel-builder \
  --resource-group rg-rust-kernel \
  --set-env-vars GITHUB_TOKEN=secretref:github-token
```

### Network Security

```bash
# Disable public access to ACR
az acr update \
  --name rustkernel \
  --public-network-enabled false

# Use private endpoint
az acr private-endpoint-connection create \
  --name rustkernel-private \
  --resource-group rg-rust-kernel \
  --registry-name rustkernel
```

## 📖 References

- [Azure Container Apps Docs](https://docs.microsoft.com/azure/container-apps/)
- [Rust FFI Guide](https://doc.rust-lang.org/nomicon/ffi.html)
- [Linux Kernel Rust](https://rust-for-linux.com/)
- [Cargo Book](https://doc.rust-lang.org/cargo/)

---

**Version:** 1.0.0  
**Last Updated:** 2026-05-16  
**Maintainer:** rust-linux-mini-kernel project  
**Support:** https://github.com/xaviercallens/rust-linux-mini-kernel/issues
