# RunuX as an AI-Computing Kernel on GCP GPUs — Milestone Plan & Cost Estimate

**Status: PLAN ONLY, and Milestone 1 is currently BLOCKED.** Nothing
in this document has been implemented or purchased — and an actual
attempt to start Milestone 1 (§4) failed for a real, verified reason
documented in §2.1. Every number below comes from a command run in
this session (`gcloud`) or a cited public source; nothing is asserted
by hand. See `AGENTS.md` evidence rules.

**Baseline:** `main` at commit `58f10d0` (PR #76, real PCI enumeration
verified against QEMU's `virtio-gpu-pci`).

---

## 1. What was actually asked, decomposed honestly

"Implement RunuX as a kernel for AI computing on standard GPU RTX and
T4, optimized and certified" bundles three very differently-sized
problems. Treating them as one line item would hide that mismatch, so:

1. **Boot / run on real GCP GPU-attached VMs.** Small, achievable, a
   direct continuation of PR #76's real PCI enumeration work — proving
   it against genuine silicon instead of QEMU's `virtio-gpu-pci`.
2. **Actually do AI compute on the GPU** — command submission, VRAM
   mapping, a fence/ring-buffer path, IOMMU-gated DMA. This is where
   "GPU driver" complexity lives. `STANDARD_HARDWARE_AI_GPU_PLAN.md`
   already concluded a from-scratch NVIDIA driver is a multi-year
   effort even for a funded team; nothing found while writing this plan
   changes that conclusion.
3. **"Certified."** This needs its own split:
   - **Formally verified** (Lean 4, in-house, extending this project's
     own existing proof tree) — real, bounded, within this project's
     control.
   - **Third-party certified** (Common Criteria / ISO 15408, FIPS
     140-3, or similar) — accredited-lab evaluations that run
     **$100K-$1M+ and 1-3 years** even for a mature, feature-frozen
     product. Not achievable by any amount of coding-agent work, and
     not something this plan promises.

## 2. Real GCP findings for this project (`gen-lang-client-0625573011`), checked 2026-09-27

```
$ gcloud compute project-info describe --format="value(quotas)" | grep GPUS_ALL_REGIONS
{'limit': 1.0, 'metric': 'GPUS_ALL_REGIONS', 'usage': 1.0}

$ gcloud compute instances list --format="table(name,zone,machineType,status,guestAccelerators[].acceleratorType)"
NAME                            ZONE        MACHINE_TYPE   STATUS   ACCELERATOR_TYPE
socreateai-agora-hermes-node1   us-east4-b  n1-standard-8  RUNNING  nvidia-tesla-t4
```

**This project's entire GPU quota is already consumed** — by a running,
pre-existing, unrelated instance (`socreateai-agora-hermes-node1`),
untouched by any of this session's work. Practical consequences:

| GPU | Quota available right now | What's needed to unblock |
|---|---|---|
| **T4** (on-demand or spot/preemptible) | **0** — `NVIDIA_T4_GPUS` and `PREEMPTIBLE_NVIDIA_T4_GPUS` limits are both 1, both already used | A quota increase request (free to file, but Google-side approval, not instant or guaranteed) or freeing the existing instance (not this project's to touch) |
| **L4** (Ada Lovelace — the same GPU generation as consumer RTX 40-series, GCP's actual cost-optimized "RTX-class" accelerator) | **1 on-demand + 3 preemptible/spot, unused** | Nothing — usable today |
| **RTX PRO 6000 Blackwell** (`G4` machine family — GCP's literal "RTX" branded SKU) | **0** — doesn't even appear in this project's quota list | A fresh quota request; see cost caveat below |

**The literal "RTX" you asked about (`G4`/RTX PRO 6000 Blackwell) is not
a low-cost SKU.** It's a brand-new, professional-tier Blackwell-generation
GPU aimed at simulation/graphics/Omniverse workloads
([Google Cloud Blog](https://cloud.google.com/blog/products/compute/introducing-g4-vm-with-nvidia-rtx-pro-6000)).
No public per-hour price was found for it as of this writing — it isn't
even listed in most third-party GPU-pricing aggregators yet, which
itself signals a premium/recent SKU. Given comparable high-end GCP GPUs
(A100 80GB ≈ $5.03/hr, H100 ≈ $10.98/hr), a reasonable expectation is
**$3-10+/hr on-demand**, the opposite of "low cost."

**Recommendation:** treat **L4** as the real "RTX, low-cost" target —
it's the actual GPU generation consumer RTX cards share, it's
genuinely cheap, and its own per-type quota is already granted. Pursue
**T4** as a second, cheaper-still target once quota allows. Only pursue
literal G4/RTX PRO 6000 if you specifically want that SKU despite the
cost — flagging this mismatch for your decision, not assuming either
way.

### 2.1 Update (same day): the real blocker is a single project-wide cap, and it cannot self-service-increase

The per-GPU-type quotas in §2 (`NVIDIA_L4_GPUS`, `PREEMPTIBLE_NVIDIA_L4_GPUS`)
being non-zero was necessary but **not sufficient** — GCP also enforces
a single, project-wide `GPUS_ALL_REGIONS` cap across *every* GPU type
combined, and this project's cap is 1, already fully consumed by the
pre-existing unrelated T4 instance. Confirmed by an actual attempt, not
inferred:

```
$ gcloud compute instances create runux-gpu-verify --accelerator=type=nvidia-l4,count=1 ...
ERROR: (gcloud.compute.instances.create) Could not fetch resource:
 - Quota 'GPUS_ALL_REGIONS' exceeded.  Limit: 1.0 globally.
```

A self-service increase request was filed against this exact quota
(`GPUS-ALL-REGIONS-per-project`, preference id `724275da-95af-44f6-a683-8bc9108d9644`)
with a human justification and contact email. **It was denied
automatically within seconds:**

```
$ gcloud quotas preferences describe 724275da-95af-44f6-a683-8bc9108d9644 ...
quotaConfig:
  grantedValue: '1'
  preferredValue: '3'
  stateDetail: Quota request denied
```

This was also not the first attempt — the same quota preference object
shows a prior `AUTO_ADJUSTER`-originated request to raise it to 3 was
already denied on 2026-09-26, a day before this session. The automated
self-service path for this billing account (`Compte facturation xavier
GCP perso` — a personal account) appears to be exhausted for this
quota. **Milestone 1 as originally scoped cannot proceed on this GCP
project without one of:**

1. **A manual Google Cloud support case** requesting the increase by
   hand — free (Basic support) accounts can still file quota-increase
   cases, but response time and outcome aren't guaranteed, and this is
   a real support interaction requiring your account, not something I
   can do on your behalf beyond drafting the request.
2. **Freeing the existing instance's GPU** (`socreateai-agora-hermes-node1`,
   T4, us-east4-b) — not attempted or requested here, since that
   instance is not part of this project's work and stopping or deleting
   it is your call entirely, not mine to suggest as a default.
3. **A different GCP project** with its own, separate default GPU
   quota (new projects often start with a small nonzero allocation,
   though this isn't guaranteed either) — if you have one, or are
   willing to create one solely for this milestone.
4. **Waiting and retrying later** — quota eligibility can change with
   more billing history/spend on the account; no defined timeline.

## 3. Cost estimates (sourced 2026-09-27; reconfirm on the [live pricing calculator](https://cloud.google.com/products/compute/pricing) before any real spend — these are third-party-aggregator estimates, not a quote)

| Instance | On-demand | Spot/preemptible | Source |
|---|---|---|---|
| `g2-standard-4` (1x L4, 4 vCPU, 16GB) | ≈ $0.71/hr | ≈ $0.34/hr | [Economize](https://www.economize.cloud/resources/gcp/pricing/compute-engine/g2-standard-4/), [Vantage](https://instances.vantage.sh/gcp/g2-standard-4) |
| T4-attached VM (once quota unblocked) | ≈ $0.35-0.54/hr | ≈ $0.11-0.16/hr | [Thunder Compute](https://www.thundercompute.com/blog/nvidia-t4-pricing), [getdeploying.com](https://getdeploying.com/gpus/nvidia-t4) |
| G4 (RTX PRO 6000 Blackwell) | not publicly listed; estimated $3-10+/hr | unknown if spot is even offered | inferred from A100/H100 tier, not directly sourced |

**Bounded milestone cost estimates** (compute time only; $0 storage/network
at this scale):

| Milestone | GPU-hours (est.) | Cost at spot rates |
|---|---|---|
| **M1** — real hardware verification (below) | 1-2 hrs | **under $1** (L4) |
| **M2** — minimal MMIO/BAR mapping + IOMMU-gated DMA groundwork | 10-20 hrs, spread over iteration | **$3-7** (L4) |
| **M3** — a real minimal compute-submission path (see §5) | genuinely open-ended; not estimated here | scope decision needed before any number is honest |

## 4. Milestone 1 — partially achieved via a different resource (TPU, not GPU): see `GPU_REAL_HARDWARE_TELEMETRY.md`

**Update (same day):** with GPU quota confirmed exhausted and region-hopping
empirically ruled out (§2.1), this project's real (and previously
unnoticed) Cloud TPU v5e quota (`TPU_LITE_PODSLICE_V5`, separate quota
pool from Compute Engine GPUs) was used instead. A single spot
`v5litepod-1` TPU VM let this project's real PCI enumeration code run,
unmodified, as a privileged userspace process against genuine
(non-QEMU) hardware for the first time — full results, cost, and scope
limits in [`GPU_REAL_HARDWARE_TELEMETRY.md`](GPU_REAL_HARDWARE_TELEMETRY.md).
**This is not a GPU and does not unblock the RTX/T4 goal** — no NVIDIA
hardware was reached — but it is real progress on the underlying "does
this code work outside an emulator" question, at near-zero cost. The
original GPU-specific Milestone 1 plan below remains blocked exactly as
described in §2.1.

### Original plan (still blocked for GPUs specifically)

Directly continues the verified, merged work in #69-#76 — same
pattern (fresh VM, real `apt-get`, unmodified script, independent of
my dev sandbox), same telemetry-doc discipline, now against a real GPU
instead of QEMU's `virtio-gpu-pci`.

**Plan:**
1. Create one `g2-standard-4` **spot** VM (1x L4), Debian 12, `us-central1-a` (or wherever L4 spot capacity is available that day — spot can fail to allocate; the harness itself needs no GPU driver, since we're reading raw PCI config space, not calling CUDA).
2. Install `qemu-system-x86` is **not** needed this time — this runs the harness as a real boot, or, more practically, first validate `driver_pci_probe::pci_enumerate` as a **userspace tool** (read `/sys/bus/pci` config space via `/dev/mem`-equivalent or just cross-check against `lspci -nn` output) before attempting a full bare-metal boot on a cloud VM (which has no serial console access by default and would need `gcloud compute instances tail-serial-port-output` wired up — solvable, but let's not conflate "does the code identify T4/L4's real vendor:device ID" with "can I get a bare-metal kernel boot logging to GCP's serial console," which is a separate, non-trivial step).
3. Confirm: the real PCI vendor/device ID GCP's L4 (and T4, once unblocked) actually reports matches this project's already-committed, cited constants (`driver_pci_core::KNOWN_NVIDIA_GPUS` currently has Tesla T4 and RTX 4090 — **L4's real ID would need to be added and cited**, since it isn't in the table yet).
4. Delete the VM immediately after. Write `docs/roadmap/GPU_REAL_HARDWARE_TELEMETRY.md` documenting exactly what was found, mirroring `GPU_PCI_PROBE_TELEMETRY.md`.
5. Cost: under $1, bounded by design (single VM, under 2 hours, spot pricing, deleted immediately).

**This does not require your approval to be cheap — it requires your
approval because it's still a real charge against a real billing
account**, per this session's standing rule of confirming before any
billable resource. I have not created anything.

## 5. What comes after M1 (not committed, scoped for a future decision)

Actual "AI computing" — a compute kernel actually dispatching work to
the GPU — needs, at minimum: VRAM BAR mapping with correct caching
attributes, an IOMMU-backed DMA-safe command buffer, a real command
submission protocol (NVIDIA's is proprietary and firmware-gated on
modern cards — even the open `nouveau`/`nova` Linux drivers rely on
NVIDIA's signed GSP firmware blob for anything past Turing/T4-class
cards), and a fence/completion mechanism. Each of those is itself a
multi-week-to-multi-month effort with real risk of hitting an
unresearchable wall (undocumented, firmware-gated hardware behavior).
This plan deliberately does **not** commit to a M3 timeline or cost —
doing so honestly requires deciding, with you, how deep to go (e.g.
"prove we can map and read back a VRAM page" is bounded; "run a matrix
multiply on the GPU from RunuX" is not, without NVIDIA's own driver
source or firmware documentation this project does not have).

## 6. "Certified" — realistic paths

- **Extend Lean 4 formal verification to the new PCI/DMA code.**
  Real, bounded, in this project's control, consistent with its
  existing `RunuxDefenses.lean` (84 theorems, 0 `sorry`) pattern. A
  reasonable, honestly-sized next step once the driver code itself
  stabilizes — proving something like "no DMA descriptor derived from
  `driver_pci_access::pci_bar_size` can address outside the BAR's
  reported extent" is a concrete, achievable theorem.
- **Third-party certification** (Common Criteria, FIPS 140-3, or
  similar): genuinely out of reach for this kind of project — six or
  seven figures, an accredited external lab, 1-3 years, and typically
  requires a frozen, shipping product as the evaluation target. Not
  something to promise or budget for here. If this is a hard
  requirement for your use case, it needs a real conversation about
  budget and timeline separate from engineering work.

## 7. Explicit non-goals of this plan

- Does not promise a working NVIDIA AI-compute kernel.
- Does not promise third-party certification of any kind.
- Does not pursue G4/RTX PRO 6000 Blackwell by default (cost mismatch
  with "low cost," flagged above) unless you say otherwise.
- Does not create any GCP resource — this document is the proposal
  step you asked for.

## 8. Decisions already made, and the one still open

Resolved in this session: (1) L4 over G4/RTX PRO 6000 — confirmed; (2)
file a GPU quota-increase request — done, denied automatically within
seconds (§2.1); (3) approve bounded Milestone 1 spend — approved, but
blocked, since there is currently no quota to spend against.

**Still open — pick one of the four unblock paths in §2.1:**

1. File a manual Google Cloud support case for the quota increase (I can draft the request; filing and any account verification is yours).
2. Free the GPU on the pre-existing `socreateai-agora-hermes-node1` instance (your call entirely — I have not touched it and won't without explicit instruction).
3. Use a different GCP project with its own default quota, if available.
4. Wait and retry the self-service request later.

Nothing further proceeds on Milestone 1 until one of these is chosen.
