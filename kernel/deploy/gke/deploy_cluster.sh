#!/bin/bash
# ============================================================
# GKE Deployment Script for MVK Benchmark Cluster
# Project: SocrateAI (gen-lang-client-0625573011)
# ============================================================
# Usage:
#   ./deploy/gke/deploy_cluster.sh                 # Deploy
#   ./deploy/gke/deploy_cluster.sh --teardown      # Destroy
# ============================================================

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-gen-lang-client-0625573011}"
REGION="us-central1"
ZONE="us-central1-a"
CLUSTER_NAME="mvk-benchmark"
BENCHMARK_MACHINE_TYPE="n2-standard-8"
CONTROL_MACHINE_TYPE="n2-standard-4"
BENCHMARK_NODES=3
USE_SPOT="${USE_SPOT:-true}"

log() { echo "[$(date -u '+%H:%M:%S')] $*"; }

# ============================================================
# Deploy
# ============================================================
deploy() {
    log "╔══════════════════════════════════════════════════════════╗"
    log "║  Deploying MVK Benchmark Cluster on GKE                 ║"
    log "║  Project: $PROJECT_ID                                   ║"
    log "╚══════════════════════════════════════════════════════════╝"

    # --- Step 1: Create VPC ---
    log "Step 1/6: Creating VPC network..."
    gcloud compute networks create ${CLUSTER_NAME}-vpc \
        --project="$PROJECT_ID" \
        --subnet-mode=custom \
        2>/dev/null || log "  VPC already exists, continuing..."

    gcloud compute networks subnets create ${CLUSTER_NAME}-subnet \
        --project="$PROJECT_ID" \
        --network=${CLUSTER_NAME}-vpc \
        --region="$REGION" \
        --range=10.0.0.0/20 \
        --secondary-range=pods=10.4.0.0/14,services=10.8.0.0/20 \
        2>/dev/null || log "  Subnet already exists, continuing..."

    # --- Step 2: Create GKE Cluster ---
    log "Step 2/6: Creating GKE Standard cluster (this takes 5-10 minutes)..."
    gcloud container clusters create "$CLUSTER_NAME" \
        --project="$PROJECT_ID" \
        --zone="$ZONE" \
        --network="${CLUSTER_NAME}-vpc" \
        --subnetwork="${CLUSTER_NAME}-subnet" \
        --cluster-secondary-range-name=pods \
        --services-secondary-range-name=services \
        --enable-ip-alias \
        --release-channel=None \
        --num-nodes=1 \
        --machine-type=e2-small \
        --no-enable-autoupgrade \
        --enable-managed-prometheus \
        || log "  Cluster already exists, continuing..."

    # --- Step 3: Create Benchmark Node Pool ---
    log "Step 3/6: Creating benchmark node pool ($BENCHMARK_NODES × $BENCHMARK_MACHINE_TYPE)..."
    
    local spot_flag=""
    if [ "$USE_SPOT" = "true" ]; then
        spot_flag="--spot"
        log "  Using Spot VMs for ~60% cost savings"
    fi

    gcloud container node-pools create benchmark-nodes \
        --project="$PROJECT_ID" \
        --cluster="$CLUSTER_NAME" \
        --zone="$ZONE" \
        --machine-type="$BENCHMARK_MACHINE_TYPE" \
        --num-nodes="$BENCHMARK_NODES" \
        --image-type=UBUNTU_CONTAINERD \
        --enable-nested-virtualization \
        --disk-size=100 \
        --disk-type=pd-ssd \
        --node-labels=role=benchmark,app=mvk-kernel \
        --node-taints=benchmark=true:NoSchedule \
        $spot_flag \
        --no-enable-autoupgrade \
        2>/dev/null || log "  Benchmark node pool already exists, continuing..."

    # --- Step 4: Create Control Node Pool ---
    log "Step 4/6: Creating control node pool (1 × $CONTROL_MACHINE_TYPE)..."
    gcloud container node-pools create control-nodes \
        --project="$PROJECT_ID" \
        --cluster="$CLUSTER_NAME" \
        --zone="$ZONE" \
        --machine-type="$CONTROL_MACHINE_TYPE" \
        --num-nodes=1 \
        --image-type=UBUNTU_CONTAINERD \
        --disk-size=50 \
        --disk-type=pd-ssd \
        --node-labels=role=control \
        $spot_flag \
        --no-enable-autoupgrade \
        2>/dev/null || log "  Control node pool already exists, continuing..."

    # --- Step 5: Get Credentials ---
    log "Step 5/6: Getting cluster credentials..."
    gcloud container clusters get-credentials "$CLUSTER_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT_ID"

    # --- Step 6: Delete default pool ---
    log "Step 6/6: Removing default node pool..."
    gcloud container node-pools delete default-pool \
        --cluster="$CLUSTER_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT_ID" \
        --quiet 2>/dev/null || log "  Default pool already removed."

    # --- Verify ---
    log ""
    log "════════════════════════════════════════════════"
    log "  ✅ GKE Cluster Deployed!"
    log "════════════════════════════════════════════════"
    log ""
    kubectl get nodes -o wide
    log ""
    log "Next steps:"
    log "  1. Install Chaos Mesh:  helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-mesh --create-namespace"
    log "  2. Build images:        docker build -t gcr.io/$PROJECT_ID/mvk-kernel:9.4.0 -f deploy/docker/Dockerfile.mvk-kernel ."
    log "  3. Run tests:           python3 deploy/scripts/run_gke_tests.py --skip-infra --full-suite"
}

# ============================================================
# Teardown
# ============================================================
teardown() {
    log "╔══════════════════════════════════════════════════════════╗"
    log "║  Tearing Down MVK Benchmark Cluster                     ║"
    log "╚══════════════════════════════════════════════════════════╝"

    log "Deleting GKE cluster..."
    gcloud container clusters delete "$CLUSTER_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT_ID" \
        --quiet 2>/dev/null || log "  Cluster not found."

    log "Deleting VPC subnet..."
    gcloud compute networks subnets delete ${CLUSTER_NAME}-subnet \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --quiet 2>/dev/null || log "  Subnet not found."

    log "Deleting VPC network..."
    # Delete firewall rules first
    for rule in $(gcloud compute firewall-rules list --filter="network:${CLUSTER_NAME}-vpc" --format="value(name)" --project="$PROJECT_ID" 2>/dev/null); do
        gcloud compute firewall-rules delete "$rule" --project="$PROJECT_ID" --quiet 2>/dev/null
    done
    gcloud compute networks delete ${CLUSTER_NAME}-vpc \
        --project="$PROJECT_ID" \
        --quiet 2>/dev/null || log "  VPC not found."

    log "✅ All resources destroyed."
}

# ============================================================
# Main
# ============================================================
if [ "${1:-}" = "--teardown" ]; then
    teardown
else
    deploy
fi
