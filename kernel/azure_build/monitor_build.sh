#!/bin/bash
#
# Monitor Azure Container Registry build status
#

set -euo pipefail

REGISTRY="${REGISTRY:-rustkernel64044}"
RUN_ID="${1:-}"

if [ -z "$RUN_ID" ]; then
    echo "Getting latest build..."
    RUN_ID=$(az acr task list-runs --registry "$REGISTRY" --output tsv --query "[0].runId")
fi

echo "Monitoring build: $RUN_ID"
echo ""

while true; do
    STATUS=$(az acr task list-runs --registry "$REGISTRY" --run-id "$RUN_ID" --query "[0].status" -o tsv)
    echo "$(date '+%H:%M:%S') - Status: $STATUS"

    if [ "$STATUS" = "Succeeded" ] || [ "$STATUS" = "Failed" ] || [ "$STATUS" = "Canceled" ]; then
        break
    fi

    sleep 15
done

echo ""
echo "Build completed with status: $STATUS"

if [ "$STATUS" = "Succeeded" ]; then
    echo "✅ Docker image ready!"
    exit 0
else
    echo "❌ Build failed. View logs with:"
    echo "   az acr task logs --registry $REGISTRY --run-id $RUN_ID"
    exit 1
fi
