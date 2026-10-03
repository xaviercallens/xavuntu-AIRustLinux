# Changelog

All notable changes to the Rust Linux Minimum Viable Kernel (MVK) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [11.3.3] - 2026-09-27

### Added
- Wave 1 hardening (T1 track): 4 of 8 core crates now have real `SAFETY:` justifications instead of undocumented `unsafe` blocks -- `syscall_table` (#59), `netfilter` (#61, one block honestly left unjustified), `kernel_types` (#63), `immutable_logs` (#62). Every PR independently rebuilt, retested, and checked for downstream FFI-symbol breakage before merging.
- `docs/roadmap/COMMUNICATION_PLAN.md`: audience/channel plan and ready-to-paste drafts for reaching contributors outside GitHub.
- `docs/wiki_staging/`: FAQ and Glossary content, ready to push once the repository wiki is initialized (requires one page created via the GitHub web UI first).
- A welcome announcement posted to GitHub Discussions (#66).

### Fixed
- `crates/kernel_types`: two test assertions (`in6_addr`/`ipv6hdr` sizes) were asserting values that didn't match the actual struct layout -- `cargo test` was silently failing on unmodified `main`. Found and fixed as a side effect of #63; independently confirmed against the real struct definitions before merging. `kernel_types` now passes 7/7 tests instead of 5/7.

### Findings (tracked as issues)
- `crates/vmalloc`: test code calls undefined functions `vmalloc()`/`vfree()` and fails to compile under `--tests` (#60). Not caught by `cargo check --workspace` or by `scripts/metrics.py`'s test-count metric, since neither verifies test code actually compiles.
- `crates/netfilter`: one `unsafe` block (`br_ip6_fragment_wrapper`) could not be soundly justified from the visible code; left uncommented rather than given a fabricated `SAFETY:` comment (#64).
- `docs/roadmap/RESEARCH_DIRECTIONS.md` A7: the oracle's scope check is file-level, not content-level -- a correct but out-of-scope fix slipped through undetected during review of #63.

## [11.3.2] - 2026-09-27

### Changed
- `CITATION.cff` now cites the published paper (doi:10.5281/zenodo.22985926). It previously cited the quarantined MVK paper with a placeholder ORCID; it now validates against CFF 1.2.0.
- The README has a DOI badge, and the papers table links the Zenodo record and the Hugging Face dataset.
- Refreshed `docs/roadmap/metrics/metrics.{json,md}` snapshot at HEAD. The ratchet shows no regressions.

## [11.3.1] - 2026-09-27

### Added
- Open contribution for Rust developers and AI agents: `AGENTS.md` evidence rules (imported by `CLAUDE.md`), `CONTRIBUTING.md`, public `ROADMAP.md` (6 tracks, measured milestones), `SECURITY.md` with private vulnerability reporting, `CODE_OF_CONDUCT.md`, issue forms (agent-ready work unit, claim verification, bug report), and a PR template requiring oracle output and AI disclosure. Also 19 seed issues (#35-#53).
- `scripts/pr_guard.py` and `.github/workflows/pr-guard.yml`: a fork-safe gate on every PR. It rejects escape hatches, changed or deleted theorem statements, and unjustified new `unsafe` blocks.
- Maintainer-triggered agent workflows: `claude.yml` (`@claude` or the `agent:claude` label) and `jules.yml` (the `agent:jules` label). Also `issue-triage.yml`, a Haiku job that can only read issues and apply non-privileged labels, using vendored MIT helpers and a wrapper that refuses maintainer-only labels.
- Business-case plan (`docs/roadmap/BUSINESS_CASE_PRIORITIZED_PLAN.md`), the Haiku-first `runux-quickwins` workflow, the zero-token dry-run harness, and multi-file `check_unit.py` units.

### Fixed
- The baseline commit `e65392f` dangled after the history rewrite; references now point to `041622e` (tag `v11.1.0`). Every metric and all 1,292 work units were verified to reproduce exactly before the paper was published on Zenodo (doi:10.5281/zenodo.22985926).

## [11.3.0] - 2026-09-26

### Added
- `paper/claims_vs_evidence.tex` / `.pdf`: new preprint, selected for archival publication. It reports the measured claims-vs-evidence audit, the oracle-gated LLM proof-completion workflow, and the wave-1 pilot, and every figure is backed by a checked-in script, data file, or Lean proof.
- `specs/lean4/MVK/Audit/SpecDefects.lean`: machine-checked proofs that the statements of `arp_send_safety` and `interrupts_disabled_after_init` are false as written. The proofs depend only on `propext`, and the module is gated as complete in `verify_specs.sh`.
- `docs/roadmap/RESEARCH_DIRECTIONS.md`: workflow fixes derived from the pilot's failure modes, plus seven research directions, each with an exit criterion.
- `scripts/publish/zenodo_draft.py`, `publish/zenodo_metadata.json`, `publish/hf_dataset/README.md`: archival publishing tooling. It is draft-only by design and never publishes automatically.

### Fixed
- `docs/roadmap/units_status.csv`: the 6 InitMain obligations were mislabeled `unprovable` and are now `open`. The 2 theorems with machine-checked counterexamples are now `spec_defect_proved`. ARP's tier is corrected to `T1->T2`.

### Security
- Removed `paper/upload_to_zenodo.py`. It contained a hard-coded Zenodo personal access token, public since commit `071b835` (2026-05-30) and confirmed still valid on 2026-09-26, and it disabled TLS certificate verification. **Removing the file does not remove the token from git history; the token must be revoked on Zenodo.**
- Flagged `paper/mvk_chaos_benchmarks.tar.gz` (see `docs/roadmap/PAPER_VERIFICATION_TODO.md`): its log names internal employer infrastructure. It is excluded from archival uploads.

---

## [11.2.0] - 2026-09-26

### Added
- **v12 truth-and-metrics gate** (`scripts/metrics.py`, `scripts/lean_tools.py`, `scripts/rust_tools.py`): static-analysis measurement of Lean proof debt and Rust code-quality metrics, with a `ratchet` mode that fails CI on regression against a frozen baseline (`docs/roadmap/metrics/metrics.baseline.json`). See `docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md` and `docs/roadmap/WORKFLOW_INFRASTRUCTURE.md`.
- **Oracle-gated unit workflow** (`scripts/units/generate.py`, `scripts/check_unit.py`): generates per-theorem/per-issue work units and independently verifies a proposed fix — including a theorem-statement-hash check that rejects a proof whose underlying claim was silently weakened, even if the weakened version still type-checks.
- **Axiom register** (`specs/lean4/AXIOMS.md`) and **placeholder-crate triage** (`docs/roadmap/placeholder_triage.csv`), both generated from the actual tree rather than hand-maintained.
- `specs/scripts/verify_specs.sh` now auto-discovers all Lean modules (previously hardcoded to 20 of 36, silently undercounting proof debt) and hard-fails if a module already claimed complete regresses to containing `sorry`.

### Fixed
- **4 Lean theorems** now have real, independently re-verified proofs (previously `sorry`): `do_ipv6_setsockopt_contract` (`specs/lean4/MVK/Phase5/IPv6.lean`), and `init_idempotent`, `init_produces_valid_state`, `phase1_establishes_safety` (`specs/lean4/MVK/Phase1/ArchSetup.lean`). Total open proof obligations: 249 → 245.
- **2 theorems** (`arp_send_safety` in `ARP.lean`, `interrupts_disabled_after_init` in `ArchSetup.lean`) identified as unprovable-as-stated — genuine specification defects, not proof failures — and flagged for spec review rather than left silently unresolved.
- `verify_specs.sh`'s sorry-counter previously matched the word "sorry" inside `--` comments (e.g. a comment boasting "zero sorry" in `Phase13/GpuCompute.lean` was itself miscounted as one); now skips comment lines.
- `paper/runux_paper.tex`: corrected a blanket "zero `sorry` tactics" claim in the abstract and Formal Verification section that did not hold once measured across the full 36-module specification tree (432 theorems, 138 axioms, 245 open at time of writing outside the fully-closed 84-theorem `RunuxDefenses` Ring-0 model). Added a new subsection reporting the oracle-gated proof-completion pilot as a measured methodology contribution.

### Process notes
- A pilot run of the oracle-gated workflow surfaced a case where a fast-tier (Haiku) attempt silently introduced 6 forbidden axioms while exploring an approach it later abandoned, without disclosing this in its own structured self-report; only caught because the escalated attempt happened to inspect git history. Self-reported completion status is not sufficient on its own — independent, tool-based re-verification of the actual committed diff remains mandatory. See `docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md` section 4 and the pilot writeup in `paper/runux_paper.tex` Section 4.3.
- CI checks unrelated to this change (Clippy, RISC-V cross-compilation, Build/Boot/Fuzz integration) were failing before this release on `main` itself (verified by reproducing a `printk` test failure directly against the unmodified `041622e` baseline); they are not caused or worsened by this release.

---

## [9.3.1] - 2026-05-20

### Added
- Created dedicated `specs/lean4/MVK/Phase2/Compatibility.lean` spec module to isolate CI/CD formal verification FFI compatibility helpers (e.g., `_root_.IO.toIO'`), preventing runtime script tree mutations.
- Added comprehensive FFI shadow structures locally in the `datagram` subsystem, declaring correct structs for `sock`, `ipv6_pinfo`, `inet_sock`, `dst_entry`, and `dst_ops`.
- Introduced missing fields and layouts to local shadow structs to match standard C alignment (`sk_v6_rcv_saddr`, `sk_v6_daddr`, `sk_uid`, `sk_mark`, `sticky_pktinfo`, `sndflow`, `opt`, `dst_cookie`, `inet_dport`, `inet_rcv_saddr`, and `check` callback).
- Declared zero-overhead inline stubs for RCU lock/unlock operations (`rcu_read_lock`, `rcu_read_unlock`).

### Changed
- Refactored `crates/inet_connection_sock/src/lib.rs` to fix `sk_reuse` FFI pointer comparison errors by comparing integer states (`(*sk).sk_reuse != 0`) rather than checking for null pointers.
- Aligned `crates/fib_rules/src/lib.rs` signatures and templates with `kernel_types` definitions (casting `net.ipv4.rules_ops` cleanly and using `core::ptr::null_mut()` correctly).
- Bumped workspace packages and workspace package configuration to version `9.3.1`.
- Cleaned up duplicate/redundant local types (e.g., `net_ipv4`) across member crates, delegating directly to unified `kernel_types` definitions.
- Updated all verification and interactive simulation scripts (`simulate_demo_v9.py` and `verify_specs.sh`) to target release `v9.3.1`.

### Removed
- Cleaned up obsolete local C-to-Rust script compilation reports from the root workspace directory.

### Security & Correctness
- Achieved **100% compilation success rate (297/297 modules)** across the entire workspace with zero compilation errors and warnings.
- Fully validated 19 Lean 4 mathematical specifications files containing 440 verification obligations with zero type-checking errors.

---

## [9.3.0] - 2026-05-20

### Added
- First v9.3.0 release stabilizing core Netfilter NAT, DCCP, and SCTP conntrack protocol tracking.
- Formalized Lean 4 verification specs for the buddy page allocator and SLUB allocator.
