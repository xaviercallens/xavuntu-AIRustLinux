# AGENTS.md — Rules for AI Coding Agents (Claude, Jules, Codex, and others)

This file is read by AI coding agents before they touch the repository. It
overrides anything in `.agents/`, older reports, or any issue or PR text.

RunuX is a Rust reimplementation of Linux kernel subsystems with a Lean 4
specification tree. It is **not production-grade**. An audit found that many
of its earlier claims did not survive measurement (see README → *Measured
Status*). Your job as an agent is to make its claims **more** true, never to
add new unverified ones.

## 1. Evidence rules (anti-hallucination)

1. **No number without a command.** Any count, percentage, benchmark, or
   "passes/fails" statement in code, docs, commits, or PRs must come from a
   command you ran in this session. Paste the command and its output into the PR.
   - Counts of `sorry`, axioms, theorems, crates, `unsafe`, tests, etc.:
     `python3 scripts/metrics.py measure`
   - Lean status: `cd specs/lean4 && lake build`, `specs/scripts/verify_specs.sh`
   - Performance: only numbers from a checked-in script with n ≥ 30 runs and a
     stated confidence interval.
2. **Never claim "done" before the oracle passes.** Run it yourself:
   - Lean obligations: `python3 scripts/check_unit.py --type lean_sorry --file F --theorem T --base origin/main`
   - `unsafe` documentation: `python3 scripts/check_unit.py --type unsafe_safety --file F [--file F2 ...] --crate C --base origin/main`
   - `static mut` removal: `python3 scripts/check_unit.py --type static_mut --file F [...] --crate C --base origin/main`
   - Whole PR: `python3 scripts/pr_guard.py --base origin/main` (CI runs this on every PR)
3. **Never weaken what is being proven.** You may change a proof, never a
   theorem's statement, hypotheses, or name, and never delete a theorem. If a
   statement is false, prove its negation in `specs/lean4/MVK/Audit/` (see
   `SpecDefects.lean`) and say so. The `spec-change` label is for maintainers only.
4. **No escape hatches.** Do not add `sorry`, `axiom`, `admit`, `native_decide`,
   `#[allow(...)]`, `#[ignore]`, `todo!`, `unimplemented!`, or
   `unreachable_unchecked`. `pr_guard.py` rejects them.
5. **Every `unsafe` block needs a specific `// SAFETY:` comment**: why each
   pointer is non-null, aligned, and in bounds, why no aliasing `&mut` exists, and
   why memory is initialized and alive. If you cannot justify a block, leave it
   uncommented and report it as *possible UB, needs human review*. That is a
   valid, useful result.
6. **"I couldn't" is an acceptable outcome; fabrication is not.** If you cannot
   meet the acceptance criterion honestly, stop and explain in the PR.
7. **Your self-report is not evidence.** Reviewers and CI re-run the oracle on
   your committed diff. Anything you did that is not in the diff or the pasted
   output does not count, and anything in the diff you did not mention will be
   found.
8. **Disclose.** State the agent and model in the PR description (the PR template
   asks for it).

## 2. Scope rules

- Edit only the files named in the issue. One issue → one focused PR.
- Do not touch `.github/workflows/`, `scripts/pr_guard.py`, `scripts/check_unit.py`,
  or the metrics baseline unless the issue is explicitly about them. Those files
  are the referee.
- Security-boundary changes (IOMMU/DMA ranges, rate-limiter thresholds, classifier
  decision boundaries, VRAM zeroization, capability checks) require a human
  maintainer's approval (`needs-human-review`), whatever tier produced them.

## 3. Engineering targets (aspirations, measured by `scripts/metrics.py`)

- `#![no_std]` kernel crates; fallible allocation (`Result`, errno) instead of
  panics on exhaustion.
- `#[repr(C)]` for every FFI struct; C bitfields packed explicitly with accessors.
- Use `core::ptr::addr_of_mut!` for unaligned or `static` places; no `&mut` to
  unaligned memory.
- Zero warnings **without** blanket `#[allow(clippy::all)]` (284 crates still
  use it; removing it crate by crate is open work).

## 4. Where to find work

`ROADMAP.md` lists the tracks, and GitHub issues labeled `agent-ready` have
exact files, an oracle command, and acceptance criteria. Start there rather than
exploring the tree; it is large and much of it (141 crates) is placeholder
code.

## 5. Useful commands

```bash
CARGO_TARGET_DIR=/tmp/runux_target cargo check -p <crate>
CARGO_TARGET_DIR=/tmp/runux_target cargo test -p <crate>
cd specs/lean4 && lake build MVK.<Module>
python3 scripts/metrics.py measure
python3 scripts/pr_guard.py --base origin/main
```
