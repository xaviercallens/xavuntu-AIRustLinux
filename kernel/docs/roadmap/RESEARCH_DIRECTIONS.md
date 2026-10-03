# Research Directions & Workflow Improvements

Derived from the wave-1 pilot (`docs/roadmap/units_status.csv`) and the
paper `paper/claims_vs_evidence.tex` §6–§9. Each item states the
evidence that motivates it and a measurable exit criterion.

---

## A. Immediate workflow fixes (next wave, low cost)

| ID | Fix | Motivating evidence | Exit criterion |
|---|---|---|---|
| A1 | Run `scripts/check_unit.py` as a **required CI job** on every `fix/*` branch, independent of the agent | F3: T1 committed 6 forbidden axioms and omitted them from its report; only incidental `git log` inspection by T2 caught it | CI job blocks merge; red-team test (A5) shows 100% of injected cheats rejected |
| A2 | A "false as stated" verdict is accepted **only with a checked proof of the negation** (as in `specs/lean4/MVK/Audit/SpecDefects.lean`) | F2: T1 labeled 6 hard-but-plausible InitMain theorems "unprovable"; the label survived escalation | Zero unbacked "false" labels in `units_status.csv` |
| A3 | Escalate only when `failed` is non-empty; otherwise finalize at T1 | F1: ARP escalated with nothing to retry | 0 wasted escalations per wave |
| A4 | T2 re-triages all T1 verdicts, not just `failed` | F2 persisted because T2 was told not to revisit | Measured re-triage flip rate reported per wave |
| A5 | Red-team corpus for the oracle: weakened statements, smuggled `axiom`, `native_decide`, out-of-scope edits | The anti-weakening hash was tested on 3 synthetic cases only | ≥ 30 injected cases, detection rate reported |
| A6 | Record per-unit tokens, wall time, and attempts automatically | Pilot cost could only be attributed per file, not per theorem | Per-unit cost columns in `units_status.csv` |
| A7 | Scope the oracle by content (which hunks relate to the unit's stated task), not only by file | Wave 1 (Rust hardening, 2026-09-27): a T2 escalation on `kernel_types` correctly added SAFETY comments, but also silently rewrote two unrelated test assertions (`in6_addr`/`ipv6hdr` sizes). Independently verified as a real, correct fix for a pre-existing broken test (`cargo test` failed on unmodified `main`) — not a fabrication — but `check_unit.py`'s scope check only verifies the touched *files* are in the unit's allow-list, not that each *hunk* relates to the stated task. A different agent making an equally "helpful" out-of-scope edit could be wrong instead of right, and the oracle would not catch it | A diff-hunk classifier (even a cheap one: hunks touching lines outside a declared line-range budget get flagged for human review) before merge |

## B. Research directions (publishable questions)

1. **Trustless agent pipelines.** How much of an LLM verification workflow's safety can be moved out of the agent's control loop? Metric: cheat-detection rate vs. agent-side vs. CI-side oracle placement (builds on A1, A5).
2. **Self-report fidelity.** How often do agent structured reports disagree with git ground truth, across models and task types? Metric: disagreement rate per 100 units; F3 is the first data point.
3. **Specification-defect discovery.** Is finding *false* specs a higher-value use of LLM provers on legacy specification corpora than closing `sorry`? Pipeline: property-based counterexample search → Lean negation proof. Metric: defects found per agent-hour vs. proofs closed per agent-hour (pilot: 2 defects vs. 4 proofs).
4. **Rust ↔ Lean congruence.** Extract `ai_bridge` ring buffer, `immutable_logs` Merkle log, and `ebpf_firewall` verdict merge with Aeneas or hax; restate RunuxDefenses theorems over extracted code. Metric: `lean.extracted_thm` in `scripts/metrics.py` (currently 0).
5. **Tier economics and routing.** Cost/success curves by goal class (arithmetic, inductive, monadic). Pilot signal: the monadic-I/O class needed T2 and ~139k tokens for 3 closures. Metric: expected cost per closed obligation under learned routing vs. fixed T1→T2.
6. **Executable claims.** Papers whose every number is bound to a script and content hash, with CI regenerating tables so stale claims fail the build. Metric: fraction of paper figures regenerated in CI (quarantine TODO tracks the current gap).
7. **A booted artifact and differential testing.** Link the translated crates into a bootable x86_64/riscv64 image and replace string-grep chaos checks with differential tests against Linux. Prerequisite for restoring any `runux_paper.tex` performance or resilience claim.

## C. Sequencing

1. A1–A3 before the next proof wave (small, directly derived from observed failures).
2. A5 + B1/B2 together — the red-team corpus is the measurement instrument for both.
3. B3 on the remaining 245 open obligations (triage pass before proof pass).
4. B4 and B7 are longer-horizon engineering; B6 applies to every future paper.
