# RunuX on Standard Hardware for AI/GPU Workloads — Improvement Plan

**Status:** PLAN ONLY. Nothing in this document has been implemented.
**Baseline:** `v11.3.0` / commit `ea0c906`.
**Execution model:** same as `RUNUX_V12_VERIFIED_CORE_PLAN.md` and
`AI_AGENT_DEFENSE_PLAN.md` — a unit list meant to run through `Workflow`
with low-tier models (Haiku for mechanical/plumbing work, Sonnet for
driver-level design and anything touching memory-safety boundaries), gated
by an oracle, not by agent self-report. No agent should be launched from
this document without a human reading it first.

---

## 1. What "standard hardware" actually requires, and what exists today

"Standard hardware" here means a generic x86_64 or ARM64 server with a
PCIe-attached GPU (NVIDIA, AMD, or a virtualized `virtio-gpu`) — not a
cloud-simulated TPU, not a specific vendor's proprietary cloud SKU, and not
RISC-V edge silicon. Measured against the repository as of this plan:

| Layer needed | What exists | Gap |
|---|---|---|
| PCIe enumeration (bus/device/function scan, config space, BAR discovery) | **Update (2026-09-27):** real config-space I/O via Configuration Mechanism #1 (ports 0xCF8/0xCFC), a real flat bus/device/function scan, and real BAR-size probing (write-all-1s technique) are now implemented in `driver_pci_access`/`driver_pci_probe` and exercised at boot by `examples/x86_64_qemu_harness`. Verified against a real (if virtual) GPU-class PCI device -- QEMU's `virtio-gpu-pci` (1af4:1050) -- correctly enumerated, identified by vendor/device ID, and BAR-sized; see [`scripts/x86_64_gpu_probe_test.sh`](../../scripts/x86_64_gpu_probe_test.sh) and [`GPU_PCI_PROBE_TELEMETRY.md`](GPU_PCI_PROBE_TELEMETRY.md). Real NVIDIA PCI IDs (10de:1eb8 Tesla T4, 10de:2684 RTX 4090, cited from pci-ids.ucw.cz) are wired into the same recognition table, unit-tested, but never run against real NVIDIA hardware -- no RTX/T4 GPU was reachable from the environment this was built in | Still a flat 256-bus scan, not a recursive PCI-PCI bridge walk; only 32-bit BAR sizing (a true 64-bit memory BAR needs both dwords combined); no MSI/MSI-X or PCIe extended-capability walk; no MMCONFIG/ECAM for the 4KiB extended config space; still QEMU-only, no real silicon of any vendor |
| IOMMU-mediated safe DMA | `crates/iommu_vtd` (311 LOC) | Intel VT-d—specific naming and structures exist; no AMD-Vi / ARM SMMU path, and no test exercising an actual two-stage page table walk |
| GPU memory/BAR types | `crates/gpu_types` (339 LOC), `crates/gpu_memory` (160 LOC) | These are `#[repr(C)]` struct definitions (e.g. `PciBarConfig`) matching `specs/lean4/MVK/Phase13/GpuCompute.lean` (9 theorems, 1 axiom, 0 sorry) — a real, closed proof exists for the *types*, not for a driver that uses them against hardware |
| GPU submission/scheduling | `crates/gpu_scheduler` (117 LOC), `crates/gpu_ioctl` (119 LOC) | Named after an ioctl-style interface; no ring-buffer submission path, no fence/sync primitive wired to any real command queue |
| Storage-to-GPU DMA | `crates/gpu_gds` (95 LOC) | Modeled specifically on **NVIDIA GPUDirect Storage** — a proprietary, vendor-specific technology. There is no vendor-neutral path (no `virtio-gpu`, no generic DMA-buf equivalent) |
| Boot on real hardware | `examples/demo_kernel` (i686) boots under QEMU; `examples/riscv_qemu_harness` boots real `arch/riscv64` workspace code via OpenSBI in QEMU ([`scripts/riscv_boot_test.sh`](../../scripts/riscv_boot_test.sh)); `examples/x86_64_qemu_harness` boots into genuine 64-bit long mode via GRUB Multiboot2, exercising real `kernel_types` logic ([`scripts/x86_64_boot_test.sh`](../../scripts/x86_64_boot_test.sh)); `examples/aarch64_qemu_harness` boots on `qemu-system-aarch64 virt` via a new `arch/aarch64` (real EL descent, PSCI shutdown, `kernel_types` exercised) ([`scripts/aarch64_boot_test.sh`](../../scripts/aarch64_boot_test.sh)) — the "ARM64 server" side of this plan's own target now has a real boot path to build on | No UEFI entry (Multiboot2/GRUB only) for a real x86_64 server; no evidence any translated crate has run on physical hardware (QEMU only, for all three architectures); no IDT/APIC/real drivers on x86_64, no real GIC/pgtables on aarch64 yet |

**Conclusion:** the type layer and the formal model for GPU compute are real and further along than most of this project's other claims — `GpuCompute.lean` is one of the few *fully closed* non-Core-Defenses proof files. What's missing is everything between "correct types" and "a GPU actually does work": real PCIe bus walking, a real IOMMU page-table implementation, and a vendor-neutral first target instead of NVIDIA-only GDS.

## 2. Why start with `virtio-gpu`, not real NVIDIA/AMD silicon

Writing a from-scratch NVIDIA or AMD GPU driver in Rust is a multi-year effort even for a well-resourced team (see: `nouveau`, `amdgpu`'s Rust-port discussions upstream). Given this project's own v12 audit found that most of its "advanced hardware" claims (TPU v5e, SpacemiT K1) were never run against real hardware at all, repeating that mistake at GPU scale would be the same failure mode again, just bigger. The pragmatic path:

1. **`virtio-gpu`** under QEMU is a real, standard, vendor-neutral device with a public, stable spec (VIRTIO 1.2 §5.7). It exercises the *entire* stack this plan cares about — PCIe enumeration, BAR mapping, IOMMU-safe DMA, command submission, fencing — without requiring proprietary NVIDIA/AMD register documentation or hardware access this project doesn't have evidence of possessing.
2. It runs in the same QEMU environment already used for the demo-kernel boot harness, so "does it actually work" is checkable in CI, not asserted.
3. It generalizes: a driver architecture that correctly does PCIe probe → IOMMU-safe DMA → virtqueue submission → fence wait is structurally the same shape a later real-silicon driver would need, so this is not throwaway work.

Real NVIDIA/AMD hardware support becomes Phase 3 (§5), explicitly gated on Phase 1–2 succeeding on `virtio-gpu` first, and on the project actually having physical hardware to test against — not simulated.

## 3. Security goals for this hardware surface

A GPU is a DMA-capable device with its own firmware and its own memory; it is one of the largest attack surfaces a kernel exposes, and it intersects directly with `AI_AGENT_DEFENSE_PLAN.md`'s threat model (an AI workload's tensors/weights flow through exactly this path). Goals, each with a metric:

| ID | Goal | Metric |
|---|---|---|
| H1 | No GPU DMA write can target kernel memory outside its assigned IOMMU domain | Lean proof: for any DMA descriptor accepted by the driver, its target range is a subset of the IOMMU-mapped range granted to that device (mirrors REQ-RCD-022's existing DMA non-overlap theorem, extended to IOMMU-mediated GPU DMA specifically) |
| H2 | A malformed/malicious command buffer cannot crash or hang the kernel | Fuzz target (`fuzz_gpu_commands`) with zero panics/hangs over a sustained run, mirroring `fuzz_packet`/`fuzz_routing`'s existing harness pattern |
| H3 | GPU firmware/VRAM contents from one workload cannot leak to the next (multi-tenant AI inference is the primary use case) | Explicit VRAM zeroization on context teardown, proven in Lean analogous to REQ-RCD-019's `kv_cache_zeroize_prevents_leakage` |
| H4 | The AI-agent-speed threat model (`AI_AGENT_DEFENSE_PLAN.md` D1–D2) extends to the GPU submission path | Load-test the command-submission oracle at agent-plausible rates, reusing that plan's `load_bench` unit type once it exists |
| H5 | Real PCIe/IOMMU code has documented `unsafe` at the rate this project committed to for its core set (`RUNUX_V12_VERIFIED_CORE_PLAN.md` goal G7: 100% `SAFETY:` coverage in the core set) | New driver crates are added to the "core set" from day one — no `unsafe` merges without a `SAFETY:` comment, checked the same way `check_unit.py`'s `unsafe_safety` unit type already checks it |

## 4. Proposed new requirements (REQ-HW-\* series)

| ID | Title | Crate(s) | Depends on |
|---|---|---|---|
| REQ-HW-001 | Real PCIe config-space read/write (type 0/1 headers) and capability-list walk (MSI-X, PCIe extended caps) over I/O-port and ECAM/MMIO config access | `driver_pci_core`, `driver_pci_probe` | — |
| REQ-HW-002 | BAR size/type probing (32-bit, 64-bit, prefetchable) using the standard write-all-1s-and-read-back algorithm, safely wrapped (no raw pointer arithmetic outside an audited `unsafe` block) | `driver_pci_core` | REQ-HW-001 |
| REQ-HW-003 | IOMMU page-table setup for a PCI device's DMA domain — start with a software/identity-mapped fallback verified safe, then the real VT-d 2-level page table walk | `iommu_vtd` (new: `iommu_generic` trait so AMD-Vi/SMMU can implement the same interface later) | REQ-HW-001, REQ-HW-002 |
| REQ-HW-004 | `virtio-gpu` PCI device binding: recognize the device, negotiate VIRTIO features, set up the control virtqueue | New crate `driver_virtio_gpu` | REQ-HW-001–003 |
| REQ-HW-005 | Command submission + fence wait over the control virtqueue (2D/3D command buffer path per VIRTIO 1.2 §5.7.6) | `driver_virtio_gpu`, `gpu_scheduler` | REQ-HW-004 |
| REQ-HW-006 | VRAM zeroization on context/resource teardown, proven in Lean (H3) | `gpu_memory` | REQ-HW-005 |
| REQ-HW-007 | `fuzz_gpu_commands` fuzz target against the command-buffer parser (H2) | `fuzz/` | REQ-HW-005 |
| REQ-HW-008 | Real x86_64 boot (UEFI or Multiboot2) linking the actual workspace crates — not the `examples/demo_kernel` stand-in — with `driver_virtio_gpu` as the first "real workload" proof point | New `kernel_image` crate (already scoped in `RUNUX_V12_VERIFIED_CORE_PLAN.md` WS5) | REQ-HW-001–007, and WS5 |
| REQ-HW-009 | Vendor-neutral GPU trait (`GpuDevice`) that `driver_virtio_gpu` implements, so a later real-silicon driver (AMD via `amdgpu`-equivalent, or NVIDIA via open kernel modules) has a defined interface to target instead of a rewrite | `gpu_types` | REQ-HW-004 |

## 5. Phased sequencing

| Phase | Scope | Exit criterion |
|---|---|---|
| **P1 — PCIe/IOMMU foundation** | REQ-HW-001, 002, 003 (software-mapped fallback only) | A real PCIe device (any device, not necessarily a GPU — the existing `driver_nvme`/`driver_idpf` crates can validate this first, cheaper than GPU work) is enumerated and its BARs mapped in QEMU, with an IOMMU domain assigned, checked in CI |
| **P2 — `virtio-gpu` end-to-end** | REQ-HW-004, 005, 006, 007, 009 | A command buffer submitted through the full stack produces a fence completion in QEMU; `fuzz_gpu_commands` runs clean; VRAM zeroization proven in Lean |
| **P3 — Real boot + hardening** | REQ-HW-008, plus H4/H5 from §3 | Boots on real x86_64 (UEFI), not just QEMU; `AI_AGENT_DEFENSE_PLAN.md`'s load-test harness (once built) run against the GPU submission path |
| **P4 — Real silicon (explicitly out of scope for now)** | AMD/NVIDIA driver work against `GpuDevice` (REQ-HW-009) | Not started until P1–P3 are done *and* the project has verified access to real, non-simulated hardware to test against — do not repeat the TPU/K1 simulation-presented-as-measurement mistake this audit already found once |

## 6. Workflow decomposition (low-tier-model execution, for later)

Following the same generator/oracle pattern as `RUNUX_V12_VERIFIED_CORE_PLAN.md` §4 and `AI_AGENT_DEFENSE_PLAN.md` §5:

| Unit type | One unit per… | Oracle | Tier |
|---|---|---|---|
| `pci_config_field` | one PCI config-space field/capability to implement read/write for (vendor ID, BAR N, MSI-X table pointer, …) | Unit test against a QEMU-emulated PCI device with a known-good config space (compare read value to `lspci -xxx` ground truth captured once, checked in) | T1 |
| `bar_probe_case` | one BAR type (32-bit, 64-bit, prefetchable, I/O-space) | Unit test with synthetic BAR values exercising the write-1s-read-back algorithm | T1 |
| `iommu_domain_case` | one IOMMU domain-setup scenario (identity map, single-device isolation, multi-device isolation) | `cargo test` + a Lean lemma stub for the isolation property, escalated to T2 if the Lean side doesn't close in 3 attempts (same escalation rule as the Lean pilot, corrected per `RESEARCH_DIRECTIONS.md` A3: only escalate if something actually failed) | T1→T2 |
| `virtqueue_op` | one virtio-gpu control-queue command (`RESOURCE_CREATE_2D`, `SET_SCANOUT`, `TRANSFER_TO_HOST_2D`, …) | Round-trip test against a QEMU `virtio-gpu` device: issue the command, assert the fence completes and the expected side effect is observed | T2 (protocol-level judgment; not mechanical) |
| `gpu_fuzz_seed` | one fuzz corpus seed / crash-triage case for REQ-HW-007 | `cargo fuzz run` reproduces zero crashes on the seed corpus; any new crash becomes a `bug_fix` unit, not silently marked fixed | T1 for seed generation, T2/human for triage |

Any unit that would change a safety-relevant boundary — what a DMA descriptor is allowed to target, what an IOMMU domain is allowed to map, whether VRAM zeroization can be skipped — requires human/T3 sign-off before merge, identical to the rule already established in `AI_AGENT_DEFENSE_PLAN.md` §5 for security thresholds. This is not a new rule; it is the same rule applied to a new subsystem.

## 7. What this plan deliberately does not claim

- It does not claim RunuX currently runs on any real GPU or any real standard-hardware server. It claims the type layer and formal model for GPU compute are further along than most of this project's other subsystems, and specifies the concrete, checkable steps to close the gap between "correct types" and "a GPU does work."
- It does not propose starting with real NVIDIA/AMD silicon, because this project has a documented pattern (TPU v5e, SpacemiT K1) of presenting simulated results as hardware measurements, and repeating that pattern at GPU scale would compound the problem this whole audit cycle exists to fix.
- It does not propose abandoning the existing `gpu_gds`/NVIDIA-specific work — it proposes making it one implementation of a vendor-neutral trait (REQ-HW-009) instead of the only path, once that trait exists.
