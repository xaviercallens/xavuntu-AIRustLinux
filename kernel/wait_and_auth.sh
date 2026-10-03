#!/bin/bash
PROJECT="gen-lang-client-0625573011"
ZONE="us-central1-a"
CLUSTER="mvk-benchmark"

echo "Waiting for cluster operations to complete..."
while true; do
  OPS=$(gcloud container operations list --project=$PROJECT --zone=$ZONE --filter="status=RUNNING AND clusterName=$CLUSTER" --format="value(name)" 2>/dev/null)
  if [ -z "$OPS" ]; then
    echo "No running operations. Proceeding..."
    break
  fi
  echo "Operations running: $OPS. Sleeping 10s..."
  sleep 10
done

MY_IP=$(curl -s ifconfig.me)
echo "Authorizing IP: $MY_IP"
gcloud container clusters update $CLUSTER \
    --zone=$ZONE \
    --project=$PROJECT \
    --enable-master-authorized-networks \
    --master-authorized-networks="$MY_IP/32"

export PATH="/opt/homebrew/share/google-cloud-sdk/bin:$PATH"
export USE_GKE_GCLOUD_AUTH_PLUGIN=True
gcloud container clusters get-credentials $CLUSTER --zone=$ZONE --project=$PROJECT
kubectl get nodes -o wide
