#!/bin/bash
#
# Execute Tests on Azure Container App
#

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-rust-kernel}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-rustkernelstore}"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         EXECUTING TESTS ON AZURE CONTAINER APP                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Create test job
echo "Starting test job..."

az containerapp job create \
    --name rust-kernel-test-job \
    --resource-group "$RESOURCE_GROUP" \
    --environment rust-kernel-env \
    --trigger-type Manual \
    --replica-timeout 3600 \
    --replica-retry-limit 1 \
    --parallelism 1 \
    --image rustkernel.azurecr.io/rust-kernel-builder:latest \
    --cpu 4.0 \
    --memory 8Gi \
    --command "/usr/local/bin/test_all.sh" \
    --env-vars \
        WORKSPACE_ROOT=/workspace \
        PARALLEL_JOBS=4 \
        TEST_LOG=/workspace/results/test_results.json

# Start the job
JOB_EXECUTION=$(az containerapp job start \
    --name rust-kernel-test-job \
    --resource-group "$RESOURCE_GROUP" \
    --query name -o tsv)

echo "Job started: $JOB_EXECUTION"
echo ""
echo "Monitoring job execution..."

# Wait for job completion
while true; do
    STATUS=$(az containerapp job execution show \
        --name "$JOB_EXECUTION" \
        --job-name rust-kernel-test-job \
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
echo "Downloading test results..."

STORAGE_KEY=$(az storage account keys list \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$STORAGE_ACCOUNT" \
    --query "[0].value" -o tsv)

az storage file download \
    --share-name results \
    --path test_results.json \
    --dest ./test_results.json \
    --account-name "$STORAGE_ACCOUNT" \
    --account-key "$STORAGE_KEY"

echo "✅ Test results downloaded: ./test_results.json"
echo ""

# Display summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

jq -r '"Total modules: \(.total_modules)
Tests passed: \(.passed_tests)
Tests failed: \(.failed_tests)
Tests skipped: \(.skipped_tests)
Test time: \(.test_time_seconds)s"' ./test_results.json

echo ""

# Show failed modules
FAILED_COUNT=$(jq '.failed_tests' ./test_results.json)
if [ "$FAILED_COUNT" -gt 0 ]; then
    echo "Failed modules:"
    jq -r '.modules[] | select(.status == "failed") | "  - \(.name)"' ./test_results.json
    echo ""
fi

if [ "$STATUS" = "Succeeded" ]; then
    echo "✅ Tests completed!"
    exit 0
else
    echo "❌ Some tests failed. Check test_results.json for details."
    exit 1
fi
