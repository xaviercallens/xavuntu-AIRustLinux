#!/bin/bash
PROJECT_ID="gen-lang-client-0625573011"
IMAGE="gcr.io/$PROJECT_ID/rust-linux-mini-kernel:gamma"

echo "Creating Cloud Run Job..."
gcloud run jobs create gamma-benchmark \
    --image $IMAGE \
    --region us-central1 \
    --project $PROJECT_ID \
    --command="/usr/local/bin/benchmark_suite.sh"

echo "Executing Cloud Run Job..."
gcloud run jobs execute gamma-benchmark \
    --region us-central1 \
    --project $PROJECT_ID \
    --wait
