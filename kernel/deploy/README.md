# GKE Multi-Pod Deployment: MVK Rust Kernel

Deploy the MVK Rust kernel across multiple GKE pods for performance testing, chaos engineering, and Rust vs C comparison.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  GKE Standard Cluster (us-central1)                          │
│                                                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ MVK Kernel 1 │ │ MVK Kernel 2 │ │ C Baseline   │           │
│  │ (server)     │ │ (client)     │ │ (server)     │           │
│  │ QEMU+iperf3  │ │ QEMU+bench   │ │ QEMU+iperf3  │           │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘           │
│         │    pod-to-pod    │                │                  │
│         └────────┬─────────┘                │                  │
│                  │                          │                  │
│  ┌───────────────┴──────────────────────────┘                │
│  │                                                            │
│  │  ┌─────────────┐ ┌─────────────┐                          │
│  │  │ Chaos Mesh   │ │ Prometheus   │                          │
│  │  │ Controller   │ │ + Grafana    │                          │
│  │  └──────────────┘ └──────────────┘                          │
│  │  (control-plane node pool)                                │
│  └───────────────────────────────────────────────────────────┘
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- GCP project with billing enabled
- `gcloud`, `terraform`, `helm`, `kubectl` installed
- Docker for building images

### 1. Deploy Everything (one command)

```bash
export GCP_PROJECT_ID=your-project-id

python3 deploy/scripts/run_gke_tests.py \
    --project-id $GCP_PROJECT_ID \
    --full-suite
```

### 2. Step-by-Step

```bash
# Step 1: Provision GKE cluster (Terraform)
cd deploy/gke
terraform init
terraform apply -var="project_id=$GCP_PROJECT_ID"

# Step 2: Get credentials
gcloud container clusters get-credentials mvk-benchmark \
    --zone us-central1-a --project $GCP_PROJECT_ID

# Step 3: Install Chaos Mesh
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm install chaos-mesh chaos-mesh/chaos-mesh \
    --namespace chaos-mesh --create-namespace \
    --set chaosDaemon.runtime=containerd

# Step 4: Build and push images
docker build -t gcr.io/$GCP_PROJECT_ID/mvk-kernel:9.4.0 \
    -f deploy/docker/Dockerfile.mvk-kernel .
docker push gcr.io/$GCP_PROJECT_ID/mvk-kernel:9.4.0

# Step 5: Deploy benchmark pods
helm install mvk-benchmark deploy/helm/mvk-benchmark \
    --set image.repository=gcr.io/$GCP_PROJECT_ID/mvk-kernel

# Step 6: Run tests
python3 deploy/scripts/run_gke_tests.py --skip-infra --full-suite
```

### 3. Teardown

```bash
python3 deploy/scripts/run_gke_tests.py \
    --project-id $GCP_PROJECT_ID \
    --teardown
```

## Test Matrix

| Phase | Tests | Duration | Tools |
|-------|-------|----------|-------|
| 1. Baseline | Boot time, CPU, memory, TCP/UDP, CRC32 | ~5 min | sysbench, iperf3, netperf |
| 2. Under Load | Performance at 75% CPU, 80% memory | ~5 min | stress-ng + iperf3 |
| 3. Chaos | 6 fault scenarios | ~10 min | Chaos Mesh |
| 4. Comparison | Rust vs C head-to-head | ~2 min | Automated report |
| **Total** | | **~22 min** | |

## Cost

| Configuration | Cost/Run | Cost/Day (8hr) |
|---------------|----------|----------------|
| Spot VMs (default) | ~$3 | ~$5 |
| On-demand VMs | ~$7 | ~$11 |

## Chaos Experiments

| # | Experiment | What It Tests | Success = |
|---|-----------|---------------|-----------|
| 3.1 | Network Partition | TCP recovery | No panic |
| 3.2 | Network Delay (100ms±50ms) | Congestion control | No data loss |
| 3.3 | Packet Loss (10%) | Retransmission | TCP recovers |
| 3.4 | CPU Stress (100%) | Scheduler resilience | No deadlock |
| 3.5 | Memory Pressure (80%) | OOM handling | Graceful OOM |
| 3.6 | Pod Kill | Boot recovery | Restarts cleanly |

## References

- [k8s-netperf](https://github.com/cloud-bulldozer/k8s-netperf) — K8s network benchmark framework
- [Chaos Mesh](https://chaos-mesh.org/) — CNCF chaos engineering platform
- Android Binder Rust Driver Benchmark (Google, 2025) — ±2% methodology
- CVE-2025-68260 — Rust Binder FFI race condition (Kangrejos 2025)
- gVisor vs Kata performance study (Semantic Scholar, 2024)
