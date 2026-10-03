#!/bin/bash
set -ex

gcloud container clusters create mvk-benchmark \
  --project=gen-lang-client-0625573011 \
  --zone=us-central1-a \
  --network=mvk-benchmark-vpc \
  --subnetwork=mvk-benchmark-subnet \
  --cluster-secondary-range-name=pods \
  --services-secondary-range-name=services \
  --enable-dataplane-v2 \
  --release-channel=regular \
  --enable-managed-prometheus \
  --enable-ip-alias \
  --machine-type=e2-micro \
  --num-nodes=1

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
  --advanced-machine-features=enable-nested-virtualization=true \
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

gcloud container clusters get-credentials mvk-benchmark --zone us-central1-a --project gen-lang-client-0625573011
