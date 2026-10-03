#!/bin/bash
# Deploy Qwen3.8-27B (UD-Q3_K_XL) to GCP Cloud Run Serverless with NVIDIA T4 GPU
# Features: min-instances 0 (scale-to-zero), HTTP auto-scaler, 16GB VRAM allocation

set -e

PROJECT_ID="${GCP_PROJECT_ID:-autoevolve-ai}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="qwen38-27b-t4-serverless"
IMAGE_TAG="us-central1-docker.pkg.dev/${PROJECT_ID}/llm-repo/qwen38-27b-t4:latest"

echo "=========================================================================="
echo "Deploying Qwen3.8-27B (UD-Q3_K_XL) to Cloud Run (NVIDIA T4 Serverless)"
echo "Project:      ${PROJECT_ID}"
echo "Region:       ${REGION}"
echo "Service:      ${SERVICE_NAME}"
echo "Image:        ${IMAGE_TAG}"
echo "=========================================================================="

# Build container via Cloud Build (or local docker push)
echo "Step 1: Submitting build to Google Cloud Build..."
gcloud builds submit \
    --project "${PROJECT_ID}" \
    --config - <<BUILD_YAML
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-t', '${IMAGE_TAG}', '-f', 'docker/Dockerfile.qwen38_t4', '.']
images:
- '${IMAGE_TAG}'
BUILD_YAML

# Deploy to Cloud Run with GPU (T4 / L4)
echo "Step 2: Deploying serverless service to Cloud Run..."
gcloud beta run deploy "${SERVICE_NAME}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --image "${IMAGE_TAG}" \
    --platform managed \
    --gpu 1 \
    --gpu-type nvidia-t4 \
    --cpu 8 \
    --memory 32Gi \
    --no-cpu-throttling \
    --min-instances 0 \
    --max-instances 4 \
    --concurrency 16 \
    --timeout 300 \
    --set-env-vars="CONTEXT_SIZE=8192,KV_CACHE_TYPE=q8_0,PARALLEL_SLOTS=2,ENABLE_VISION=false" \
    --allow-unauthenticated

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --platform managed --region "${REGION}" --project "${PROJECT_ID}" --format="value(status.url)")
echo "=========================================================================="
echo "Deployment Complete!"
echo "Service URL: ${SERVICE_URL}"
echo "Health Check: curl ${SERVICE_URL}/health"
echo "OpenAI API:   curl ${SERVICE_URL}/v1/chat/completions"
echo "=========================================================================="
