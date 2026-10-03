# RunuX — A Rust Reimplementation of Linux Kernel Subsystems

**A `#[no_std]` Rust kernel and Linux-subsystem reimplementation with Lean 4 formal verification — real boots on x86_64, RISC-V (riscv64gc), and AArch64 under QEMU and on real Google Cloud VMs, an eBPF-style syscall firewall, and real PCIe/IOMMU probing on Google Cloud TPU/accelerator hardware.**

[![CI — Runtime & Integration](https://github.com/xaviercallens/rust-linux-mini-kernel/actions/workflows/runtime_tests.yml/badge.svg)](https://github.com/xaviercallens/rust-linux-mini-kernel/actions/workflows/runtime_tests.yml)
[![CI — RISC-V Cross-Compilation](https://github.com/xaviercallens/rust-linux-mini-kernel/actions/workflows/riscv64_tests.yml/badge.svg)](https://github.com/xaviercallens/rust-linux-mini-kernel/actions/workflows/riscv64_tests.yml)
[![CI — Security Audit](https://github.com/xaviercallens/rust-linux-mini-kernel/actions/workflows/security_audit.yml/badge.svg)](https://github.com/xaviercallens/rust-linux-mini-kernel/actions/workflows/security_audit.yml)
[![CI — Lean 4 Verification](https://github.com/xaviercallens/rust-linux-mini-kernel/actions/workflows/verify-specs.yml/badge.svg)](https://github.com/xaviercallens/rust-linux-mini-kernel/actions/workflows/verify-specs.yml)
[![Metrics Ratchet](https://github.com/xaviercallens/rust-linux-mini-kernel/actions/workflows/metrics-ratchet.yml/badge.svg)](docs/roadmap/metrics/metrics.baseline.json)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)
[![Version](https://img.shields.io/badge/version-11.3.8-green)](https://github.com/xaviercallens/rust-linux-mini-kernel/releases)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22985926.svg)](https://doi.org/10.5281/zenodo.22985926)
[![Contributors welcome](https://img.shields.io/badge/contributors-welcome-brightgreen)](CONTRIBUTING.md)
[![Agent-ready issues](https://img.shields.io/github/issues/xaviercallens/rust-linux-mini-kernel/agent-ready?label=agent-ready%20issues)](https://github.com/xaviercallens/rust-linux-mini-kernel/issues?q=is%3Aopen+label%3Aagent-ready)

> **Author:** Xavier Callens
> **Latest Release:** v11.3.8 — September 27, 2026 — real AArch64 boot, the third architecture from scratch, independently verified on GCP
> **Status:** actively audited. See [Measured Status](#measured-status-2026-09-26) below for numbers generated from the tree, not asserted by hand.
> **Reproducible boot images** (RISC-V ELF, x86_64 GRUB Multiboot2 ISO, AArch64 ELF — the same binaries attached to the releases below, re-verified before upload, checksummed): public, no-account-needed mirror at
> [`gs://socrateai-datalake-gen-lang-client-0625573011/runux-boot-images/`](https://storage.googleapis.com/socrateai-datalake-gen-lang-client-0625573011/runux-boot-images/README.md) — see that `README.md` for `qemu-system-*` commands to boot each one yourself.

---

## Try it in 60 seconds: boot RunuX on three CPU architectures

No Rust toolchain, no build, no account. Download a prebuilt image from the public mirror and boot it under QEMU (`sudo apt install qemu-system-x86 qemu-system-arm qemu-system-misc` on Debian/Ubuntu):

```bash
B=https://storage.googleapis.com/socrateai-datalake-gen-lang-client-0625573011/runux-boot-images
curl -O $B/runux-riscv64-qemu-harness-v11.3.4 -O $B/runux-aarch64-qemu-harness-v11.3.7 \
     -O $B/runux-x86_64-v11.3.6-grub-multiboot2.iso -O $B/SHA256SUMS
sha256sum -c SHA256SUMS --ignore-missing

# RISC-V: OpenSBI -> S-mode -> RunuX
qemu-system-riscv64 -machine virt -nographic -bios default -kernel runux-riscv64-qemu-harness-v11.3.4
# AArch64: EL2 -> EL1 descent -> RunuX, clean PSCI shutdown
qemu-system-aarch64 -machine virt -cpu cortex-a72 -nographic -nic none -kernel runux-aarch64-qemu-harness-v11.3.7
# x86_64: GRUB Multiboot2 -> real 64-bit long-mode switch -> RunuX (Ctrl-A X to quit if it doesn't self-exit)
qemu-system-x86_64 -cdrom runux-x86_64-v11.3.6-grub-multiboot2.iso -nographic -vga none -nic none \
  -device isa-debug-exit,iobase=0xf4,iosize=0x04 -no-reboot
```

Each prints `[SUCCESS] RunuX <arch> booted successfully inside QEMU`. What this is and isn't: a boot harness that runs a small slice of real crate code (`kernel_types::SafePageFrame` on x86_64/AArch64) — not a usable OS; it has no scheduler, drivers, or userspace. See [Measured Status](#measured-status-2026-09-26) for exactly what's verified.

---

## 🤝 Call for contributors — humans and AI agents

This project is too large and too important for one person. We are asking for help from the **Rust community**, **Lean provers**, **kernel and security engineers**, and **people running AI coding agents** (Claude Code, Google Jules, others) on four goals:

- **Memory-safe infrastructure you can prove:** every `unsafe` block justified, and every theorem honest about what it proves.
- **Certified software, not claimed software:** a Lean 4 proof or a script behind every number.
- **Efficient AI through verifiable output:** agents whose work passes an oracle they don't control, so nobody has to redo it.
- **Systems that hold up against AI-assisted attacks:** defenses measured against adaptive, machine-speed attackers.

**How:** read the [roadmap](ROADMAP.md), pick an [`agent-ready`](https://github.com/xaviercallens/rust-linux-mini-kernel/issues?q=is%3Aopen+label%3Aagent-ready) or [`good first issue`](https://github.com/xaviercallens/rust-linux-mini-kernel/issues?q=is%3Aopen+label%3A%22good+first+issue%22), and follow [CONTRIBUTING.md](CONTRIBUTING.md) (humans) or [AGENTS.md](AGENTS.md) (AI agents). Pull requests from forks are welcome. Every PR runs an anti-hallucination guard ([`scripts/pr_guard.py`](scripts/pr_guard.py)) and the metrics ratchet. Maintainers can hand issues to Claude (`@claude` or the `agent:claude` label) or Jules (`agent:jules`). Found a number with no evidence behind it? Open a *Claim verification* issue. Security issues: [SECURITY.md](SECURITY.md).

---

## What this project actually is

RunuX is a Cargo workspace of Rust crates that reimplement pieces of Linux kernel subsystems — mostly networking (IPv4/IPv6, Netfilter/NAT, connection tracking, tunneling) — behind `#[repr(C)]` FFI types intended to be binary-compatible with the corresponding Linux 5.10 structures. A separate Lean 4 specification tree models correctness properties for parts of the design, most completely a Ring 0 syscall-interception model (`RunuxDefenses.lean`, fully closed). An experimental AI/Edge-inference layer targets simulated RISC-V and TPU hardware.

This README used to make several claims that didn't hold up when measured — "297/297 modules, zero warnings," "92 Lean 4 theorems, zero sorry," and demo GIFs captioned as live captures that were in fact hand-drawn animations. Those have been corrected below. The audit that found this, the tooling that measures it continuously, and the improvement plans that follow from it are all in this repository — see [Measured Status](#measured-status-2026-09-26) and [`docs/roadmap/`](docs/roadmap/).

---

## Measured Status (2026-09-26)

Every number below is produced by `scripts/metrics.py measure` (static analysis, no build required) or by `specs/scripts/verify_specs.sh` (real `lake env lean` type-checking). Re-run either yourself; nothing here is asserted by hand.

| Metric | Measured | Detail |
|---|---|---|
| Crates in the workspace | 316 | 141 of these are ≤25-line placeholders (`fn *_init() -> 0`), not implemented subsystems. Triage proposal: [`docs/roadmap/placeholder_triage.csv`](docs/roadmap/placeholder_triage.csv) |
| Compiler warnings | 0 (`cargo check`) | Achieved via `#[allow(clippy::all, ...)]` in 284 of 316 crates, not by resolving lints |
| Lean 4 specification tree | 37 files, 434 theorems, 138 axioms | See breakdown below |
| Lean 4 open proof obligations (`sorry`) | 245 | Down from 249 at the start of this audit cycle; 2 more theorems were proved **false as stated** rather than fixed — see [`specs/lean4/MVK/Audit/SpecDefects.lean`](specs/lean4/MVK/Audit/SpecDefects.lean) |
| Fully closed proof model | `RunuxDefenses.lean` — 84 theorems, 0 axioms, 0 `sorry` | Ring 0 pre-dispatch interception, W^X enforcement, Merkle audit log, LMS policy state machine. This is real and complete; it does not (yet) extend to the other 36 files |
| `unsafe` blocks / documented | 722 / 111 (15%) | Up from 101 (14%) after Wave 1 hardened 4 of 8 core crates (#59, #61-#63). `crates/ai_detector::activation_slice` has a known aliasing issue (`&self -> &mut`), not yet fixed |
| `static mut` (workspace) | 193 | Down from 197 after Wave 1 removed 4 sites (`syscall_table`, `netfilter`, `kernel_types`×2) |
| Tests | 335 `#[test]`, in 74 of 316 crates | 2 fuzz targets |
| PCIe/GPU enumeration | `driver_pci_access`/`driver_pci_probe`/`driver_pci_core` now do real config-space I/O (ports 0xCF8/0xCFC), real bus enumeration, and real BAR-size probing — no longer mocks. Verified against a real (virtual) GPU-class device, QEMU's `virtio-gpu-pci` (1af4:1050), correctly identified by vendor/device ID with real BAR sizes read out — [`scripts/x86_64_gpu_probe_test.sh`](scripts/x86_64_gpu_probe_test.sh), [`docs/roadmap/GPU_PCI_PROBE_TELEMETRY.md`](docs/roadmap/GPU_PCI_PROBE_TELEMETRY.md). Also verified against a real, non-QEMU **production hypervisor** (GCP), n=30 with an independent sysfs oracle and a same-CPU-family control VM: 100% config-byte match on every device across both environments, and — resolved with concrete evidence, not inference — the Google accelerator function is `vfio-pci`-bound (real IOMMU-mediated hardware passthrough) with a real AMD-Vi IOMMU present only on the accelerator-attached VM, absent on the control — [`docs/roadmap/GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md`](docs/roadmap/GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md), design rationale in [`docs/roadmap/TPU_ACCELERATOR_IMPROVEMENT_PLAN.md`](docs/roadmap/TPU_ACCELERATOR_IMPROVEMENT_PLAN.md). An independent review of the first pass at this (`docs/roadmap/GPU_REAL_HARDWARE_TELEMETRY.md`) caught real overclaims and a real safety bug (unsynchronized BAR-sizing writes from userspace could have corrupted the live NIC carrying the SSH session) — both corrected; the tool now defaults to read-only | No real NVIDIA GPU (RTX or T4) reachable or tested anywhere in this work — GCP's entire Compute Engine GPU quota for this project is consumed by a pre-existing unrelated instance (confirmed, see [`docs/roadmap/GCP_AI_KERNEL_MILESTONE_PLAN.md`](docs/roadmap/GCP_AI_KERNEL_MILESTONE_PLAN.md)); real PCI IDs for Tesla T4/RTX 4090 are wired into the recognition table and unit-tested only. Flat bus scan (no bridge recursion); 32-bit BARs only; no MSI/MSI-X, no MMCONFIG/ECAM. No command submission, VRAM mapping, or driver of any kind — and, per the design doc, none is realistically achievable for TPU hardware at all |
| Google Cloud TPU accelerator investigation (M0-M5) | Full writeup and Opus-tier design review: [`docs/roadmap/TPU_ACCELERATOR_IMPROVEMENT_PLAN.md`](docs/roadmap/TPU_ACCELERATOR_IMPROVEMENT_PLAN.md). Real, verified work: (M1) real ML workload (JAX on `v5litepod-1`) syscall traces captured with `strace -f -tt -i` and an authoritative `/usr/include/.../unistd_64.h`-derived syscall table — [`docs/roadmap/ML_WORKLOAD_SYSCALL_TRACES.md`](docs/roadmap/ML_WORKLOAD_SYSCALL_TRACES.md); (M4) those real traces replayed through this repo's own unmodified `ebpf_firewall::evaluate_syscall` and `ai_detector::evaluate_pid_event` — [`docs/roadmap/ML_WORKLOAD_FIREWALL_REPLAY.md`](docs/roadmap/ML_WORKLOAD_FIREWALL_REPLAY.md), finding the classifier's weights are untrained (not a tuning gap); (M5) a real, reproducible recipe for turning this project's boot image into a bootable Google Compute Engine custom disk image, reaching real SeaBIOS firmware execution on real GCE hardware — [`docs/roadmap/M5_GCE_CUSTOM_BOOT_ATTEMPT.md`](docs/roadmap/M5_GCE_CUSTOM_BOOT_ATTEMPT.md) | **Doesn't show:** a working RunuX boot on real cloud hardware past firmware (Google's SeaBIOS fork, `1.8.2-google`, doesn't get further than GRUB's first multi-sector read — root cause narrowed, not fixed). GPU quota (T4/L4/RTX-class) for this project was found fully exhausted project-wide (`GPUS_ALL_REGIONS`) before any real NVIDIA GPU could be reached — see [`docs/roadmap/GCP_AI_KERNEL_MILESTONE_PLAN.md`](docs/roadmap/GCP_AI_KERNEL_MILESTONE_PLAN.md); this is why the accelerator work above used Cloud TPU instead |
| Boot testing | (1) `examples/demo_kernel` i686 binary boots under QEMU (no long mode, no real crates linked). (2) `examples/riscv_qemu_harness` boots via OpenSBI→S-mode on `qemu-system-riscv64 -machine virt` ([`scripts/riscv_boot_test.sh`](scripts/riscv_boot_test.sh)), independently re-verified on a fresh GCP VM, 30/30 boots (mean 0.0617s, 95% CI [0.0611s, 0.0622s]) — [`docs/roadmap/RISCV_BOOT_TELEMETRY.md`](docs/roadmap/RISCV_BOOT_TELEMETRY.md). (3) `examples/x86_64_qemu_harness` boots real **64-bit long mode** via GRUB Multiboot2 on `qemu-system-x86_64` — genuine PAE/EFER.LME/CR0.PG mode switch (not the demo_kernel trick), and the first workspace boot path to actually call into a real crate (`kernel_types::SafePageFrame::new`, both the valid-pointer and null-rejection paths) rather than only print banners — verified by [`scripts/x86_64_boot_test.sh`](scripts/x86_64_boot_test.sh), independently re-verified on a fresh GCP VM, 30/30 boots (mean 0.5518s, 95% CI [0.5026s, 0.6010s], TCG software emulation, no KVM on this VM tier) — [`docs/roadmap/X86_64_BOOT_TELEMETRY.md`](docs/roadmap/X86_64_BOOT_TELEMETRY.md). (4) `examples/aarch64_qemu_harness` boots on `qemu-system-aarch64 -machine virt` — a from-scratch `arch/aarch64` (no prior AArch64 code existed in this repo), real EL3/EL2→EL1 exception-level descent, PL011 UART, and a clean PSCI `SYSTEM_OFF` shutdown (exit 0); also exercises real `kernel_types::SafePageFrame` logic like the x86_64 harness — verified by [`scripts/aarch64_boot_test.sh`](scripts/aarch64_boot_test.sh), independently re-verified on a fresh GCP VM, 30/30 boots (mean 0.0392s, 95% CI [0.0388s, 0.0395s], TCG cross-emulation, no native ARM hardware used) — [`docs/roadmap/AARCH64_BOOT_TELEMETRY.md`](docs/roadmap/AARCH64_BOOT_TELEMETRY.md) | All three real-boot harnesses exercise only a small, deliberately-chosen slice of real workspace code (page-table CSR setup / `SafePageFrame`), not full subsystem init — RISC-V's `riscv_arch_init`/`riscv_irq_init`/`riscv_pgtable_init` and AArch64's `aarch64_arch_init`/`aarch64_irq_init`/`aarch64_pgtable_init` still print and return, and none of the three harnesses has a scheduler, drivers, filesystem, or userspace, so no Linux performance/feature comparison is made or implied. See [Roadmap](#roadmap) |

**Wave 1 progress (hardening the 8-crate core-set gap):** 4/8 crates done — `syscall_table` ([#59](https://github.com/xaviercallens/rust-linux-mini-kernel/pull/59)), `netfilter` ([#61](https://github.com/xaviercallens/rust-linux-mini-kernel/pull/61), 1 block honestly left unjustified, tracked in [#64](https://github.com/xaviercallens/rust-linux-mini-kernel/issues/64)), `kernel_types` ([#63](https://github.com/xaviercallens/rust-linux-mini-kernel/pull/63)), `immutable_logs` ([#62](https://github.com/xaviercallens/rust-linux-mini-kernel/pull/62)). Every PR was independently rebuilt, retested, and checked for downstream FFI-symbol breakage before merging — not just trusted from the agent's report. Remaining: `ai_bridge` (19 sites), `page_alloc` (33), `slab` (45) — deliberately not yet run; real cost per crate in the first 4 was higher than estimated (582,912 tokens for 15 sites), and the remaining 3 are much larger files. `vmalloc` (1 site) is blocked on a real, separately-discovered bug: its test calls undefined functions ([#60](https://github.com/xaviercallens/rust-linux-mini-kernel/issues/60)).

**Full detail, per-file breakdown, and the methodology:** [`docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md`](docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md) (section 0, "Baseline: measured vs. claimed") and [`docs/roadmap/PAPER_VERIFICATION_TODO.md`](docs/roadmap/PAPER_VERIFICATION_TODO.md) (which papers' claims survived a reproducibility check, and which didn't).

### What is solid

- The FFI struct layer (`kernel_types`) and the core-set crates (`ebpf_firewall`, `ai_bridge`, `immutable_logs`, `slab`, `page_alloc`, `ai_detector`) are substantial (700–1,550 LOC each) and tested.
- `RunuxDefenses.lean`'s 84 theorems are genuinely fully closed — zero `sorry`, zero axioms.
- RISC-V cross-compilation (`riscv64gc-unknown-none-elf`) genuinely works for the workspace crates that exist.
- The metrics ratchet and oracle-gated proof-completion workflow described below are real, tested infrastructure, not aspirational.

### The demo media

Both `demo_v8_extended.gif` and `runux_gcp_demo_v3.gif`, previously captioned as a "live terminal trace" and an "automated execution" recording, are **hand-scripted animations** generated by `scripts/generate_runux_demo.py` / `_v2.py` using PIL's `ImageDraw` — synthetic frames drawn to look like a terminal, not a captured session. No `asciinema`, `script -c`, or similar capture tool is used anywhere in this repository's scripts. They are left in the repo below as illustrative mockups of the intended UX, labeled accurately.

---

## Architecture (as designed — see Measured Status for what's actually implemented)

```
┌───────────────────────────────────────────────────────────┐
│                       RunuX Kernel                        │
├──────────┬──────────┬──────────┬──────────────────────────┤
│ Process  │  Memory  │   VFS    │      Networking          │
│  Mgmt    │   Mgmt   │          │  IPv4/v6, Netfilter,     │
│ sched_   │ page_    │ vfs_     │  NAT, Conntrack,         │
│ core/    │ alloc/   │ inode/   │  Tunnel, IDPF            │
│ fair     │ slab/    │ dcache   │                          │
│          │ mmap     │          │                          │
├──────────┴──────────┴──────────┴──────────────────────────┤
│              kernel_types  (FFI Bridge Layer)              │
│          Bit-exact C ABI struct compatibility              │
├───────────────────────────────────────────────────────────┤
│        requires!() / ensures!()  Design-by-Contract        │
│        SafeSkb · SafeSock · SafePageFrame wrappers         │
├───────────────────────────────────────────────────────────┤
│      Lean 4 Formal Specifications (37 files, partial)      │
│   Ring 0 Defenses (closed) · Memory/Netfilter/Routing      │
│                    (open, in progress)                     │
└───────────────────────────────────────────────────────────┘
```

---

## Formal Verification (Lean 4)

```bash
cd specs/lean4 && lake update && lake build
../scripts/verify_specs.sh   # full type-check + per-module sorry/axiom report
```

| Subsystem | Theorems | Axioms | Open (`sorry`) |
|---|---|---|---|
| RunuX Core Defenses (Ring 0) | 84 | 0 | **0 — fully closed** |
| Boot & Memory Management | 50 | 26 | 35 |
| Netfilter / Conntrack / NAT | 224 | 67 | 164 |
| IPv4/IPv6 & Routing | 54 | 44 | 46 |
| GPU Compute & QuantumLTN | 9 | 1 | 0 |
| Sockets & Scheduling (misc.) | 11 | 0 | 0 |
| Audit (spec-defect proofs, new) | 2 | 0 | 0 |
| **Total** | **434** | **138** | **245** |

Two theorems that a first proof-completion pass could not close (`arp_send_safety`, `interrupts_disabled_after_init`) turned out to be **false as stated**, not merely hard — see the machine-checked disproofs in [`specs/lean4/MVK/Audit/SpecDefects.lean`](specs/lean4/MVK/Audit/SpecDefects.lean) (depends only on Lean's standard `propext` axiom). The 138 axioms are not all justified hardware assumptions; a register and reduction plan is at [`specs/lean4/AXIOMS.md`](specs/lean4/AXIOMS.md).

---

## The v12 Workflow: Metrics Gate + Oracle-Gated LLM Proof Completion

This project's response to the gap between claims and evidence is now built as reusable infrastructure, not just a one-time correction:

- **`scripts/metrics.py`** — static-analysis measurement of the Lean proof debt and Rust code quality, with a `ratchet` mode that fails CI if a PR makes any tracked metric worse than the frozen baseline (`docs/roadmap/metrics/metrics.baseline.json`). No build required.
- **`scripts/check_unit.py`** — an oracle for verifying a proposed fix to one theorem or one `unsafe` block: it rejects new axioms/`sorry`/lint-suppressions, and for Lean fixes it hashes the theorem **statement** so a "fix" that silently weakens what's being proven is rejected even if the weakened version still type-checks.
- **`scripts/units/generate.py`** — turns the measured gap into ~1,290 individually checkable work units (one per open `sorry`, undocumented `unsafe` block, `static mut`, or placeholder crate).

A first pilot run (4 files, 12 open theorems, two-tier LLM workflow) closed 4 theorems with independently re-verified proofs, proved 2 more false as stated, and surfaced a real failure mode: a fast-tier agent silently introduced 6 forbidden axioms and omitted this from its own report, caught only because a second pass happened to inspect git history. Full writeup, methodology, and that failure mode: **[`paper/claims_vs_evidence.tex`](paper/claims_vs_evidence.tex) / [`.pdf`](paper/claims_vs_evidence.pdf)** — this is the paper in this repository whose figures are all backed by a checked-in script, data file, or proof.

Details: [`docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md`](docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md), [`docs/roadmap/RESEARCH_DIRECTIONS.md`](docs/roadmap/RESEARCH_DIRECTIONS.md), [`docs/roadmap/AI_AGENT_DEFENSE_PLAN.md`](docs/roadmap/AI_AGENT_DEFENSE_PLAN.md).

---

## Papers in this repository

| Document | Status |
|---|---|
| [`paper/claims_vs_evidence.tex`](paper/claims_vs_evidence.tex) / `.pdf` | **Published** on Zenodo, [doi:10.5281/zenodo.22985926](https://doi.org/10.5281/zenodo.22985926); data on [Hugging Face](https://huggingface.co/datasets/callensxavier/claims-vs-evidence-runux-audit). Every figure traces to a checked-in script, data file, or Lean proof. |
| [`paper/runux_paper.tex`](paper/runux_paper.tex) / `.pdf` | Kept, corrected in place (formal-verification section now reports measured numbers instead of "zero sorry"). Its performance and chaos-engineering sections are **not** independently re-verified — see the TODO list below. |
| `paper/quarantine/*.tex` (4 papers) + 2 supporting docs | **Quarantined.** Each carries an in-file banner stating the specific figure and why no reproducible artifact was found (e.g. a claimed 25.3% `mmap` latency reduction on GCP bare metal has no matching benchmark harness anywhere in this repository; a claimed "100% elimination of memory vulnerabilities" is contradicted by a live aliasing bug found in this same audit). None are declared false outright — quarantine records absent evidence, not disproof. |

Full per-claim breakdown: [`docs/roadmap/PAPER_VERIFICATION_TODO.md`](docs/roadmap/PAPER_VERIFICATION_TODO.md).

---

## Quick Start

### Prerequisites

- Rust nightly toolchain with `rust-src`
- Lean 4 (via `elan`) for the specification tree
- Python 3.10+ for `scripts/metrics.py` and the unit-generation tooling (stdlib only)
- QEMU (for the demo-kernel boot harness — see caveat above)

### Build & Measure

```bash
git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git
cd rust-linux-mini-kernel

# Compile the workspace
CARGO_TARGET_DIR=/tmp/runux_target cargo check --workspace

# Run existing unit tests (74 of 316 crates have any)
cargo test --workspace

# Measure the actual state of the tree — no assertions, just numbers
python3 scripts/metrics.py measure

# Full Lean verification: 37 modules, real lake type-checking
cd specs/lean4 && lake build && cd ../scripts && ./verify_specs.sh
```

### Fuzzing

```bash
rustup run stable cargo install cargo-fuzz
cd fuzz
cargo +nightly fuzz run fuzz_packet -- -max_total_time=30
cargo +nightly fuzz run fuzz_routing -- -max_total_time=30
```

---

## Demo Media (illustrative mockups, not captured sessions)

![RunuX Kernel Boot Demo](demo_v8_extended.gif)
*Hand-drawn mockup of a QEMU boot sequence, generated by `scripts/generate_runux_demo.py` (PIL `ImageDraw`). Not a recording of a real build or boot.*

![RunuX GCP Bare Metal Deployment](runux_gcp_demo_v3.gif)
*Hand-drawn mockup of a bare-metal deployment terminal, generated by `scripts/generate_runux_demo_v2.py`. Not a recording of a real deployment; no verified evidence of a `c3-metal-85` deployment was found in this repository during the 2026-09-26 audit (see `docs/roadmap/PAPER_VERIFICATION_TODO.md`).*

---

## CI / CD Pipeline

| Workflow | What It Checks | Status as of v11.3.0 |
|---|---|---|
| **Metrics Ratchet** | `scripts/metrics.py ratchet` — no regression vs. baseline | ✅ Passing |
| **Verify Lean 4 Specifications** | `verify_specs.sh` — full type-check, 37/37 modules | ✅ Passing |
| **Runtime & Integration Tests** | `cargo check --workspace`, QEMU demo-kernel boot, fuzzing | ❌ Failing — pre-existing, traced to a poisoned-mutex cascade in `crates/printk`'s own test suite, reproduced against the unmodified pre-audit baseline commit; not caused by the audit or workflow changes |
| **RISC-V Cross-Compilation** | `cargo check --workspace --target riscv64gc-unknown-none-elf` | ❌ Failing — pre-existing on `main` at the same baseline commit |
| **Security Audit (Clippy)** | Full-strictness clippy pass | ❌ Failing — pre-existing; the "zero warnings" state elsewhere is achieved via blanket `allow` suppression, not by satisfying this check |

Reporting failing CI honestly here rather than showing green badges for checks that don't pass is the whole point of this update.

---

## Release History

See [CHANGELOG.md](CHANGELOG.md) for full entries. Recent:

| Version | Date | Milestone |
|---|---|---|
| **v11.3.8** | Sep 27, 2026 | Real AArch64 boot — a from-scratch `arch/aarch64`, third architecture, independently re-verified on GCP |
| v11.3.6 | Sep 27, 2026 | Real x86_64 long-mode boot via GRUB Multiboot2, independently re-verified on GCP |
| v11.3.4 | Sep 27, 2026 | RISC-V boots for real via OpenSBI, independently re-verified on GCP |
| v11.3.3 | Sep 27, 2026 | Wave 1 hardening, community outreach |
| v11.3.2 | Sep 27, 2026 | Open contribution & published paper |
| v11.3.0 | Sep 27, 2026 | Selected `claims_vs_evidence.tex` as the published paper; machine-checked spec-defect proofs; history rewrite removing two files that leaked internal infrastructure hostnames; removed a hard-coded Zenodo token |
| v11.2.1 | Sep 26, 2026 | Quarantined 4 papers + 2 supporting docs whose claims had no reproducible artifact |
| v11.2.0 | Sep 26, 2026 | Corrected `runux_paper.tex`'s formal-verification claims to measured numbers; added the v12 pilot writeup |
| v11.1.0 | Sep 6, 2026 | (Prior release; several of its README/paper claims are the ones corrected above) |

---

## Roadmap

Concrete, plan-only documents (nothing below is implemented yet):

- **[`docs/roadmap/BUSINESS_CASE_PRIORITIZED_PLAN.md`](docs/roadmap/BUSINESS_CASE_PRIORITIZED_PLAN.md)** — **start here.** Business case and the low-effort/high-impact ordering of everything below, with token-optimized, Haiku-first workflows (`.claude/workflows/runux-quickwins.js`) gated by an independent verifier.

- **[`docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md`](docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md)** — closing the 245 open proof obligations, the 141 placeholder crates, the 664 undocumented `unsafe` blocks, and getting a real bootable image on x86_64/riscv64, via the oracle-gated low-tier-model workflow.
- **[`docs/roadmap/AI_AGENT_DEFENSE_PLAN.md`](docs/roadmap/AI_AGENT_DEFENSE_PLAN.md)** — hardening the existing 40 Core Defenses requirements against an adaptive, high-frequency, black-box-querying AI-agent attacker, distinct from the human-paced attacker the current design assumes.
- **[`docs/roadmap/COMMUNICATION_PLAN.md`](docs/roadmap/COMMUNICATION_PLAN.md)** — how we're trying to reach contributors (Discussions, wiki, external channels), and the actual metrics for whether it worked.
- **[`docs/roadmap/STANDARD_HARDWARE_AI_GPU_PLAN.md`](docs/roadmap/STANDARD_HARDWARE_AI_GPU_PLAN.md)** — getting real PCIe/IOMMU/GPU support (starting with vendor-neutral `virtio-gpu`, not simulated NVIDIA/TPU claims) onto a standard x86_64 server, with the security properties (DMA isolation, VRAM zeroization) proven, not asserted.
- **[`docs/roadmap/RESEARCH_DIRECTIONS.md`](docs/roadmap/RESEARCH_DIRECTIONS.md)** — workflow fixes from the pilot's failure modes, and 7 open research questions.
- **[`docs/roadmap/PAPER_VERIFICATION_TODO.md`](docs/roadmap/PAPER_VERIFICATION_TODO.md)** — exactly what's missing for each quarantined claim to be restored.

---

## Acknowledgments

This project owes its existence to **Linus Torvalds** and the Linux kernel community, whose decades of engineering excellence created the foundation that RunuX translates into Rust. We also acknowledge the **Rust**, **Lean 4**, **RISC-V International**, and **QEMU** communities for the tooling this project builds on.

---

## Documentation

| Document | Description |
|---|---|
| [ROADMAP.md](ROADMAP.md) | **Public roadmap**: tracks, milestones, where to contribute |
| [CONTRIBUTING.md](CONTRIBUTING.md) / [AGENTS.md](AGENTS.md) | How humans and AI agents contribute; evidence rules |
| [SECURITY.md](SECURITY.md) | Private vulnerability reporting, including AI-agent attacks and prompt injection |
| [docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md](docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md) | Measured baseline, workstreams, and the low-tier-model workflow design |
| [docs/roadmap/PAPER_VERIFICATION_TODO.md](docs/roadmap/PAPER_VERIFICATION_TODO.md) | Per-claim status of every paper in this repository |
| [docs/roadmap/AI_AGENT_DEFENSE_PLAN.md](docs/roadmap/AI_AGENT_DEFENSE_PLAN.md) | Security hardening plan against AI-agent-class attackers |
| [docs/roadmap/RESEARCH_DIRECTIONS.md](docs/roadmap/RESEARCH_DIRECTIONS.md) | Workflow fixes and open research questions |
| [specs/lean4/AXIOMS.md](specs/lean4/AXIOMS.md) | Register of all 138 Lean axioms, pending justification |
| [specs/PROOF_STATUS_REPORT.md](specs/PROOF_STATUS_REPORT.md) | Auto-generated by `verify_specs.sh` on every run |
| [docs/SYMBRAIN_V4.md](docs/SYMBRAIN_V4.md) | SymBrain v4 design document (see `PAPER_VERIFICATION_TODO.md` for what's simulated vs. measured) |
| [paper/claims_vs_evidence.tex](paper/claims_vs_evidence.tex) | The published paper |
| [docs/roadmap/TPU_ACCELERATOR_IMPROVEMENT_PLAN.md](docs/roadmap/TPU_ACCELERATOR_IMPROVEMENT_PLAN.md) | Design proposal + M0-M5 milestone tracking for RunuX on Google Cloud TPU/accelerator hardware |
| [docs/roadmap/GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md](docs/roadmap/GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md) | n=30 real PCIe/IOMMU telemetry campaign, accelerator VM vs. control VM |
| [docs/roadmap/M5_GCE_CUSTOM_BOOT_ATTEMPT.md](docs/roadmap/M5_GCE_CUSTOM_BOOT_ATTEMPT.md) | Reproducible recipe for a custom GCE boot image from this repo's kernel; honest partial result |
| [docs/roadmap/GCP_AI_KERNEL_MILESTONE_PLAN.md](docs/roadmap/GCP_AI_KERNEL_MILESTONE_PLAN.md) | GPU (T4/L4/RTX-class) cost/quota investigation and plan |

## License

MIT License with Citation Requirement. See [LICENSE](LICENSE).

---

*Correcting the gap between claims and evidence — one measured commit at a time.*
