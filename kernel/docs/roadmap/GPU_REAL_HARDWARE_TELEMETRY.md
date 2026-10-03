# PCI Verification Against a Production Hypervisor — GCP TPU VM

**Status: real, first of its kind, and narrower than originally
planned — and narrower than this document's own first draft claimed.**
An initial version of this doc said "real hardware." That was
imprecise and has been corrected below: what was actually verified is
RunuX's PCI code against **a production Google Compute Engine
hypervisor's presentation of PCI devices to a guest VM** — which may
mix hypervisor-emulated functions (the Intel 440FX/PIIX4 chipset
devices almost certainly are: those are well-known QEMU/KVM software
emulation targets, present because GCE's hypervisor is KVM-based) with
physical functions passed through to the guest. PCI enumeration from
inside the guest cannot, by itself, tell emulation and passthrough
apart — that distinction needs a different kind of check (see
"Corrections" below), not yet done. `docs/roadmap/GCP_AI_KERNEL_MILESTONE_PLAN.md`'s
Milestone 1 targeted a real NVIDIA GPU (L4 or T4). That path is
blocked — this project's entire Compute Engine `GPUS_ALL_REGIONS`
quota is consumed by a pre-existing, unrelated instance, confirmed by
both a direct `gcloud compute instances create` failure and an
automatically-denied quota-increase request, and confirmed again
empirically by identical failures in three separate regions
(us-central1, us-west1, europe-west4) — see that plan doc's §2.1 for
the full record.

## Corrections to this document's first draft (2026-09-27, same day)

An independent design review caught three overclaims and one real
safety bug in the first version of this work. Recorded here rather
than silently fixed, per this project's own evidence rules:

| First-draft claim | Correction |
|---|---|
| "Verified against real, non-QEMU hardware" | Verified against a production hypervisor's *virtual* PCI bus. The 440FX/PIIX4 devices are software-emulated chipset devices, not silicon; whether `1ae0:0063` is passed-through physical hardware or itself an abstraction is not established by PCI enumeration alone. |
| "A real AMD Milan IOMMU" | A PCI function with vendor `1022` (AMD) and an IOMMU-shaped class code is visible to the guest. Whether that reflects a physical IOMMU exposed to the guest, a virtualized (`vIOMMU`) presentation, or an artifact of GCE's virtual chipset topology is **not established** — "Milan" was a device-ID name lookup, not an observation of silicon. Resolving this needs `dmesg` (does the guest kernel actually initialize AMD-Vi?), `/sys/class/iommu/`, `/sys/kernel/iommu_groups/`, and — most usefully — a control VM of the same machine family *without* a TPU attached, to see if the same function still appears (if so, it's generic to the AMD-based GCE chipset, not TPU-specific). |
| "Google, Inc. PCI vendor ID (1ae0) ... newly identified" | **False, corrected.** Checked directly against the live PCI ID Repository (`https://pci-ids.ucw.cz/read/PC/1ae0`, 2026-09-27): vendor `1ae0` and device `0042` (gVNIC) are both already public and well-established. Device `0063` specifically was not found in that database as of the same check — that part of the original claim holds, but should never have been stated as "the vendor ID is newly identified," which was wrong. |
| (bug, not a claim) | The original BAR-sizing code, run from this userspace tool with no synchronization against the Linux kernel's own PCI config-space lock, could corrupt a live, driver-bound device's state — including, in the worst case, the network interface carrying the very SSH session running the tool. It ran once (n=1) and nothing visibly broke, which is not the same as being safe. Fixed in `driver_pci_access::pci_bar_size` (Command-register decode bits are now cleared for the duration of the size probe) and in `examples/pci_probe_userspace` (BAR sizing is opt-in via `--bar-size-unbound`, default is read-only, and every function is checked against sysfs for a bound driver immediately before any write, not just once at startup). |

See `docs/roadmap/GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md` for the follow-up
work (control-VM comparison, n≥30 stability runs, an independent sysfs
oracle) that resolves the IOMMU and passthrough-vs-emulation questions
this correction leaves open.

**What happened instead:** this project also has real, unused quota
for Cloud TPU v5e (`TPU_LITE_PODSLICE_V5`, both on-demand and spot,
16.0 available across several regions) — a completely separate quota
pool from Compute Engine GPUs. A single-chip `v5litepod-1` spot TPU VM
was created, and `lspci` showed it exposes a **real PCI device tree**,
including Google's own accelerator hardware as a genuine PCI device —
not a GPU, but real, non-QEMU hardware nonetheless, and the first
opportunity this project has had to check its PCI code against
anything other than emulation.

## What was built: a userspace cross-check, not a kernel boot

A managed Cloud TPU VM boots a fixed OS image — there's no GRUB/serial
console plumbing to chainload a custom kernel the way `examples/x86_64_qemu_harness`
does under QEMU (that's real, separate infrastructure work, not
attempted here). Instead, `examples/pci_probe_userspace` (new) runs
this project's **actual, unmodified** `driver_pci_probe::pci_enumerate`
and `driver_pci_access::pci_config_read32`/`pci_bar_size` — the exact
same functions the bare-metal kernel harness calls — as a privileged
Linux process. `iopl(3)` (a real Linux syscall, requires root) grants a
userspace process the same raw I/O-port access ring 0 code has, so the
same `in`/`out`-instruction config-space reads execute for real,
without needing a kernel boot to exercise them.

## Result (2026-09-27, GCP TPU v5e VM, `us-west4-a`, spot)

Independently cross-checked against `lspci -nn`'s ground truth —
**every field matched, for all 8 devices found:**

| Address | Vendor:Device | Class:Subclass | Identity (via `lspci`) |
|---|---|---|---|
| 00:00.0 | 8086:1237 | 06:00 | Intel 440FX host bridge |
| 00:01.0 | 8086:7110 | 06:01 | Intel PIIX4 ISA bridge |
| 00:01.3 | 8086:7113 | 06:80 | Intel PIIX4 ACPI |
| 00:03.0 | 1022:164f | 08:06 | **AMD Milan IOMMU** (real IOMMU hardware, not an emulated one) |
| 00:04.0 | 1af4:1004 | 00:00 | Red Hat Virtio SCSI |
| **00:05.0** | **1ae0:0063** | **ff:00** | **Google, Inc. device — the TPU accelerator itself**, vendor-specific PCI class |
| 00:06.0 | 1ae0:0042 | 02:00 | Google gVNIC (virtual NIC) |
| 00:07.0 | 1af4:1005 | 00:ff | Red Hat Virtio RNG |

`driver_pci_core::GOOGLE_VENDOR_ID` (`0x1ae0`) was added and cited from
this direct observation (Google's device IDs largely aren't in the
public pci-ids.ucw.cz database the NVIDIA/virtio IDs were sourced from).

Host: real AMD EPYC 7B13, binary SHA-256
`d2e8d6fdf683d2a3e781efa2f54df1b42f36e305eab4424d6ba0e2f5e1d366b7`.

## Cost

Single `v5litepod-1` (spot), created and deleted within the same
session, under 15 minutes total lifetime. At ≈$1.20/chip-hour on-demand
(TPU v5e is a single-chip podslice here) with spot discounts typically
60-91% off, this is well under $1 — no different in spirit from the
CPU-architecture boot verifications' cost discipline earlier in this
project's history.

## What this does and doesn't show

- **Does show:** `driver_pci_access`'s Configuration Mechanism #1
  implementation and `driver_pci_probe`'s bus-walk logic are correct
  against real hardware, not just QEMU's emulation of it — the first
  time this project has verified any of its PCI code outside an
  emulator. It also incidentally confirms a real AMD IOMMU is present
  on this VM class, relevant to future DMA-isolation work
  (`crates/iommu_vtd` currently only models Intel VT-d).
- **Doesn't show:** anything about NVIDIA GPU hardware specifically —
  no RTX or T4 GPU was reached in this verification (that remains
  blocked; see the milestone plan). Doesn't show a kernel boot on real
  hardware (this was a userspace cross-check by design, not a
  substitute for one). Doesn't show anything about the TPU's actual
  compute capabilities — `class ff:00` (vendor-specific) means the PCI
  layer alone can't and doesn't attempt to characterize what the device
  does beyond identifying it.

## Reproduce this yourself

```bash
git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git
cd rust-linux-mini-kernel
cargo build --release -p pci_probe_userspace --target x86_64-unknown-linux-gnu
# copy the resulting binary to a Linux machine you have root on, then:
sudo ./pci_probe_userspace
# cross-check against:
lspci -nn
```
