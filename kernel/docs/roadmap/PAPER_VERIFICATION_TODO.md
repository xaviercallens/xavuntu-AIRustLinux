# Paper Verification TODO

**Status as of 2026-09-26.** This tracks which documents under `paper/` are
published (claims are backed by a reproducible artifact in this repository)
versus quarantined (claims could not be substantiated during this audit).
Quarantined documents carry an in-file banner and live under
`paper/quarantine/`; do not move them back to `paper/` until every row for
that document below is resolved.

Companion to `docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md` (which covers
code/proof debt) — this file covers the separate problem of papers making
empirical claims the repository can't currently reproduce.

---

## Published

| Document | Status | Basis |
|---|---|---|
| `paper/claims_vs_evidence.tex` / `.pdf` | **Selected for archival publication** | All figures backed by checked-in scripts, data, or Lean proofs; see "Publication candidate" below. |
| `paper/runux_paper.tex` / `.pdf` | Kept, superseded; Sections 3.3/5/6 open (see TODO) | Formal-verification numbers (432 theorems, 138 axioms, 245 open, 84-theorem closed Ring-0 model) cross-checked against `scripts/metrics.py measure` and `specs/PROOF_STATUS_REPORT.md`. The new Section 4.3 pilot data cross-checked against `docs/roadmap/units_status.csv` and this session's independent oracle re-verification of PR #27/#28. Performance/chaos-engineering tables (Section 5–6) are **not** independently re-verified this cycle — see TODO below. |
| `paper/xavier_publications.tex` | Published, with caveats | A publication index, not itself a results paper. Item summaries for the quarantined papers must stay consistent with their quarantine status — see TODO below. |
| `paper/COLLABORATION_PROPOSAL.md` / `.pdf` | Not reviewed | No empirical claims found on a skim; out of scope for this pass. |
| `paper/REPRODUCIBILITY.md`, `paper/REPRODUCIBILITY_SOP.md` | Not reviewed | Describe a process, not results; out of scope for this pass. |

### Publication candidate (2026-09-26)
`paper/claims_vs_evidence.tex` / `.pdf` supersedes `runux_paper.tex` as the paper selected for archival publication. Every figure in it is backed by a checked-in script, data file, or Lean proof (`scripts/metrics.py`, `docs/roadmap/metrics/metrics.baseline.json`, `docs/roadmap/units_status.csv`, `specs/lean4/MVK/Audit/SpecDefects.lean`).

### TODO on `runux_paper.tex` (findings from the 2026-09-26 re-check)
- [ ] **CRC32 "4.73% faster"**: `paper/dataset.json` holds 5 runs per side with overlapping ranges; Welch t = 1.64 — not significant at α = 0.05. Re-run with n ≥ 30 and report a CI, or drop the speedup claim.
- [ ] **QEMU boot time 5003 vs 5004 ms**: the boot harness targets the i686 `examples/demo_kernel`, not the translated crates. Rescope the claim to the demo kernel or build a real image (see v12 plan WS5).
- [ ] **TCP throughput ≥95% of C**: no C baseline is recorded (table shows "—"); the verdict is unsupported until one is measured.
- [ ] **Chaos Mesh "zero panics"**: `run_gke_tests.py` detects panics by grepping the demo kernel's QEMU boot log for the string "panic"; the translated stack is not exercised. Rescope or redesign as a differential test.
- [ ] **"297/297 modules translated"**: 141 crates are ≤25-LOC placeholders (`scripts/metrics.py`, `rust.placeholder_crates`); rescope to the implemented subset.
- [ ] **Sensitive content**: `paper/mvk_chaos_benchmarks.tar.gz` (in public history since `a9f8419`) contains `chaos_run.log` lines naming internal employer Helm mirrors and a local SOCKS proxy. Exclude from any archival upload; consider removing from the repository and history (owner decision — history rewrite is destructive).
- [ ] `xavier_publications.tex` item 1 ("RunuX-AI: Systolic-Aware ML Runtimes") currently states "88.0% occupancy rate (173.4 TFLOPS)" as fact, with no "simulated" qualifier — the source paper (`runux_ai_paper.tex`, now quarantined) does say "under high-fidelity **simulation**". Fix the summary to carry the same qualifier, or remove the figure until real-hardware validated.
- [ ] `xavier_publications.tex` item 3 ("MVK") repeats the unverified 25.3%/12.2% GCP bare-metal figures from the now-quarantined `mvk_scientific_paper.tex`. Update or remove pending resolution of that quarantine.
- [ ] `xavier_publications.tex` item 4 repeats the "95% Attack Surface Reduction" and eradication claims from the now-quarantined `security_scientific_paper.tex`. Same treatment.

---

## Quarantined (`paper/quarantine/`)

### `mvk_scientific_paper.tex` / `.pdf`
Claims: `mmap` latency −25.3%, page-fault latency −12.2%, syscall latency +8.9%, all measured via `rdtsc` on a "dedicated Google Cloud C2 bare-metal" instance; a "12-hour sustained fuzzing stress test" showing "1.2 panics/hour" on the C baseline vs. 0.0 on MVK; 2-hour flatline latency test.

- [ ] Locate or write the `rdtsc`-based benchmark harness described (syscall/mmap/page-fault latency loops, 100k–1M iterations). None found under `scripts/` or `crates/` in this audit.
- [ ] If it doesn't exist, either build it and re-run on comparable hardware, or retract the specific cycle-count table and replace with whatever is actually reproducible.
- [ ] Locate the "12-hour sustained fuzzing stress test" artifact/logs (panics/hour claim) — none found; `fuzz/fuzz_targets/` currently has 2 targets run for seconds, not hours, per `paper/runux_paper.tex`'s own (published) fuzzing description.
- [ ] Resolve the discrepancy: this paper claims dedicated non-emulated bare-metal GCP execution; nothing elsewhere in the repo corroborates that this specific run happened. Either produce the run's raw telemetry/logs or retract the "natively on GCP... rather than in hypervisor emulation" framing.

### `security_scientific_paper.tex` / `SECURITY_SCIENTIFIC_PAPER.md` / `.pdf`
Claims: "eliminates 100% of spatial and temporal memory vulnerabilities at compile time"; "95% attack surface reduction... quarantines raw hardware IO to <4.2% of the codebase."

- [ ] Measure actual `unsafe` density and compare to the "<4.2%" claim. This session measured 722 `unsafe {}` blocks and 1,613 `unsafe fn` across the workspace (53,778 LOC) — this needs to be expressed as a comparable percentage and checked against the claim, not assumed.
- [ ] The "100% elimination" claim is contradicted by this session's finding of a live aliasing bug in `crates/ai_detector` (`activation_slice(&self) -> &mut [i8; N]`) and by only ~14% `SAFETY:` comment coverage on `unsafe` blocks (101/722). Either fix and re-audit before restating the claim, or scope the claim explicitly to the *safe* subset of the codebase (which the compiler does genuinely protect) rather than the whole kernel including its `unsafe` surface.
- [ ] No Miri run log exists in this repository confirming zero UB workspace-wide (Miri is installed locally per this session's tooling check, but has not been run over the full workspace as part of this audit). Run `cargo miri test` over at least the core crate set (see `RUNUX_V12_VERIFIED_CORE_PLAN.md` §3) before restating any "zero UB" claim.

### `quantum_ltn_paper.tex` / `.pdf`
Claims: 72.45× contraction acceleration (1,424.5µs → 19.6µs), 55.40× VRAM reduction (1,280MB → 23.1MB), on GCP `n2-standard-4` using Google's `TensorNetwork` library; unitary/energy drift bounds; "all boundary invariants... closed in the Lean 4 proof assistant."

- [ ] `crates/quantum_ltn/` and `specs/lean4/MVK/QuantumLTN/PolarQuant.lean` exist and are relevant, but no benchmark script producing these exact figures (1,424.5µs, 19.6µs, 1280MB, 23.1MB) was found. Locate or reconstruct the benchmark run, or retract the specific numbers.
- [ ] Confirm whether this was ever run against the real `TensorNetwork` library on real `n2-standard-4` hardware, or is a projected/simulated estimate. State whichever is true explicitly in the paper.
- [ ] Cross-check "closed in the Lean 4 proof assistant" against `specs/lean4/MVK/QuantumLTN/PolarQuant.lean` (1 theorem, 1 axiom per this session's measurement) and `FuzzyLogic.lean` (0 theorems) — confirm the claimed invariants actually correspond to what's proved there, not just an adjacent-sounding theorem name.

### `runux_ai_paper.tex` / `.pdf`
Claims: 88.0% MXU occupancy / 173.4 TFLOPS on TPU v5e, 6.6–7.3× FlashAttention-2 speedup, 2.85× decode speedup, −64.9% energy/token — explicitly disclosed in its own abstract as "under high-fidelity **simulation**."

- [ ] This is the most honestly-framed of the four (it discloses "simulation" up front), but `scripts/run_benchmarks.sh --simulate-tpu` needs to be confirmed to actually produce these exact figures when run. If it produces different or placeholder numbers, correct the paper or the script.
- [ ] Downstream summaries (`xavier_publications.tex`, `paper/quarantine/peer_review_report.md`) drop the "simulation" qualifier when repeating these figures — fix wherever this paper's numbers are cited elsewhere to retain the qualifier, or promote to a real-hardware result if TPU v5e access is obtained and the run is actually performed.
- [ ] Confirm the "open-source benchmark evaluation dataset" and the "private GitHub repository for rigorous artifact replication" mentioned in the abstract actually exist and are linked; if not, remove that sentence.

### `peer_review_report.md`
- [ ] Either identify and name the actual independent reviewers (if this review is real), or relabel this document honestly as an internal self-assessment / AI-assisted red-team pass rather than "Peer-Review," and remove the "Board of Reviewers" framing.

---

## Process note

None of the above is a claim that the underlying ideas (PolarQuant quantization, WARS scheduling, systolic TPU tiling, RCU-style safety arguments) are wrong — only that this repository, as audited on 2026-09-26, does not contain the artifacts needed to reproduce the specific numbers published about them. The bar for moving a document out of quarantine is: a script or dataset checked into this repository (or a linked, accessible external one) that a third party can run to reproduce the cited figure, or a corrected figure/claim that such a script does produce.
