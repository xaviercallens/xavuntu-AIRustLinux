# RunuX on TPU and Google-Accelerator Infrastructure: An Honest Improvement Plan

**Status:** Design proposal, produced by an independent higher-effort
review pass (Opus-tier) after `GCP_AI_KERNEL_MILESTONE_PLAN.md`
established that this project's Compute Engine GPU quota is exhausted
and that Cloud TPU v5e quota is available instead. Nothing here has
been implemented as of this document; §1's ranking informed which
Phase 1 work was actually done (see `GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md`).
Every number in this document is either carried over from established
session context and marked as such, or a target/estimate, labeled as
one. Per `AGENTS.md` §1, none of it counts as evidence until a command
in a PR reproduces it.

**Scope of the wall:** RunuX will not drive TPU compute. This proposal
is built around that fact, not around getting past it. Google's TPU
hardware is dramatically more closed than even NVIDIA's -- no public
ISA, no command-submission protocol documentation, no register-level
programming manual, no open-source driver analog to `nouveau`. All
real access to TPU compute goes through Google's proprietary
`libtpu.so` and the XLA compiler stack. **Writing any kind of real
command-submission/compute-dispatch driver for the TPU from RunuX is
not "very hard" -- it is close to impossible without inside access to
Google's hardware team, and any proposal claiming otherwise should be
rejected.**

---

## 0. Corrections applied before further planning

An initial real-hardware observation this session (documented in
`GPU_REAL_HARDWARE_TELEMETRY.md`) was reviewed and found to contain
real overclaims and one real safety bug. All were corrected before
this plan proceeded -- see that document's "Corrections" section and
`GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md` for the controlled, n=30 follow-up
that resolved the open questions (passthrough vs. emulation: resolved,
`vfio-pci`-bound; IOMMU: resolved, present only on the TPU VM and not
on a same-CPU-family control). Doing this correction *before* further
design work, rather than after, is itself the pattern this document
tries to reinforce throughout.

---

## 1. What "leverage Google's accelerator" can honestly mean

### 1.1 Rejected interpretations

| Idea | Why it is rejected |
|---|---|
| A TPU command-submission or compute driver in RunuX | No public ISA, queue format, register map, firmware interface, or open reference driver exists. The TPU's PCI class code (`0xff00`, vendor-specific) itself carries no semantics. Reverse-engineering `libtpu.so` is outside this project's capability, likely against the Cloud Terms of Service, and would produce nothing independently verifiable. **Rejected.** |
| Reading or writing the TPU's MMIO BARs to "fingerprint" it | Touching undocumented registers on a proprietary, live, `vfio-pci`-passthrough device can hang the device or the VM, and a successful read has no meaning we could check against anything. **Rejected.** BAR *sizes* from sysfs are fine (already done); BAR *contents* are not. |
| Performance comparisons with Google's own TPU stack | RunuX runs no TPU workload, so there is nothing to compare. **Rejected.** |
| "RunuX as an AI-accelerator kernel" | RunuX cannot boot on a TPU VM today (no bootloader/serial-console plumbing exists for that), and even if it could, it could not use the accelerator. **Rejected as framing.** |
| Cryptographic "hardware attestation" from PCI enumeration alone | A guest's view of PCI is whatever the hypervisor presents. Enumeration can check internal consistency, but it cannot attest anything against a hostile or compromised hypervisor -- that needs a real root of trust (vTPM quote, confidential-computing attestation report). **Reframed**, not rejected outright -- see candidate B. |

### 1.2 Realistic candidates

Every candidate must pass: *what command proves it, and what result would falsify it?*

#### A. Differential PCI topology verification plus a telemetry dataset — DONE for Phase 1

Run RunuX's real enumeration code repeatedly against an independent
oracle (Linux sysfs), with a proper control (same CPU family, no
accelerator). This is exactly what `GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md`
now documents: n=30 on both a TPU VM and a control VM, 100%
config-byte match against sysfs, zero side effects, and a resolved
answer on both the passthrough and IOMMU questions.

- **Value:** Turns "worked once" into a real, controlled, falsifiable
  result. Produces a genuinely useful topology/telemetry dataset as a
  side effect.
- **Reuse:** High -- extends `examples/pci_probe_userspace` and follows
  the `boot_telemetry/*.csv` precedent already established for the
  three CPU-architecture boot verifications.

#### B. Inventory consistency checking (the honest version of "attestation")

A narrower tool: does a VM's device inventory match what its declared
machine type and accelerator type should expose, and does it stay
stable over time and across the fleet? E.g. "a `v5litepod-1` should
expose exactly one `1ae0:0063` function, bound to `vfio-pci`."

- **Oracle:** baselines from A's telemetry data. Deliberately inject a
  mismatch and confirm the tool flags it (the same discipline already
  applied to validate `pci_diff.py` itself before any real cloud run).
- **Does not prove:** anything against a malicious hypervisor -- that
  limitation must be stated in the tool's own output, not only in
  docs. Real attestation needs a hardware root of trust (vTPM quote)
  this project doesn't yet use.
- **Value:** real but modest. Reuse: medium-high (A plus an
  expectations file).

#### C. The host-side defense stack in shadow mode against real ML workloads

The most interesting long-term direction, and the riskiest one.
`ebpf_firewall`, `ai_detector`, and `immutable_logs` carry this
project's only fully closed proof file (`RunuxDefenses.lean`, 84
theorems). Those proofs cover the *logic* of the architecture -- its
invariants -- and say nothing about whether the classifier catches
real attacks or tolerates real benign workloads on real AI
infrastructure. That's an empirical question a TPU VM running JAX can
help answer.

Proposed steps: (1) record syscall traces from real, benign ML jobs on
a TPU VM (`bpftrace`/`perf trace`/`strace -f` -- tools already
available there, no libtpu internals inspected); (2) compile the
firewall policy engine and classifier as a host library; (3) replay
traces offline and measure false-positive rate ("shadow mode"); (4)
later, replay synthetic malicious traces built from public
ATT&CK-style patterns, explicitly labeled synthetic.

- **Falsified by:** a high false-positive rate on benign ML traces --
  a genuinely useful negative result, not a failure to hide (e.g.
  libtpu's `ioctl`/`mmap`/`futex` call patterns may look anomalous to
  a classifier never trained on them).
- **Does not prove:** kernel-side latency. The project's "sub-15µs"
  classifier target cannot be measured from userspace replay and must
  never be cited from it. Does not prove robustness against adaptive
  adversaries.
- **Honesty flag:** classifier thresholds and decision boundaries are
  named security-boundary changes under `AGENTS.md` §2 and require
  `needs-human-review` regardless of which tier produces them.
- **Value:** potentially the highest in this list -- it tests the
  project's most mature, most-verified subsystem against reality, not
  just against its own formal model. Effort: open-ended.

A small dogfooding item fits here too: store telemetry records from A
in an `immutable_logs` Merkle log and publish the root hash in the PR.
That gives tamper-evidence of the dataset *relative to the published
root* -- not protection against the author, and the docs should say so.

#### D. AMD-Vi (AMD IOMMU) model in Lean

Unlike the TPU, AMD's IOMMU is publicly specified (AMD I/O
Virtualization Technology spec, document #48882). A Lean model of the
Device Table Entry, the translation walk, and a DMA-isolation theorem
("device d can reach only pages mapped in its domain's table") is
achievable spec work extending the existing Intel-VT-d-only
`iommu_vtd` crate -- and, as of `GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md`,
this is no longer hypothetical: a real AMD-Vi IOMMU (`ivhd0`) doing
real passthrough isolation for a real Google accelerator was directly
observed.

- **Honesty flag:** the guest cannot program the host's IOMMU, and
  RunuX cannot boot on this VM to exercise a model against it -- this
  is spec work justified by *evidence that AMD-Vi is relevant to real
  GCP workloads*, not validated *by* anything observed here.
  IOMMU/DMA-range changes are a named security boundary needing human
  review.
- **Value:** real for the formal-methods track, now with a concrete
  motivating example instead of a hypothetical one.

#### E. Custom-kernel boot plumbing on GCE

Booting RunuX itself through a custom image and the serial console.
Plausible on plain Compute Engine (which supports both); likely not
available on managed TPU VMs (Google-managed runtime images) --
unconfirmed, worth checking as its own small task before investing
further. Even with RunuX booted on a TPU VM, the accelerator would
stay unusable per the wall stated up top.

### 1.3 Ranking (informed §2's actual Phase 1 scope)

| Rank | Candidate | Achievability | Reuse | Value | Status |
|---|---|---|---|---|---|
| 1 | A. Differential PCI verification + dataset | High | High | Moderate | **Done** (`GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md`) |
| 2 | B. Inventory consistency | Moderate-high | Moderate-high | Moderate | Not started |
| 3 | C. Defense stack in shadow mode | Moderate (trace capture easy; evaluation hard) | High (code) / low (infra) | Potentially highest | Not started |
| 4 | E. GCE custom boot | Moderate (plain GCE); low (TPU VM) | Moderate | Low-moderate | Not started |
| 5 | D. AMD-Vi Lean model | Moderate (spec work) | Low | Low-moderate, now motivated by real evidence | Not started |
| — | TPU compute driver, MMIO fingerprinting, perf claims | none | n/a | n/a | **Rejected, not a milestone** |

---

## 2. Milestone sequence

| M | Content | Boundable? | Status |
|---|---|---|---|
| **M0** | Corrections to the first observation: safety fix in `pci_probe_userspace`, wording fixes, `pci.ids` check | Yes | **Done** |
| **M1** | Differential harness: n=30 on TPU v5e + AMD control VM, independent sysfs oracle (validated on synthetic data first), CSVs, doc | Yes, one session, <$2 | **Done** |
| **M2** | Replay backend + CI fixtures: capture campaign data as a checked-in test fixture so `cargo test -p driver_pci_probe` re-verifies this result without cloud access on every PR | Yes | **Done** -- `driver_pci_core::PciConfigBackend` trait (generic, no `dyn`/`alloc`, works in the `#![no_std]` kernel path), `driver_pci_access::HardwareIo` real-hardware impl, `crates/driver_pci_probe/tests/replay_gce_tpu_v5e.rs` replaying genuine captured config-space bytes from the real TPU VM campaign; validated to actually fail on a deliberately corrupted fixture before trusting it |
| **M3** | Round 2-3: Intel-family control, other TPU generations/zones as quota allows, inventory expectations file (B) | Each round boundable; total coverage open-ended (quota-dependent) | Not started |
| **M4** | Candidate C: benign ML syscall traces, offline replay through `ebpf_firewall`/`ai_detector`, FPR with confidence intervals; synthetic attack traces labeled as such | Collection: yes. Usefulness: open-ended | **Done** (both halves) -- collection: n=10 traces each for 2 real JAX/TPU workloads, `ML_WORKLOAD_SYSCALL_TRACES.md`. Replay: 620,934 real events through the real, unmodified `ebpf_firewall`/`ai_detector` code, `ML_WORKLOAD_FIREWALL_REPLAY.md`. Firewall layer: clean, deterministic, fully explicable (0.0032% flagged, always the same real JIT-compilation call). **Bigger finding than a FPR number**: the classifier's weights have no evident training provenance anywhere in this repo, and its erratic behavior on identical benign traffic is consistent with an untrained/arbitrary weight matrix, not a fitted model -- meaningful FPR/TPR evaluation is blocked on training it first. Synthetic attack traces remain unstarted |
| **M5** | Candidate E: RunuX boots on plain GCE via custom image + serial console | Plain GCE: likely boundable. TPU VM: unconfirmed, possibly not possible | **Attempted, partial.** Image-build/import recipe works (real, reusable, documented in `M5_GCE_CUSTOM_BOOT_ATTEMPT.md`) and SeaBIOS-level firmware execution succeeds on real GCE hardware. Actual boot hangs/garbles right after "Booting from Hard Disk 0..." -- narrowed to Google's own SeaBIOS fork (`1.8.2-google`) via a real local repro showing mainline SeaBIOS + the identical `virtio-scsi` disk boots cleanly. Root cause within the fork not isolated; stopped here rather than force a fix, per `AGENTS.md`'s "I couldn't is acceptable" rule |
| **M6** | Candidate D: AMD-Vi Lean model + isolation theorem | Open-ended (formal-methods track) | Not started |
| **M7** | vTPM-bound inventory records (B+) | Open-ended | Not started |
| — | TPU compute driver | **Not a milestone.** | Rejected |

**Community-shareable work items** (each should become an
`agent-ready` issue with exact files and an oracle): M2's replay
backend, each M3 environment as its own "add fixture for
&lt;generation/zone&gt;" issue, M4's trace-replay harness (kept
separate from the classifier evaluation itself), M5, M6.

---

## 3. Non-goals (restated from `GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md` and `GPU_REAL_HARDWARE_TELEMETRY.md`, kept here for one authoritative list)

This plan does not claim, promise, or aim at: any TPU compute,
command submission, memory management, firmware interaction, or MMIO
register access; any reverse engineering of `libtpu.so` or TPU
firmware; any performance claim involving TPUs or comparison with
Google's own stack; that RunuX boots on a TPU VM (it doesn't, and
whether it can is unknown); that PCI enumeration inside a VM observes
physical hardware directly rather than a hypervisor's presentation of
it (resolved for the specific TPU function via `vfio-pci` binding, not
generalized to every function); cryptographic attestation against a
hostile hypervisor; any security certification; that the Lean proofs
in `RunuxDefenses.lean` say anything about empirical detection quality
against real traffic (they cover design invariants only); that the
"sub-15µs" classifier target has been measured in any setting
described here; or novelty of the topology dataset beyond what was
actually checked against the public PCI ID registry.
