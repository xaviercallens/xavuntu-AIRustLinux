# Benign ML Workload Syscall Traces — Collection Phase (M4, Round 1 of 2)

**Status: real, n=10 per workload, collection only.** This is the
first half of Candidate C / Milestone 4 from
`TPU_ACCELERATOR_IMPROVEMENT_PLAN.md`: "record syscall traces from
real, benign ML jobs on a TPU VM." It does **not** include the second,
larger half of M4 (replaying these traces through `ebpf_firewall`/
`ai_detector` and measuring false-positive rate) -- that remains
separate, unstarted, open-ended work, exactly as scoped in the design
doc. Nothing in this document should be read as a claim about how the
defense stack performs; it's ground-truth data collection to make that
future evaluation possible.

## What was captured

Two representative benign ML workloads, run under `strace -f -tt`
(full syscall trace with timestamps) on a real GCP Cloud TPU v5e VM
(`v5litepod-1`, spot, `us-west4-a`, 2026-09-27), n=10 independent runs
each:

1. **`device_enum`** ([`ml_workload_device_enum.py`](ml_workload_traces/ml_workload_device_enum.py)):
   `import jax; print(jax.devices())` -- the lightest-weight real
   interaction with the TPU: JAX startup, runtime initialization,
   device discovery via `libtpu`. JAX was not preinstalled on this
   runtime image (`v2-alpha-tpuv5-lite`) and was installed fresh
   (`pip install "jax[tpu]"`) before capture -- a real, disclosed step,
   not assumed to already be present.
2. **`matmul_512x512`** ([`ml_workload_matmul.py`](ml_workload_traces/ml_workload_matmul.py)):
   a 512x512 random matrix multiply via `jnp.dot`, forced to complete
   with `.block_until_ready()` -- exercises actual TPU compute
   dispatch through JAX/XLA, not just device enumeration.

`jax.devices()` confirmed a real `TpuDevice` was recognized
(`[TpuDevice(id=0, process_index=0, coords=(0,0,0), core_on_chip=0)]`)
-- this is exactly the software boundary
`TPU_ACCELERATOR_IMPROVEMENT_PLAN.md` describes: Google's own stack
can drive the TPU; RunuX cannot and does not attempt to here.

## Results

| Workload | n | Mean syscalls/run | Stdev | Mean unique syscalls | Stable set (present in every run) | Mean wall time |
|---|---|---|---|---|---|---|
| `device_enum` | 10 | 35,174 | 309 (0.9%) | 84.5 | 84 | 6.002s |
| `matmul_512x512` | 10 | 59,023 | 535 (0.9%) | 84.8 | 84 | 7.880s |

Full data: [`ml_workload_traces/workload_summary.csv`](ml_workload_traces/workload_summary.csv),
[`ml_workload_traces/syscall_frequency.csv`](ml_workload_traces/syscall_frequency.csv).

**Both workloads are remarkably stable run-to-run** (~0.9% coefficient
of variation in total syscall count; only 1-2 syscall *names* vary
across the full set of 10 runs each, out of 84-85 present). This
matters for any future anomaly-detection evaluation: a benign workload
this consistent gives a classifier a real, learnable baseline to work
against, rather than inherent noise that would be indistinguishable
from an actual anomaly.

**A real connection to the earlier PCI/passthrough finding:** `ioctl`
(6,460-6,610 calls across the 10-run set) and `mmap` (7,795-8,811
calls) are both among the most frequent syscalls in every run. This is
consistent with -- not proof of, but consistent with --
`GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md`'s finding that the TPU accelerator
is `vfio-pci`-bound: VFIO's userspace API is `ioctl`-driven (DMA-buf
mapping, IOMMU group operations, device reset) and backed by `mmap`
for the actual MMIO BAR mapping into the process. The two pieces of
telemetry -- PCI topology and syscall behavior -- corroborate each
other without either one proving the other.

`rt_sigprocmask` dominates by raw count (119K-318K calls) but this is
very likely generic Python/threading-runtime signal-mask housekeeping,
not TPU-specific -- flagged here rather than left to imply otherwise.

## What this does and doesn't show

- **Does show:** two real benign ML workloads on real TPU hardware
  produce a stable, characterizable syscall profile -- real data any
  future firewall/classifier evaluation can be built against, rather
  than synthetic or assumed traffic patterns.
- **Doesn't show:** anything about `ebpf_firewall` or `ai_detector`'s
  actual false-positive rate on this traffic -- that replay and
  measurement step has not been done. Doesn't show anything about
  malicious/anomalous traffic (no attack traces were captured or
  synthesized in this pass). Doesn't show broader workload coverage
  (only two small, single-process, single-host JAX programs; no
  multi-host, no real training job, no checkpointing). Doesn't
  characterize per-syscall *arguments* (paths, sizes, targets) -- only
  syscall names and counts, deliberately, to keep the committed
  summary data small and free of local file paths.

## Data handling

Raw `strace` output (~9.5MB compressed, tens of thousands of lines per
run) was captured, analyzed, and **not committed** -- only the
aggregate summary CSVs above are checked in, consistent with keeping
telemetry data structured and small (the `boot_telemetry/*.csv`
precedent). The raw traces were reviewed for anything sensitive before
being discarded from the working environment; the summary CSVs contain
only syscall names and counts, no arguments, paths, or identifiers.

## Cost

One spot `v5litepod-1` TPU VM, created, used for JAX install + 20
total workload runs under `strace`, and deleted within roughly 20
minutes total lifetime. Consistent with every other bounded campaign
this project has run on GCP this session.

## Reproduce this yourself

```bash
# On a TPU VM (or any machine with TPU access):
pip install "jax[tpu]" -f https://storage.googleapis.com/jax-releases/libtpu_releases.html
bash docs/roadmap/ml_workload_traces/capture_traces.sh   # produces ~/ml_traces.tar.gz

# Back on your workstation, after extracting the tarball:
python3 scripts/telemetry/ml_trace_analyze.py ~/ml_traces \
  --workloads device_enum:device_enum:device_enum_timing.csv \
              matmul_512x512:matmul:matmul_timing.csv \
  --out docs/roadmap/ml_workload_traces
```

## Next round (M4, part 2) -- done, see `ML_WORKLOAD_FIREWALL_REPLAY.md`

**Update, same session:** the replay-harness engineering was done.
`examples/firewall_replay` replays these exact 620,934 real events
through the real, unmodified `ebpf_firewall::evaluate_syscall` and
`ai_detector::evaluate_pid_event`. The rule-based firewall layer is
clean and fully explicable (0.0032% flagged, always the same real
`memfd_create("xla-jit-exec")` JIT-compilation call). The classifier
layer's result is more significant than a false-positive-rate number:
its weights have no evident training provenance anywhere in this
repository, and its erratic behavior on real, identical-workload
traffic is consistent with an untrained/arbitrary weight matrix, not a
fitted model responding to real signal. Full write-up:
`ML_WORKLOAD_FIREWALL_REPLAY.md`.
