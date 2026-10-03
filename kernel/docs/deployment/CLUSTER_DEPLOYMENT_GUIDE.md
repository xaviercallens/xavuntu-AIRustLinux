# Rust MVK Routing Cluster Deployment & Telemetry Guide

This guide details the deployment of the **Rust Linux Minimum Viable Kernel (MVK)** stubs into a virtualized multi-node routing cluster, alongside continuous integration and telemetric crash monitoring.

---

## 1. Virtual Cluster Architecture

The test environment simulates a three-tier routing topology with:
1. **Edge Routers (Ingress/Egress)**: Running MVK stubs for multicast snooping and FOU6 (Generic UDP Encapsulation for IPv6).
2. **Core Router**: Running Netfilter NAT and IP routing stubs.
3. **Mock Telemetry Scraper**: Standard service scraping logs, looking for kernel memory leaks, KASAN alerts, or scheduler starvation events.

```
                  ┌───────────────┐
                  │ Ingress Edge  │ (MVK FOU6 / Multicast)
                  └───────┬───────┘
                          │
                  ┌───────▼───────┐
                  │ Core Router   │ (MVK Netfilter / CFS)
                  └───────┬───────┘
                          │
                  ┌───────▼───────┐
                  │ Egress Edge   │ (MVK FOU6 / Multicast)
                  └───────────────┘
```

---

## 2. Docker Compose Virtual Router Cluster

We use a standard container-based simulation where nodes communicate on a dedicated virtual network.

To start the cluster:
```bash
docker-compose -f docker-compose.cluster.yml up -d
```

This starts:
- `mvk-router-ingress` (Edge Node)
- `mvk-router-core` (Core NAT Node)
- `mvk-router-egress` (Edge Node)
- `mvk-telemetry-collector` (Prometheus/Grafana telemetry stub)

---

## 3. KASAN/UBSAN Telemetry & Panic Scraping

Kernel Address Sanitizer (KASAN) and Undefined Behavior Sanitizer (UBSAN) outputs are printed to the kernel ring buffer (`dmesg`) or standard log files.

The script `scripts/kasan_monitor.sh` runs as a sidecar agent on each node:
1. Scrapes log files or standard system output.
2. Identifies sanitization events (e.g., use-after-free, out-of-bounds array indexing, null pointer dereferences).
3. Translates events into prometheus metric gauges or logs them to a centralized collector.

### Continuous Telemetry Execution

Run the scraper script:
```bash
./scripts/kasan_monitor.sh --log-file /var/log/syslog --interval 5
```

This registers standard alerting hooks for immediate routing updates in case of subsystem crashes.
