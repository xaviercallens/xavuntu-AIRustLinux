#!/bin/bash
set -ex

gcloud container node-pools create benchmark-nodes \
  --cluster=mvk-benchmark \
  --zone=us-central1-a \
  --project=gen-lang-client-0625573011 \
  --machine-type=n2-standard-8 \
  --num-nodes=3 \
  --spot \
  --disk-size=100GB \
  --disk-type=pd-ssd \
  --image-type=UBUNTU_CONTAINERD \
  --enable-nested-virtualization \
  --node-labels=role=benchmark,app=mvk-kernel \
  --node-taints=benchmark=true:NoSchedule \
  --scopes=https://www.googleapis.com/auth/cloud-platform

gcloud container node-pools create control-nodes \
  --cluster=mvk-benchmark \
  --zone=us-central1-a \
  --project=gen-lang-client-0625573011 \
  --machine-type=n2d-standard-4 \
  --num-nodes=1 \
  --spot \
  --disk-size=50GB \
  --disk-type=pd-ssd \
  --image-type=UBUNTU_CONTAINERD \
  --node-labels=role=control \
  --scopes=https://www.googleapis.com/auth/cloud-platform

gcloud container node-pools delete default-pool --cluster=mvk-benchmark --zone=us-central1-a --project=gen-lang-client-0625573011 --quiet

kubectl get nodes
