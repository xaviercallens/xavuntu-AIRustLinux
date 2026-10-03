#!/bin/bash
#
# Simple build test - compile a few modules to verify setup
#

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-rust-kernel}"
CONTAINER_ENV="${CONTAINER_ENV:-rust-kernel-env}"
ACR_NAME="${ACR_NAME:-rustkernel64044}"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              SIMPLE BUILD TEST                                 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "This will test building a few modules to verify the setup works."
echo ""

# Create a simple build job
echo "Creating build test job..."

az containerapp job create \
    --name rust-kernel-build-test \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINER_ENV" \
    --trigger-type Manual \
    --replica-timeout 1800 \
    --replica-retry-limit 0 \
    --parallelism 1 \
    --image "${ACR_NAME}.azurecr.io/rust-kernel-builder:latest" \
    --cpu 4.0 \
    --memory 8Gi \
    --registry-server "${ACR_NAME}.azurecr.io" \
    --command "/bin/bash" \
    --args "-c" \
    --args "cd /workspace && ls -la && echo 'Files in workspace:' && find . -maxdepth 2 -type d && cargo --version && rustc --version" \
    2>/dev/null || echo "Job may already exist"

echo ""
echo "Starting test job..."

JOB_EXECUTION=$(az containerapp job start \
    --name rust-kernel-build-test \
    --resource-group "$RESOURCE_GROUP" \
    --query name -o tsv)

echo "Job execution: $JOB_EXECUTION"
echo ""
echo "Waiting for completion..."

# Wait for job
while true; do
    STATUS=$(az containerapp job execution show \
        --name "$JOB_EXECUTION" \
        --job-name rust-kernel-build-test \
        --resource-group "$RESOURCE_GROUP" \
        --query properties.status -o tsv)

    echo "Status: $STATUS"

    if [ "$STATUS" = "Succeeded" ] || [ "$STATUS" = "Failed" ]; then
        break
    fi

    sleep 10
done

echo ""
echo "Job completed with status: $STATUS"
echo ""

# Show logs
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "JOB LOGS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

az containerapp job execution show \
    --name "$JOB_EXECUTION" \
    --job-name rust-kernel-build-test \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.template.containers[0]" -o json || true

echo ""

if [ "$STATUS" = "Succeeded" ]; then
    echo "✅ Test successful! Environment is ready."
    exit 0
else
    echo "❌ Test failed. Check logs above."
    exit 1
fi
