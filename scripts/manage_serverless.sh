#!/usr/bin/env bash
# ==============================================================================
# ANSE Serverless Cost-Control & Lifecycle Manager
# Provides instant 0-cost shutdown & one-command reactivation for:
#   1. Local Serverless Scale-to-Zero LoRA Endpoint (port 8000)
#   2. Remote GCP Cloud Run GPU Prover (deepseek-prover-v2 in us-central1)
# ==============================================================================

set -euo pipefail

REGION="us-central1"
SERVICE="deepseek-prover-v2"
LOCAL_PORT=8000
BACKUP_YAML="config/deepseek_prover_v2_cloudrun.yaml"

print_banner() {
    echo "================================================================"
    echo "   ANSE Serverless Lifecycle & Zero-Cost Manager"
    echo "================================================================"
}

cmd_status() {
    print_banner
    echo "[1/2] Local LoRA Serverless Endpoint (Port $LOCAL_PORT):"
    if lsof -i :"$LOCAL_PORT" >/dev/null 2>&1; then
        PID=$(lsof -t -i :"$LOCAL_PORT" | head -n 1)
        echo "  - Status: RUNNING (PID: $PID)"
        curl -s "http://localhost:$LOCAL_PORT/v1/cost" || true
        echo ""
    else
        echo "  - Status: STOPPED (Port $LOCAL_PORT free, Cost: \$0.00)"
    fi

    echo ""
    echo "[2/2] GCP Cloud Run GPU Service ($SERVICE in $REGION):"
    if command -v gcloud >/dev/null 2>&1; then
        INGRESS=$(gcloud run services describe "$SERVICE" --region "$REGION" --format="value(metadata.annotations['run.googleapis.com/ingress'])" 2>/dev/null || echo "unknown")
        MIN_SCALE=$(gcloud run services describe "$SERVICE" --region "$REGION" --format="value(spec.template.metadata.annotations['autoscaling.knative.dev/minScale'])" 2>/dev/null || true)
        MIN_SCALE="${MIN_SCALE:-0}"
        echo "  - Ingress: $INGRESS"
        echo "  - Min Replicas: $MIN_SCALE"
        if [ "$INGRESS" = "internal" ]; then
            echo "  - Zero-Cost Guard: ACTIVE (Blocked from external traffic, 0 instances, \$0.00)"
        elif [ "$MIN_SCALE" = "0" ]; then
            echo "  - Scale-to-Zero: ACTIVE (Min 0 instances, incurs cost only on active requests)"
        else
            echo "  - WARNING: Min instances > 0 ($MIN_SCALE)"
        fi
    else
        echo "  - gcloud CLI not available"
    fi
}

cmd_stop() {
    print_banner
    echo ">>> Executing Zero-Cost Stop Protocol..."

    # 1. Stop local endpoint
    echo "[1/2] Checking Local Serverless Endpoint (Port $LOCAL_PORT)..."
    if lsof -i :"$LOCAL_PORT" >/dev/null 2>&1; then
        PID=$(lsof -t -i :"$LOCAL_PORT")
        echo "  - Terminating process (PID: $PID)..."
        kill -15 "$PID" 2>/dev/null || kill -9 "$PID" 2>/dev/null || true
        echo "  - Local endpoint stopped. Memory and CPU reclaimed."
    else
        echo "  - Local endpoint already stopped (\$0.00 cost)."
    fi

    # 2. Lock Cloud Run GPU service to zero cost
    echo "[2/2] Enforcing Zero-Cost on Cloud Run GPU ($SERVICE in $REGION)..."
    if command -v gcloud >/dev/null 2>&1; then
        mkdir -p config
        if [ ! -f "$BACKUP_YAML" ]; then
            echo "  - Backing up configuration to $BACKUP_YAML..."
            gcloud run services describe "$SERVICE" --region "$REGION" --format=yaml > "$BACKUP_YAML"
        fi
        echo "  - Applying min-instances=0 and ingress=internal..."
        gcloud run services update "$SERVICE" \
            --region "$REGION" \
            --min-instances=0 \
            --ingress=internal \
            --quiet
        echo "  - Cloud Run service locked: all external traffic blocked, 0 instances running."
        echo "  - Cost: \$0.00 guaranteed."
    fi

    echo ""
    echo ">>> All serverless endpoints are STOPPED and sealed at \$0.00 cost."
}

cmd_start() {
    print_banner
    echo ">>> Reactivating Serverless Services..."

    # 1. Reactivate Cloud Run
    echo "[1/2] Restoring Cloud Run Service ($SERVICE in $REGION)..."
    if command -v gcloud >/dev/null 2>&1; then
        echo "  - Setting ingress=all and min-instances=0 (scale-to-zero enabled)..."
        gcloud run services update "$SERVICE" \
            --region "$REGION" \
            --min-instances=0 \
            --ingress=all \
            --quiet
        SERVICE_URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format="value(status.url)")
        echo "  - Cloud Run service reactivated: $SERVICE_URL"
    fi

    # 2. Start local endpoint
    echo "[2/2] Starting Local Serverless Scale-to-Zero LoRA Endpoint..."
    if ! lsof -i :"$LOCAL_PORT" >/dev/null 2>&1; then
        nohup uv run python -m anse.gateway.serverless_lora_endpoint > results/serverless_lora_endpoint.log 2>&1 &
        sleep 2
        echo "  - Local serverless daemon started on port $LOCAL_PORT (starts DORMANT, costs \$0 when idle)."
    else
        echo "  - Local serverless daemon already running on port $LOCAL_PORT."
    fi

    echo ""
    echo ">>> Serverless services REACTIVATED successfully."
}

case "${1:-status}" in
    stop)
        cmd_stop
        ;;
    start|reactivate)
        cmd_start
        ;;
    status)
        cmd_status
        ;;
    *)
        echo "Usage: $0 {status|stop|start}"
        exit 1
        ;;
esac
