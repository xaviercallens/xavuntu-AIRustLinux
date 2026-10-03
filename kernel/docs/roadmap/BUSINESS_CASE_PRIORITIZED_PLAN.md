# RunuX — Business Case and Prioritized, Token-Optimized Plan

**Status:** plan plus runnable tooling. Nothing in Waves 1–3 has been
executed yet. Supersedes the *ordering* (not the content) of
`RUNUX_V12_VERIFIED_CORE_PLAN.md`, `AI_AGENT_DEFENSE_PLAN.md`,
`STANDARD_HARDWARE_AI_GPU_PLAN.md`, and `RESEARCH_DIRECTIONS.md`.
**Baseline:** `main` at `2eca7d9`, v11.3.0.

---

## 1. Business case

### What is actually valuable here

The measured audit (`paper/claims_vs_evidence.tex`) points to one asset
that the evidence already supports. It is not the kernel. It is **the
method and tooling for verifying AI-generated systems code:**

- a static metrics ratchet that blocks regressions without a build (`scripts/metrics.py`);
- an oracle that rejects silently weakened proofs, smuggled axioms or lint suppressions, and out-of-scope edits (`scripts/check_unit.py`);
- a tiered LLM workflow in which an independent verifier, not the agent that made the change, decides what ships;
- negation-backed triage, which proved 2 of 12 pilot obligations *false as stated* (`specs/lean4/MVK/Audit/SpecDefects.lean`).

The kernel remains useful as the **testbed and demonstrator**. It is a
realistic, messy, AI-assisted codebase where the tooling has a measured
track record.

### Why now (external drivers, qualitative)

- **EU Cyber Resilience Act** (Regulation (EU) 2024/2847). Its vulnerability-reporting obligations apply from September 2026, and its main security-by-design and documentation obligations from December 2027. Evidence of how code was verified is becoming a compliance artifact.
- **Memory-safety policy push.** CISA and partner agencies published *The Case for Memory Safe Roadmaps* (Dec 2023), and the US ONCD published *Back to the Building Blocks* (Feb 2024). Both ask vendors for memory-safety roadmaps; an `unsafe` inventory with justified `SAFETY:` coverage is exactly that kind of evidence.
- **AI-generated code volume.** This repository is itself a documented example of generation outpacing verification. Every team adopting coding agents faces the same gap.

No market-size figures are claimed here. They are not measured, and this
plan does not repeat the unverified-number pattern it exists to fix.

### Offer hypotheses (to validate, cheapest first)

| # | Hypothesis | Cheapest validation | Evidence it rests on |
|---|---|---|---|
| O1 | Teams adopting AI coding agents will use (and pay support for) an open-source "claims vs. evidence" toolkit | Publish the Zenodo DOI and HF dataset, post the paper, and count inbound interest and repo adoption over 60 days | Paper, metrics tool, oracle, pilot data |
| O2 | Rust/embedded vendors need a memory-safety evidence pack (unsafe inventory, `SAFETY:` coverage, Miri results) for roadmaps and CRA files | Run Wave 1 on RunuX's core set and publish the before/after evidence pack as a worked example | Wave 1 output (§4) |
| O3 | Open-source security funders will fund the tooling | Apply to programs that fund open infrastructure, e.g. NLnet NGI and the Sovereign Tech Agency. Eligibility must be checked, not assumed | Paper, artifacts, CRA/memory-safety alignment |

**Not viable to sell now:** RunuX as a production kernel, and GPU/TPU or
performance claims. Both lack evidence (see `PAPER_VERIFICATION_TODO.md`).

### Business KPIs (what the pitch will cite)

| KPI | Source | Baseline |
|---|---|---|
| Core-set `SAFETY:` coverage | `scripts/metrics.py` restricted to the core set | 101 undocumented blocks across 8 crates |
| Core-set `static mut` | same | 10 |
| Specification defects found per agent-hour | `units_status.csv` + workflow usage | Pilot: 2 defects in about 34 min of wall-clock time |
| Independent-verification pass rate | verifier results | new in Wave 1 |
| Tokens per verified unit | workflow usage report | new in Wave 1 |
| Human review minutes per PR | reviewer log | new in Wave 1 |
| External signal | Zenodo/HF download counts, inbound contacts | 0 (not yet published) |

---

## 2. Prioritization method

`score = Impact (1–5) × Confidence (0–1) ÷ Effort`, where Effort is
estimated agent tokens plus human review minutes. **Low effort / high
impact goes first.** Token estimates come from the measured wave-1 Lean
pilot:

| Measured pilot agent | Model | Tokens |
|---|---|---|
| T1 file with 1 trivial theorem (ARP) | Haiku | 30.7k |
| T1 file with 5–6 theorems | Haiku | 49.6k–96.9k |
| T2 escalation | Sonnet | 43.9k–139.2k |
| Bookkeeping agent (append a CSV) | Sonnet | 46.9k (**waste**: now a script) |
| T2 escalation with nothing to retry (ARP) | Sonnet | 43.9k (**waste**: fixed by rule A3) |

Wave 1 involves mechanical Rust edits rather than proofs. Its per-unit
cost is **unknown until the pilot run** in W0.5. The ranges below are
estimates to be replaced by measurements.

---

## 3. Ranked backlog

### Wave 0 — near-zero agent tokens (do first)

| ID | Item | Impact | Effort | Who |
|---|---|---|---|---|
| W0.1 | Revoke the leaked Zenodo token (still live at last check) | 5: credibility blocker for any business use | 2 min | Human |
| W0.2 | Publish the Zenodo draft (DOI `10.5281/zenodo.22985926`) and make the HF dataset public | 5: first citable, external asset (O1) | 5 min | Human |
| W0.3 | Add a CI job that runs `check_unit.py` on every `qw/*`/`fix/*` PR (fix A1 from `RESEARCH_DIRECTIONS.md`) | 5: closes the trust gap the pilot exposed | ~20 lines of YAML; must be pushed by a human, because the current token lacks `workflow` scope | Human push |
| W0.4 | Replace the LLM bookkeeping agent with `scripts/units/record_results.py` | 3: saves about 47k tokens per wave | **Done** (this change) | — |
| W0.5 | Pilot calibration: `runux-quickwins` with `{"pilot": true}` (2 smallest crates, 3 sites) | 4: turns the estimates below into measurements | Estimated 0.1–0.2M tokens | Workflow |

### Wave 1 — Haiku-first hardening of the core set (high impact, low effort)

| ID | Item | Units | Model | Oracle | Est. tokens |
|---|---|---|---|---|---|
| W1.1 | **`runux-quickwins`**: `SAFETY:` comments on 101 undocumented `unsafe` blocks and removal of 10 `static mut`, in 8 core crates | 8 crate units (111 sites) | Haiku fix + Haiku verifier; Sonnet only on failure | `check_unit.py` (multi-file), `cargo check`/`cargo test` | 0.4–1.0M (estimate) |
| W1.2 | Fix the known aliasing bug `ai_detector::activation_slice(&self) -> &mut` | 1 | Sonnet (soundness judgment) | `cargo test -p ai_detector`, plus `cargo miri test -p ai_detector` where it runs | ~50–150k |
| W1.3 | Remove blanket `#[allow(clippy::all)]` in 4 core crates (`kernel_types`, `syscall_table`, `netfilter`, `ai_runtime`) | 4 | Haiku | `cargo clippy -p X -- -D warnings` | Size first with a deterministic clippy run (0 tokens) |
| W1.4 | Re-run the CRC32 benchmark with n ≥ 30 and a confidence interval; keep or retract the "4.73% faster" claim | — | none (script) | Welch test | 0 agent tokens |

After Wave 1, the "zero warnings" and "documented `unsafe`" claims become
**true for the core set** rather than true by suppression. That is the O2
evidence pack.

### Wave 2 — Research value (Haiku triage, Sonnet only on candidates)

| ID | Item | Model | Token strategy |
|---|---|---|---|
| W2.1 | Negation-backed triage of the 245 open `sorry`: classify each **statement only** as likely-false / arithmetic / inductive / monadic | Haiku, about 25 statements per agent (~10 agents) | Statement text only, no proof context |
| W2.2 | Try a machine-checked disproof (as in `SpecDefects.lean`) only for "likely false" candidates | Sonnet | Oracle: `lake build MVK.Audit.*` and `#print axioms` showing only standard axioms |
| W2.3 | Close arithmetic-class `sorry` (`omega`/`decide`/`simp`) | Haiku, one agent per file | Existing `lean_sorry` oracle with the statement-hash check |

The pilot rate was 2 false out of 12 real obligations. That sample is too
small to extrapolate, and measuring the real rate is itself a publishable
result (`RESEARCH_DIRECTIONS.md` B3).

### Wave 3 — Deferred until O1–O3 show traction

v12 WS5 bootable image; `STANDARD_HARDWARE_AI_GPU_PLAN.md` (virtio-gpu first);
`AI_AGENT_DEFENSE_PLAN.md` load bench and CFI; Aeneas/hax extraction. These
are high-effort, multi-wave efforts. Starting them before a business signal
exists would spend the most tokens on the least-validated bets.

---

## 4. Token-optimization rules (apply to every workflow)

1. **Precompute the work list.** Pass exact files and line numbers in `args` or the script default, so agents never explore the codebase. Measured prompt size: about 320–600 tokens per agent in `runux-quickwins`.
2. **Use one agent per crate or file, not per site,** and merge unit types that touch the same file to avoid parallel branch conflicts (Wave 1: 8 agents, not 111).
3. **Default to Haiku with `effort: 'low'`.** Use Sonnet only on an oracle failure (rule A3) and only for soundness or protocol judgment.
4. **Use small read windows.** Agents read about 25 lines per site (`sed -n`), never whole files; `slab/src/lib.rs` alone is 1,134 lines.
5. **The independent verifier is cheap and mandatory.** It is a Haiku agent that only runs commands, computes the diff base itself (it never trusts the fixer), and alone may push or open a PR.
6. **Nothing that a script can do goes to an agent.** Examples: bookkeeping (`record_results.py`), sizing (`rust_tools.py`), and benchmarks (W1.4).
7. **Use at most 2 T1 attempts for mechanical edits.** A third attempt rarely helps with comments or atomics.
8. **Dry-run every workflow at zero tokens first,** executing it in Node with a mocked `agent()` (see §5), to validate control flow before spending anything.
9. **Pilot before fan-out.** Run `{"pilot": true}` on the 2 smallest units, read the usage report, then scale.

---

## 5. Running Wave 1

The workflow is saved at `.claude/workflows/runux-quickwins.js`. Its default
work list is the core set measured on 2026-09-27. Regenerate it before reuse,
because line numbers drift.

```text
# 1. zero-token dry run (control flow + prompt sizes)
node scripts/workflows/dryrun.js .claude/workflows/runux-quickwins.js

# 2. calibration pilot (2 smallest crates)
Workflow({ name: "runux-quickwins", args: { pilot: true } })

# 3. full wave after reviewing pilot PRs and token usage
Workflow({ name: "runux-quickwins" })

# 4. record results deterministically (no agent)
python3 scripts/units/record_results.py <workflow-result.json>
```

Every PR it opens has already passed `check_unit.py` in a worktree the fixer
never touched. "Partial" PRs list each `unsafe` block the agents could not
justify as **possible UB, needs human review**. Those blocks are findings,
not failures.

## 6. Exit criteria for this plan

- W0.1–W0.3 done. Human actions are tracked, not assumed.
- W1.1–W1.4 merged: core-set `SAFETY:` coverage at 100% (or every remaining block listed as possible UB), core `static mut` = 0, no blanket `allow` in the core set, and the CRC32 claim resolved.
- One measured number each for tokens per verified unit and human minutes per PR, so the O1/O2 pitch uses measurements, not estimates.
