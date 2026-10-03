#!/bin/bash
#
# Execute Benchmarks on Azure Container App
#

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-rust-kernel}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-rustkernelstore}"
ITERATIONS="${ITERATIONS:-10000}"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║      EXECUTING BENCHMARKS ON AZURE CONTAINER APP              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Iterations: $ITERATIONS"
echo ""

# Create benchmark job
echo "Starting benchmark job..."

az containerapp job create \
    --name rust-kernel-benchmark-job \
    --resource-group "$RESOURCE_GROUP" \
    --environment rust-kernel-env \
    --trigger-type Manual \
    --replica-timeout 1800 \
    --replica-retry-limit 1 \
    --parallelism 1 \
    --image rustkernel.azurecr.io/rust-kernel-builder:latest \
    --cpu 4.0 \
    --memory 8Gi \
    --command "/usr/local/bin/benchmark_suite.sh" \
    --env-vars \
        WORKSPACE_ROOT=/workspace \
        ITERATIONS="$ITERATIONS" \
        BENCHMARK_LOG=/workspace/results/benchmark_results.json

# Start the job
JOB_EXECUTION=$(az containerapp job start \
    --name rust-kernel-benchmark-job \
    --resource-group "$RESOURCE_GROUP" \
    --query name -o tsv)

echo "Job started: $JOB_EXECUTION"
echo ""
echo "Monitoring job execution..."

# Wait for job completion
while true; do
    STATUS=$(az containerapp job execution show \
        --name "$JOB_EXECUTION" \
        --job-name rust-kernel-benchmark-job \
        --resource-group "$RESOURCE_GROUP" \
        --query properties.status -o tsv)

    echo "Status: $STATUS"

    if [ "$STATUS" = "Succeeded" ] || [ "$STATUS" = "Failed" ]; then
        break
    fi

    sleep 30
done

echo ""
echo "Job completed with status: $STATUS"
echo ""

# Download results
echo "Downloading benchmark results..."

STORAGE_KEY=$(az storage account keys list \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$STORAGE_ACCOUNT" \
    --query "[0].value" -o tsv)

az storage file download \
    --share-name results \
    --path benchmark_results.json \
    --dest ./benchmark_results.json \
    --account-name "$STORAGE_ACCOUNT" \
    --account-key "$STORAGE_KEY"

echo "✅ Benchmark results downloaded: ./benchmark_results.json"
echo ""

# Display summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "BENCHMARK SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

jq -r '.benchmarks[] |
"[\(.name)]
  C:    \(.c_time_seconds)s
  Rust: \(.rust_time_seconds)s
  Speedup: \(.speedup)x (\(.winner) wins)
"' ./benchmark_results.json

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Calculate average speedup
AVG_SPEEDUP=$(jq '[.benchmarks[].speedup] | add / length' ./benchmark_results.json)
echo "Average speedup: ${AVG_SPEEDUP}x"
echo ""

# Count wins
RUST_WINS=$(jq '[.benchmarks[] | select(.winner == "rust")] | length' ./benchmark_results.json)
C_WINS=$(jq '[.benchmarks[] | select(.winner == "c")] | length' ./benchmark_results.json)

echo "Rust wins: $RUST_WINS"
echo "C wins: $C_WINS"
echo ""

echo "✅ Benchmarks completed!"
