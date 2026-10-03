# GPU PCI Probe — Real Enumeration, Local QEMU Verification

**Status: real, reproducible, narrow.** This documents the first real
(non-mock) PCI config-space code in this repository, and its
verification against a real (if virtual) GPU-class PCI device. It is
**not** a claim of a working NVIDIA or AMD GPU driver, and no real
RTX/T4 hardware was used or reachable anywhere in this work.

## Why this exists

`docs/roadmap/STANDARD_HARDWARE_AI_GPU_PLAN.md` audited this project's
GPU-related crates and found `driver_pci_core`/`driver_pci_probe`/
`driver_pci_access` were pure mocks: `pci_read_config` unconditionally
set its output to `0`, with a comment reading `// Just a mock
implementation`. A from-scratch NVIDIA/AMD GPU driver is a multi-year
undertaking (see that plan's §2) and out of scope here — but genuine
PCI bus enumeration, config-space access, and BAR discovery are real,
bounded, and directly useful groundwork regardless of which GPU vendor
is eventually targeted. This is that work.

## What was built

- **`driver_pci_access`**: real x86 legacy PCI configuration-space I/O
  via ports `0xCF8`/`0xCFC` ("Configuration Mechanism #1"), including a
  BAR-size probe using the standard write-all-1s/read-back-mask/restore
  technique.
- **`driver_pci_core`**: `PciAddress`/`PciDeviceInfo` types populated by
  real enumeration (not stubs), plus a small table of real, individually
  cited NVIDIA PCI IDs (`KNOWN_NVIDIA_GPUS`) and the real QEMU/virtio-gpu
  ID, used only for human-readable identification — never to drive a
  device.
- **`driver_pci_probe`**: `pci_enumerate` — a real (flat, non-bridge-
  recursive) scan of all 256 buses × 32 devices × 8 functions, skipping
  absent slots (`vendor_id == 0xFFFF`) and correctly handling the
  multi-function bit to skip functions 1–7 when function 0 says the
  device isn't multi-function.
- **`examples/x86_64_qemu_harness`** now calls this real code at boot,
  printing every device found (bus:device.function, vendor:device,
  class:subclass) and, for any display-class device, its recognized
  name and BAR sizes.
- 7 new unit tests (`config_address` layout math, known-GPU recognition,
  display-class detection) — all passing, all host-testable without
  hardware.

## Real, cited PCI IDs

Individually verified against the PCI ID Repository
(<https://pci-ids.ucw.cz>), the canonical database `lspci`/`pciutils`
themselves query, as of 2026-09-27:

| Vendor:Device | Name | Source |
|---|---|---|
| `10de:1eb8` | NVIDIA TU104GL [Tesla T4] | <https://pci-ids.ucw.cz/read/PC/10de/1eb8> |
| `10de:2684` | NVIDIA AD102 [GeForce RTX 4090] | <https://pci-ids.ucw.cz/read/PC/10de/2684> |
| `1af4:1050` | Virtio 1.0 GPU (QEMU `virtio-gpu-pci`) | <https://www.qemu.org/docs/master/specs/pci-ids.html> |

The NVIDIA IDs are wired into the recognition table and unit-tested,
but this environment has no reachable RTX or T4 GPU (`nvidia-smi` is
not installed, no `/dev/nvidia*` device nodes exist) — they have never
been exercised against real NVIDIA hardware. Only the virtio-gpu ID has
been proven against a real device below.

## Verification (local QEMU, 2026-09-27)

Two oracles, both checked-in scripts, both re-run before this write-up:

1. **`scripts/x86_64_boot_test.sh`** (no GPU attached) — enumeration
   correctly finds exactly the 4 devices QEMU's default `i440fx`
   chipset provides and correctly reports none of them as display
   controllers:

   ```
   00:00.0 vendor=8086 device=1237 class=06 subclass=00   (Intel 440FX host bridge)
   00:01.0 vendor=8086 device=7000 class=06 subclass=01   (PIIX3 ISA bridge)
   00:01.1 vendor=8086 device=7010 class=01 subclass=01   (PIIX3 IDE)
   00:01.3 vendor=8086 device=7113 class=06 subclass=80   (PIIX4 ACPI)
   ```

   Every ID above matches well-known, independently verifiable QEMU
   `i440fx` machine defaults — this is a real cross-check that the
   enumeration logic is correct, not just "didn't crash."

2. **`scripts/x86_64_gpu_probe_test.sh`** (new; boots the same kernel
   with `-device virtio-gpu-pci` attached) — the enumeration finds a
   5th device and correctly identifies it:

   ```
   00:02.0 vendor=1af4 device=1050 class=03 subclass=80 -- QEMU virtio-gpu (virtio 1.0)
       BAR1 size=0x00001000 bytes
       BAR4 size=0x00004000 bytes
       BAR5 size=0x00000010 bytes
   [PASS] At least one display/GPU-class PCI device was enumerated for real
   ```

   `PASS` in both cases; QEMU exits cleanly (code 1, the isa-debug-exit
   success sentinel) either way.

## What this does and doesn't show

- **Does show:** genuine PCI config-space reads/writes against real
  (QEMU-emulated) hardware correctly enumerate a bus, correctly
  identify a real device by its real PCI vendor/device ID, and
  correctly compute real BAR sizes — verified against ground truth
  (well-known QEMU chipset device IDs) rather than only checked for
  "didn't crash."
- **Doesn't show:** a working GPU driver of any kind. No command
  submission, no VRAM mapping, no IOMMU-gated DMA, no fence/ring-buffer
  path. `driver_pci_access::pci_bar_size` also only handles 32-bit BARs
  correctly (a true 64-bit memory BAR needs both dwords combined — see
  the doc comment on that function); the bus scan is flat, not a real
  recursive PCI-PCI bridge walk; there is no MSI/MSI-X or PCIe
  extended-capability parsing, and no MMCONFIG/ECAM for the 4KiB
  extended config space. **No real NVIDIA GPU (RTX or T4) was used,
  reachable, or tested against anywhere in this work.**

## Reproduce this yourself

```bash
git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git
cd rust-linux-mini-kernel
sudo apt-get install -y qemu-system-x86 grub-pc-bin grub-common xorriso mtools
bash scripts/x86_64_boot_test.sh              # enumeration against QEMU's default chipset only
bash scripts/x86_64_gpu_probe_test.sh          # enumeration with a real virtio-gpu-pci device attached
cargo test -p driver_pci_core -p driver_pci_access
```
