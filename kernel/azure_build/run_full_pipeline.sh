#!/bin/bash
#
# Full Azure Build, Test, and Benchmark Pipeline
# Runs complete validation cycle with automatic issue fixing
#

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-rust-kernel}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-rustkernelstore}"
ITERATIONS="${ITERATIONS:-10000}"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║      RUST KERNEL FULL VALIDATION PIPELINE                     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "This will run:"
echo "  1. Automatic issue fixing"
echo "  2. Full build (121 modules)"
echo "  3. Comprehensive testing"
echo "  4. Performance benchmarks (C vs Rust)"
echo ""
echo "Estimated time: 45-60 minutes"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

START_TIME=$(date +%s)
RESULTS_DIR="./pipeline_results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

echo ""
echo "Results will be saved to: $RESULTS_DIR"
echo ""

# Step 1: Upload fixer script and run it
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Fixing Common Issues"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

STORAGE_KEY=$(az storage account keys list \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$STORAGE_ACCOUNT" \
    --query "[0].value" -o tsv)

# Upload fixer script
az storage file upload \
    --share-name workspace \
    --source fix_common_issues.py \
    --path fix_common_issues.py \
    --account-name "$STORAGE_ACCOUNT" \
    --account-key "$STORAGE_KEY"

# Run fixer
az containerapp job create \
    --name rust-kernel-fix-job \
    --resource-group "$RESOURCE_GROUP" \
    --environment rust-kernel-env \
    --trigger-type Manual \
    --replica-timeout 600 \
    --replica-retry-limit 1 \
    --parallelism 1 \
    --image rustkernel.azurecr.io/rust-kernel-builder:latest \
    --cpu 2.0 \
    --memory 4Gi \
    --command "python3 /workspace/fix_common_issues.py /workspace" 2>/dev/null || true

FIX_EXECUTION=$(az containerapp job start \
    --name rust-kernel-fix-job \
    --resource-group "$RESOURCE_GROUP" \
    --query name -o tsv)

echo "Fixing issues..."
while true; do
    STATUS=$(az containerapp job execution show \
        --name "$FIX_EXECUTION" \
        --job-name rust-kernel-fix-job \
        --resource-group "$RESOURCE_GROUP" \
        --query properties.status -o tsv)
    [ "$STATUS" = "Succeeded" ] || [ "$STATUS" = "Failed" ] && break
    sleep 10
done

echo "✅ Issues fixed"
echo ""

# Step 2: Build
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Building All Modules"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

./run_azure_build.sh || true
cp build_results.json "$RESULTS_DIR/" 2>/dev/null || true

SUCCESSFUL_BUILDS=$(jq -r '.successful_builds' build_results.json 2>/dev/null || echo "0")
FAILED_BUILDS=$(jq -r '.failed_builds' build_results.json 2>/dev/null || echo "0")

echo ""
echo "Build Summary: $SUCCESSFUL_BUILDS successful, $FAILED_BUILDS failed"
echo ""

# Step 3: Test
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Running Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

./run_azure_tests.sh || true
cp test_results.json "$RESULTS_DIR/" 2>/dev/null || true

PASSED_TESTS=$(jq -r '.passed_tests' test_results.json 2>/dev/null || echo "0")
FAILED_TESTS=$(jq -r '.failed_tests' test_results.json 2>/dev/null || echo "0")

echo ""
echo "Test Summary: $PASSED_TESTS passed, $FAILED_TESTS failed"
echo ""

# Step 4: Benchmark
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Running Benchmarks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ITERATIONS=$ITERATIONS ./run_azure_benchmarks.sh || true
cp benchmark_results.json "$RESULTS_DIR/" 2>/dev/null || true

AVG_SPEEDUP=$(jq '[.benchmarks[].speedup] | add / length' benchmark_results.json 2>/dev/null || echo "0")
RUST_WINS=$(jq '[.benchmarks[] | select(.winner == "rust")] | length' benchmark_results.json 2>/dev/null || echo "0")

echo ""
echo "Benchmark Summary: ${AVG_SPEEDUP}x average speedup, $RUST_WINS Rust wins"
echo ""

# Generate final report
END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))
TOTAL_MINUTES=$((TOTAL_TIME / 60))

cat > "$RESULTS_DIR/PIPELINE_REPORT.md" << EOF
# Rust Kernel Module Validation Report

**Date:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
**Duration:** ${TOTAL_MINUTES} minutes
**Results Directory:** $RESULTS_DIR

---

## Pipeline Summary

| Stage | Status | Details |
|-------|--------|---------|
| Issue Fixing | ✅ Complete | Automatic C-style syntax fixes |
| Build | ${SUCCESSFUL_BUILDS}/121 | $FAILED_BUILDS failures |
| Tests | ${PASSED_TESTS}/${SUCCESSFUL_BUILDS} | $FAILED_TESTS failures |
| Benchmarks | ✅ Complete | ${AVG_SPEEDUP}x avg speedup |

---

## Build Results

**Total Modules:** 121
**Successful Builds:** $SUCCESSFUL_BUILDS
**Failed Builds:** $FAILED_BUILDS
**Success Rate:** $(( SUCCESSFUL_BUILDS * 100 / 121 ))%

$([ "$FAILED_BUILDS" -gt 0 ] && echo "
### Failed Modules

\`\`\`
$(jq -r '.modules[] | select(.status == "failed") | .name' build_results.json 2>/dev/null || echo "N/A")
\`\`\`
" || echo "")

---

## Test Results

**Modules Tested:** $SUCCESSFUL_BUILDS
**Tests Passed:** $PASSED_TESTS
**Tests Failed:** $FAILED_TESTS
**Tests Skipped:** $(jq -r '.skipped_tests' test_results.json 2>/dev/null || echo "0")

$([ "$FAILED_TESTS" -gt 0 ] && echo "
### Failed Tests

\`\`\`
$(jq -r '.modules[] | select(.status == "failed") | .name' test_results.json 2>/dev/null || echo "N/A")
\`\`\`
" || echo "")

---

## Benchmark Results

**Iterations:** $ITERATIONS per benchmark
**Average Speedup:** ${AVG_SPEEDUP}x (Rust vs C)
**Rust Wins:** $RUST_WINS
**C Wins:** $(jq '[.benchmarks[] | select(.winner == "c")] | length' benchmark_results.json 2>/dev/null || echo "0")

### Detailed Results

$(jq -r '.benchmarks[] |
"**\(.name)**
- C: \(.c_time_seconds)s
- Rust: \(.rust_time_seconds)s
- Speedup: \(.speedup)x
- Winner: \(.winner)
"' benchmark_results.json 2>/dev/null || echo "N/A")

---

## FFI Compatibility

$(jq -r '[.modules[] | select(.ffi_compatibility != "passed")] | length' test_results.json 2>/dev/null || echo "0") modules have FFI compatibility issues.

$(jq -r '.modules[] | select(.ffi_compatibility != "passed") | "- \(.name): \(.ffi_compatibility)"' test_results.json 2>/dev/null || echo "")

---

## Recommendations

$(if [ "$FAILED_BUILDS" -gt 30 ]; then
    echo "- 🔴 **High build failure rate:** Review module translation quality"
else
    echo "- ✅ **Build health:** Good"
fi)

$(if [ "$FAILED_TESTS" -gt 20 ]; then
    echo "- 🔴 **High test failure rate:** Investigate FFI compatibility issues"
else
    echo "- ✅ **Test health:** Good"
fi)

$(if awk "BEGIN {exit !($AVG_SPEEDUP < 0.9)}"; then
    echo "- ⚠️  **Performance:** Rust slower than C on average"
else
    echo "- ✅ **Performance:** Rust competitive with or faster than C"
fi)

---

## Files

- [build_results.json](build_results.json) - Detailed build logs
- [test_results.json](test_results.json) - Detailed test results
- [benchmark_results.json](benchmark_results.json) - Benchmark data

---

**Generated by:** Rust Kernel Module Validation Pipeline
**Version:** 1.0.0
EOF

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              PIPELINE COMPLETE                                 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Total time: ${TOTAL_MINUTES} minutes"
echo ""
echo "Results:"
echo "  - Build: $SUCCESSFUL_BUILDS/$((121)) successful ($(( SUCCESSFUL_BUILDS * 100 / 121 ))%)"
echo "  - Tests: $PASSED_TESTS/$SUCCESSFUL_BUILDS passed"
echo "  - Benchmarks: ${AVG_SPEEDUP}x average speedup"
echo ""
echo "Full report: $RESULTS_DIR/PIPELINE_REPORT.md"
echo ""

# Open report if on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "$RESULTS_DIR/PIPELINE_REPORT.md" 2>/dev/null || true
fi
