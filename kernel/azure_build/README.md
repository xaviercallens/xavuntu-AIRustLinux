# Azure Build, Test, and Benchmark System

Comprehensive Azure-based infrastructure for building, testing, and benchmarking Rust Linux kernel FFI modules.

## 🚀 Quick Start

### Prerequisites

- Azure CLI installed (`az`)
- Docker installed
- Azure subscription with permissions to create resources

### Deployment

```bash
cd azure_build

# Set environment variables (optional)
export RESOURCE_GROUP=rg-rust-kernel
export LOCATION=swedencentral
export ACR_NAME=rustkernel
export STORAGE_ACCOUNT=rustkernelstore

# Deploy infrastructure
chmod +x deploy_to_azure.sh
./deploy_to_azure.sh
```

This creates:
- Resource Group
- Azure Container Registry (ACR)
- Storage Account with file shares
- Container Apps Environment
- Container App with build/test/benchmark capabilities

### Running Operations

**Build all modules:**
```bash
chmod +x run_azure_build.sh
./run_azure_build.sh
```

**Run tests:**
```bash
chmod +x run_azure_tests.sh
./run_azure_tests.sh
```

**Execute benchmarks:**
```bash
chmod +x run_azure_benchmarks.sh
ITERATIONS=10000 ./run_azure_benchmarks.sh
```

## 📦 Components

### Docker Container

**Dockerfile** - Build environment with:
- Rust 1.82 toolchain
- Linux kernel headers
- Build tools (gcc, clang, make)
- Benchmarking tools (hyperfine, perf)
- Python for analysis

**Build:** `docker build -t rust-kernel-builder .`

### Build System

**build_all.sh** - Parallel module compilation
- Builds all 121 Rust modules
- 4 parallel jobs (configurable)
- Comprehensive error logging
- JSON output with build statistics

**Output:** `build_results.json`
```json
{
  "build_start": "2026-05-16T20:00:00Z",
  "build_end": "2026-05-16T20:15:00Z",
  "total_modules": 121,
  "successful_builds": 95,
  "failed_builds": 26,
  "warnings": 342,
  "build_time_seconds": 900,
  "modules": [
    {
      "name": "netfilter",
      "status": "success",
      "build_time_seconds": 15,
      "warnings": 3,
      "errors": []
    }
  ]
}
```

### Test System

**test_all.sh** - Comprehensive testing
- Cargo test for all modules
- Clippy linting
- FFI compatibility checks (repr(C), extern "C")
- Parallel execution

**Output:** `test_results.json`
```json
{
  "test_start": "2026-05-16T20:15:00Z",
  "test_end": "2026-05-16T20:30:00Z",
  "total_modules": 121,
  "passed_tests": 85,
  "failed_tests": 10,
  "skipped_tests": 26,
  "test_time_seconds": 900,
  "modules": [
    {
      "name": "netfilter",
      "status": "passed",
      "test_time_seconds": 12,
      "tests_passed": 5,
      "clippy_warnings": 2,
      "ffi_compatibility": "passed"
    }
  ]
}
```

### Benchmark System

**benchmark_suite.sh** - C vs Rust performance comparison

**Benchmarks:**
1. **Socket Buffer Allocation** - Memory allocation/deallocation
2. **ARP Packet Processing** - Network packet handling
3. **Route Lookup (FIB)** - Binary tree traversal

**Output:** `benchmark_results.json`
```json
{
  "benchmark_start": "2026-05-16T20:30:00Z",
  "benchmark_end": "2026-05-16T20:35:00Z",
  "iterations": 10000,
  "benchmarks": [
    {
      "name": "Socket Buffer Allocation",
      "c_time_seconds": 0.125,
      "rust_time_seconds": 0.118,
      "speedup": 1.059,
      "iterations": 10000,
      "winner": "rust"
    },
    {
      "name": "ARP Packet Processing",
      "c_time_seconds": 0.089,
      "rust_time_seconds": 0.091,
      "speedup": 0.978,
      "iterations": 10000,
      "winner": "c"
    },
    {
      "name": "Route Lookup (FIB)",
      "c_time_seconds": 0.056,
      "rust_time_seconds": 0.054,
      "speedup": 1.037,
      "iterations": 10000,
      "winner": "rust"
    }
  ]
}
```

## 🔧 Configuration

### Environment Variables

**Build System:**
- `WORKSPACE_ROOT` - Workspace directory (default: `/workspace`)
- `PARALLEL_JOBS` - Number of parallel jobs (default: `4`)
- `BUILD_LOG` - Build results file (default: `/workspace/build_results.json`)

**Test System:**
- `TEST_LOG` - Test results file (default: `/workspace/test_results.json`)

**Benchmark System:**
- `ITERATIONS` - Number of benchmark iterations (default: `1000`)
- `BENCHMARK_LOG` - Benchmark results file (default: `/workspace/benchmark_results.json`)

### Azure Resources

**Container App:**
- CPU: 4.0 cores
- Memory: 8 GiB
- Min replicas: 0 (scale to zero)
- Max replicas: 5
- Timeout: 3600s (1 hour)

**Storage:**
- Account: Standard_LRS
- File shares:
  - `workspace` - Source code (100 GB)
  - `results` - Build/test/benchmark results (50 GB)

## 📊 Results Analysis

### Build Results

```bash
# View summary
jq '.total_modules, .successful_builds, .failed_builds, .warnings' build_results.json

# List failed modules
jq -r '.modules[] | select(.status == "failed") | .name' build_results.json

# Show errors for a specific module
jq '.modules[] | select(.name == "af_inet") | .errors' build_results.json
```

### Test Results

```bash
# View test summary
jq '.passed_tests, .failed_tests, .skipped_tests' test_results.json

# List modules with failing tests
jq -r '.modules[] | select(.status == "failed") | .name' test_results.json

# Check FFI compatibility issues
jq -r '.modules[] | select(.ffi_compatibility != "passed") | "\(.name): \(.ffi_compatibility)"' test_results.json
```

### Benchmark Results

```bash
# View all benchmarks
jq -r '.benchmarks[] | "\(.name): \(.speedup)x (\(.winner) wins)"' benchmark_results.json

# Calculate average speedup
jq '[.benchmarks[].speedup] | add / length' benchmark_results.json

# Count wins
jq '[.benchmarks[] | select(.winner == "rust")] | length' benchmark_results.json
```

## 🐛 Troubleshooting

### Build Failures

**Common Issues:**

1. **Missing dependencies:** Check Dockerfile has all required packages
2. **Out of memory:** Increase container memory or reduce parallel jobs
3. **Syntax errors:** Run `cargo check` locally first
4. **FFI issues:** Verify `#[repr(C)]` and `extern "C"` usage

### Test Failures

**Common Issues:**

1. **No tests found:** Modules may not have test coverage yet
2. **Clippy warnings:** Run `cargo clippy --fix` locally
3. **FFI compatibility:** Ensure all structs have `#[repr(C)]`

### Deployment Issues

**Common Issues:**

1. **ACR authentication:** Run `az acr login --name $ACR_NAME`
2. **Storage mount:** Verify storage account key is correct
3. **Job timeout:** Increase `replica-timeout` in job creation
4. **Resource limits:** Check Azure subscription quotas

## 🔄 CI/CD Integration

### GitHub Actions Example

```yaml
name: Azure Build and Test

on: [push, pull_request]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Azure Login
        uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Run Build
        run: |
          cd azure_build
          ./run_azure_build.sh

      - name: Run Tests
        run: |
          cd azure_build
          ./run_azure_tests.sh

      - name: Upload Results
        uses: actions/upload-artifact@v3
        with:
          name: results
          path: |
            azure_build/build_results.json
            azure_build/test_results.json
```

## 📈 Performance Expectations

### Build Performance

- **Total time:** ~15-20 minutes for 121 modules
- **Parallel jobs:** 4 (4-core container)
- **Success rate:** 75-85% (depends on module quality)
- **Memory usage:** ~6-7 GB peak

### Test Performance

- **Total time:** ~10-15 minutes
- **Coverage:** FFI compatibility, clippy, unit tests
- **Expected pass rate:** 70-80%

### Benchmark Performance

- **Total time:** ~5-10 minutes (10,000 iterations each)
- **Variance:** ±2-3% typical
- **Expected results:** Rust competitive with C (0.9x - 1.2x)

## 📝 Cost Estimation

**Azure Resources (Monthly):**

- Container Apps: ~$50-100 (based on usage)
- Storage Account: ~$5-10 (100 GB)
- Container Registry: ~$5 (Basic tier)
- Data transfer: ~$2-5

**Per Build Run:**
- Compute: ~$0.20-0.30 (15-20 minutes)
- Storage: ~$0.01

**Estimated monthly cost for daily builds:** ~$70-130

## 🔗 References

- [Azure Container Apps Documentation](https://docs.microsoft.com/azure/container-apps/)
- [Rust FFI Guide](https://doc.rust-lang.org/nomicon/ffi.html)
- [Linux Kernel Rust](https://rust-for-linux.com/)

---

**Version:** 1.0.0  
**Last Updated:** 2026-05-16  
**Maintainer:** rust-linux-mini-kernel project
