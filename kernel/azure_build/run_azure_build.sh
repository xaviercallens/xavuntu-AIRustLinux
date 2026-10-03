#!/bin/bash
#
# Execute Build on Azure Container App
#

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-rust-kernel}"
CONTAINER_APP="${CONTAINER_APP:-rust-kernel-builder}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-rustkernelstore}"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        EXECUTING BUILD ON AZURE CONTAINER APP                 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Trigger container app job
echo "Starting build job..."

az containerapp job create \
    --name rust-kernel-build-job \
    --resource-group "$RESOURCE_GROUP" \
    --environment rust-kernel-env \
    --trigger-type Manual \
    --replica-timeout 3600 \
    --replica-retry-limit 1 \
    --parallelism 1 \
    --image rustkernel.azurecr.io/rust-kernel-builder:latest \
    --cpu 4.0 \
    --memory 8Gi \
    --command "/usr/local/bin/build_all.sh" \
    --env-vars \
        WORKSPACE_ROOT=/workspace \
        PARALLEL_JOBS=4 \
        BUILD_LOG=/workspace/results/build_results.json

# Start the job
JOB_EXECUTION=$(az containerapp job start \
    --name rust-kernel-build-job \
    --resource-group "$RESOURCE_GROUP" \
    --query name -o tsv)

echo "Job started: $JOB_EXECUTION"
echo ""
echo "Monitoring job execution..."

# Wait for job completion
while true; do
    STATUS=$(az containerapp job execution show \
        --name "$JOB_EXECUTION" \
        --job-name rust-kernel-build-job \
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
echo "Downloading build results..."

STORAGE_KEY=$(az storage account keys list \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$STORAGE_ACCOUNT" \
    --query "[0].value" -o tsv)

az storage file download \
    --share-name results \
    --path build_results.json \
    --dest ./build_results.json \
    --account-name "$STORAGE_ACCOUNT" \
    --account-key "$STORAGE_KEY"

echo "✅ Build results downloaded: ./build_results.json"
echo ""

# Display summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "BUILD SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

jq -r '"Total modules: \(.total_modules)
Successful: \(.successful_builds)
Failed: \(.failed_builds)
Warnings: \(.warnings)
Build time: \(.build_time_seconds)s
Success rate: \((.successful_builds / .total_modules * 100 | floor))%"' ./build_results.json

echo ""

if [ "$STATUS" = "Succeeded" ]; then
    echo "✅ Build completed successfully!"
    exit 0
else
    echo "❌ Build failed. Check build_results.json for details."
    exit 1
fi
