# GCE/TPU PCI Topology Telemetry — Phase 1 (n=30, real hardware, controlled)

**Status: real, n=30, independently controlled.** This is the
follow-up to `GPU_REAL_HARDWARE_TELEMETRY.md`, addressing the
correction recorded there: a single observation (n=1, no control) is
not evidence of a stable, general result, and PCI enumeration alone
cannot distinguish hypervisor emulation from real hardware passthrough.
This campaign fixes both gaps.

## What changed since the first observation

1. **Fixed a real safety bug.** `driver_pci_access::pci_bar_size` now
   clears the Command register's I/O/memory decode bits for the
   duration of a BAR-size probe and restores them immediately after;
   `examples/pci_probe_userspace` now defaults to **read-only** mode
   (no BAR-sizing writes at all) and only performs sizing writes when
   explicitly asked *and* sysfs confirms no driver is bound to that
   function, re-checked immediately before every write. See
   `GPU_REAL_HARDWARE_TELEMETRY.md`'s corrections section for why the
   original code was unsafe (it could have corrupted the live network
   interface the SSH session itself depended on).
2. **Added an independent oracle.** `scripts/telemetry/pci_diff.py`
   never trusts RunuX's own self-reported match/mismatch fields --
   every comparison is re-derived from raw sysfs snapshot files
   (`vendor`, `device`, `class`, `config`) captured by
   `scripts/telemetry/pci_topology_run.sh` at the same time as each
   run. Validated against synthetic data before any real run: a clean
   fixture passes, and a deliberately corrupted fixture (one field
   flipped) is correctly caught and fails.
3. **Added a control.** A same-zone, same-CPU-family (`AMD EPYC 7B13`)
   `n2d-standard-2` VM with **no accelerator attached**, run through
   the identical campaign, to separate "true of any AMD-based GCE VM"
   from "specific to the TPU attachment."
4. **n=30 per environment**, not n=1.

## Campaign (2026-09-27, `us-west4-a`, both VMs spot, both deleted immediately after)

| | TPU VM (`v5litepod-1`) | Control VM (`n2d-standard-2`, no accelerator) |
|---|---|---|
| PCI devices found | 8 | 6 |
| Clean runs (sysfs identity match, all fields) | **30/30** | **30/30** |
| Config-space byte match vs. sysfs (every function, every run) | **True, 100%** | **True, 100%** |
| New `dmesg` warnings/errors after the run | 0 | 0 |
| Enumeration wall time (mean, n=30) | 59.868ms | 47.795ms |
| 95% CI | [59.742, 59.994]ms | [47.577, 48.013]ms |

Raw data: [`pci_telemetry/tpu_campaign_runs.csv`](pci_telemetry/tpu_campaign_runs.csv),
[`tpu_campaign_devices.csv`](pci_telemetry/tpu_campaign_devices.csv),
[`control_campaign_runs.csv`](pci_telemetry/control_campaign_runs.csv),
[`control_campaign_devices.csv`](pci_telemetry/control_campaign_devices.csv).

**On the timing difference:** the two CIs don't overlap, so it's a
real, repeatable difference between the two environments -- but this
enumeration does a flat, brute-force scan of all 256 buses regardless
of how many devices actually exist (documented limitation of
`driver_pci_probe::pci_enumerate`), so most of the ~48-60ms is scan
overhead, not per-device cost. A plausible explanation is that
VFIO-mediated config-space reads for the passed-through TPU function
(see below) trap through an extra hypervisor layer versus purely
emulated reads -- but that is a hypothesis, not something this
campaign measured directly. Treat this as a platform characterization,
not a performance claim about RunuX's code.

## The passthrough-vs-emulation question is now resolved

`GPU_REAL_HARDWARE_TELEMETRY.md`'s correction said this couldn't be
determined from PCI enumeration alone. It can't -- so this campaign
checked Linux's own view of the device instead:

```
$ readlink -f /sys/bus/pci/devices/0000:00:05.0/driver   # the 1ae0:0063 function
/sys/bus/pci/drivers/vfio-pci
```

**The TPU accelerator function is bound to `vfio-pci`** -- the standard
Linux driver used specifically for IOMMU-mediated PCI passthrough of a
physical device into a guest VM. This is concrete evidence (not an
inference from a device-ID name lookup) that `1ae0:0063` is a real,
physically passed-through function, not a hypervisor-software
emulation of one. The Intel 440FX/PIIX4 chipset devices, by contrast,
remain almost certainly pure KVM emulation (standard PC chipset
emulation, unrelated to any physical device).

## The IOMMU question is now resolved, with a proper control

| | TPU VM | Control VM (same CPU family, no accelerator) |
|---|---|---|
| `/sys/class/iommu/` | `ivhd0` (AMD-Vi IOMMU device) present | **empty** |
| `/sys/kernel/iommu_groups/` | group `0` present | **empty** |
| Any AMD-vendor (`1022`) PCI function at all | yes, `1022:164f`, class `0806` | **none** |
| `/dev/vfio/` | `/dev/vfio/0`, `/dev/vfio/vfio` present | not checked (no passthrough device to isolate) |

The control VM -- same host CPU family, same zone, same session, no
TPU -- has **zero** IOMMU-related devices, groups, or any AMD-vendor
PCI function whatsoever. This directly answers the open question from
the first observation: the AMD-Vi IOMMU is present on the TPU VM
*because* a physical device is being passed through and needs
IOMMU-mediated isolation, not because it's a generic feature of
AMD-based GCE instances. This is real IOMMU hardware doing real
DMA-isolation work for a real passed-through accelerator -- relevant,
concretely, to `crates/iommu_vtd`'s scope (currently Intel VT-d-only;
this is the first real evidence an AMD-Vi extension would apply to an
actual GCP workload, not a hypothetical one).

## What this does and doesn't show

- **Does show:** RunuX's real `driver_pci_access`/`driver_pci_probe`
  code reads PCI configuration space correctly -- every field, every
  byte, every function, across 30 independent runs on two different
  real environments -- checked against an oracle that never trusts the
  tool's own self-report. Does show the TPU accelerator is a genuine
  IOMMU-isolated hardware passthrough, not emulation, with a proper
  same-host-family control ruling out the alternative explanation.
  Does show the safety fix works: zero BAR-sizing writes occurred (the
  campaign ran in default read-only mode), zero new `dmesg`
  warnings/errors, zero lost SSH sessions, across both VMs.
- **Doesn't show:** anything about the TPU's actual compute
  capability, any NVIDIA GPU hardware (still unreached, see
  `GCP_AI_KERNEL_MILESTONE_PLAN.md`), a kernel boot on real hardware
  (this remains a userspace cross-check by design), or a performance
  claim about RunuX itself (the timing difference is a platform
  characteristic, not a benchmark result). Coverage is one zone, one
  TPU generation (v5e), one control machine type -- broader coverage
  (other zones, generations, machine families) is explicitly future
  work, not claimed here.

## Cost

Two spot VMs (`v5litepod-1` TPU + `n2d-standard-2` control), created
and deleted within roughly 15 minutes total combined lifetime, same
zone. Consistent with every other cloud-verification step this project
has taken (under $1-2 for the whole campaign at typical spot rates;
exact charge not yet confirmed against the billing report -- see
`GCP_AI_KERNEL_MILESTONE_PLAN.md`'s cost-estimate caveat, which applies
here too).

## Reproduce this yourself

```bash
git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git
cd rust-linux-mini-kernel
cargo build --release -p pci_probe_userspace --target x86_64-unknown-linux-gnu
# copy the binary + scripts/telemetry/pci_topology_run.sh to a VM you have root on:
sudo ./pci_topology_run.sh --binary ./pci_probe_userspace --iterations 30 --out campaign.tar.gz
# back on your workstation:
python3 scripts/telemetry/pci_diff.py campaign.tar.gz --out docs/roadmap/pci_telemetry/
```

## Next rounds (not yet done, scoped honestly)

- **Round 2 remaining:** an Intel-based control (in addition to the
  AMD one here) to separate CPU-vendor effects from accelerator
  effects entirely.
- **Round 3:** other TPU generations (v4, v5p, v6e) and multi-chip
  pod slices, other zones -- each bounded in cost, coverage itself is
  open-ended and quota-dependent (this project's GPU quota is already
  known to be exhausted; TPU quota availability elsewhere is
  unconfirmed).
- **Replay backend + CI fixtures: done, same day.** `driver_pci_core::PciConfigBackend`
  is a generic trait (`pci_enumerate` is now generic over it, no
  behavior change on the real hardware path -- re-verified against a
  real QEMU boot before and after the refactor) implemented by
  `driver_pci_access::HardwareIo` (real I/O ports) and by a test-only
  `ReplayBackend` in `crates/driver_pci_probe/tests/replay_gce_tpu_v5e.rs`
  that serves reads from `tests/fixtures/gce_tpu_v5e_us-west4-a_2026-09-27.txt`
  -- genuine captured config-space bytes from run 1 of this campaign,
  not a hand-written approximation. `cargo test -p driver_pci_probe`
  now re-verifies the exact real-hardware device list (all 8 devices,
  every vendor/device/class/subclass field) on every run, with no
  cloud access, and was confirmed to actually fail when the fixture is
  deliberately corrupted before being trusted.
- **Round 4 (separate track):** using this same trace-capture
  discipline to replay benign ML-workload syscall traces through
  `ebpf_firewall`/`ai_detector` offline and measure false-positive
  rate -- the highest-value, most open-ended direction identified
  during design review, intentionally not started in this pass.
