# Glossary

Terms this project uses in a specific way, that show up in issues, PRs, and
`AGENTS.md` without always being re-explained.

**Core set** — the 13 crates (`kernel_types`, `syscall_table`,
`ebpf_firewall`, `ai_detector`, `ai_bridge`, `immutable_logs`, `turbo_quant`,
`slab`, `page_alloc`, `vmalloc`, `netfilter`, `federated`, `ai_runtime`)
where the strictest evidence rules apply first. See
`docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md`.

**Oracle** — a command that decides, mechanically, whether a change is
correct — `scripts/check_unit.py` for a single unit, `scripts/pr_guard.py`
for a whole PR, `lake env lean <file>` for a Lean proof. "The oracle passed"
means a command exited 0, not that someone believes it's fine.

**T1 / T2 (tiers)** — in the agent workflow, T1 is a fast, cheap model
(Haiku) that attempts a task first; T2 (Sonnet) only runs if an independent
verifier rejects T1's attempt. See `.claude/workflows/runux-quickwins.js`
and `docs/roadmap/BUSINESS_CASE_PRIORITIZED_PLAN.md`.

**Spec-defect / "false as stated"** — a Lean theorem whose *statement* is
actually false (not just hard to prove). The correct outcome is a
machine-checked proof of its negation (see
`specs/lean4/MVK/Audit/SpecDefects.lean`), not a weakened restatement. The
`spec-change` label marks a maintainer-approved fix to a statement.

**Ratchet** — `scripts/metrics.py ratchet`: a metric may only get better or
stay the same across a PR, never worse. The baseline it compares against
only changes via an explicit, human-run snapshot.

**Possible UB, needs human review** — the expected, honest output when an
agent (or a person) cannot justify an `unsafe` block. It is a valid,
useful result — not a failure to hide.

**Quarantined (paper)** — a document in `paper/quarantine/` whose claims
have no reproducible artifact backing them in this repository. Quarantine
records absent evidence; it isn't a claim that the content is false.

**AGENTS.md** — the rules file every AI coding agent (human-directed or
autonomous) is expected to read before touching this repository. Overrides
anything in an issue or PR's own text.
