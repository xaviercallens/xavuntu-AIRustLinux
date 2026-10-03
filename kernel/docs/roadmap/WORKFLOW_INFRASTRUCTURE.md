# v12 Workflow Infrastructure

**Status:** infrastructure only. No kernel code, no Lean proofs, and no
stub implementations were changed by this PR. It builds the tooling that
`docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md` (section 4) describes for
driving the actual fixes with low-tier models under an oracle gate.

Scope was deliberately kept to tooling rather than starting on the ~1,400
individual fixes the plan identifies (249 `sorry`, 259 constant-body stub
functions, 664 undocumented `unsafe` blocks, 197 `static mut`, 141
placeholder crates). Doing those through this same PR would produce either
a wall of low-quality mass edits or a PR nobody can meaningfully review.
This PR instead makes the fixes mechanically checkable and trackable, so
they can land in small, independently-reviewable PRs afterward.

## What's here

| File | Purpose |
|---|---|
| `scripts/lean_tools.py` | Parses `specs/lean4/MVK/**/*.lean`: counts `sorry`/`axiom`/`theorem`, extracts each theorem's statement and a hash of it (for the anti-weakening check). No Lean toolchain required. |
| `scripts/rust_tools.py` | Parses `crates/*/src/**/*.rs`: counts `unsafe` blocks/fns, `SAFETY:` comments, `static mut`, blanket `#[allow(clippy::all)]`, stub markers, constant-body `extern "C" fn`s, crate LOC. No cargo required. |
| `scripts/metrics.py` | `measure` / `snapshot-baseline` / `ratchet` subcommands. Computes the metrics from the plan's section 2, and fails (exit 1) if a PR makes any of them worse relative to `docs/roadmap/metrics/metrics.baseline.json`. |
| `docs/roadmap/metrics/metrics.baseline.json` | Frozen snapshot at commit `041622e` (v11.1.0), the plan's measured baseline. Only changes via a human-run `snapshot-baseline`, never automatically. |
| `.github/workflows/metrics-ratchet.yml` | Runs `metrics.py measure` + `ratchet` on every PR and push to `main`. |
| `scripts/units/generate.py` | Generates oracle-checkable "unit cards" (JSON) for four work types: `lean_sorry`, `unsafe_safety`, `static_mut`, `placeholder_triage`. Cards are fully reproducible from the tree and are **not** bulk-committed (see `.gitignore`); only `docs/roadmap/units_summary.json` (counts) and a hand-picked example set under `docs/roadmap/units/examples/` are committed. |
| `scripts/check_unit.py` | The oracle + anti-cheat gate a work-unit PR must pass (see below). Stdlib-only, no third-party deps. |
| `scripts/units/triage_placeholders.py` | Applies the plan's *explicit* IMPLEMENT/MERGE/REMOVE rules to the 141 placeholder crates and emits `docs/roadmap/placeholder_triage.csv`. Everything not covered by an explicit rule is marked `REVIEW`, not guessed. |
| `scripts/units/emit_axioms.py` | Enumerates every Lean `axiom` into `specs/lean4/AXIOMS.md` as `NEEDS-REVIEW`, for goal G3 (axiom count <=30, each justified). |
| `specs/scripts/verify_specs.sh` | Fixed to auto-discover all 36 `.lean` files (it previously hardcoded 20, silently missing Phase5–13 and QuantumLTN) and to hard-fail if any module on the `COMPLETE_MODULES` list regresses to containing `sorry`. |

## Why static analysis, not a real build

`metrics.py`, `rust_tools.py`, and the unit generator do not invoke `cargo`
or `lake`. That's deliberate for this layer: it makes the ratchet cheap
enough to run on every PR, and it means the workflow doesn't need a full
toolchain to decide which units exist. The *oracle* for an individual unit
(`check_unit.py`) does invoke the real tool (`lake env lean` for
`lean_sorry`, `cargo check`/`cargo test` for the Rust unit types) — static
analysis decides what to check, the real toolchain decides if it's
correct.

## Measured vs. generated counts

`scripts/metrics.py measure` and `scripts/units/generate.py --summary-only`
use different counting rules on purpose and will not match exactly:

- `metrics.py`'s `lean.sorry` is a raw token count (249 at baseline).
- `generate.py`'s `lean_sorry` unit count groups by *theorem* (290 at
  baseline) — a theorem's 40-line window can contain more than one `sorry`,
  or (rarely) misattribute a nearby theorem's `sorry`. This is a documented
  heuristic in the generator; it only affects work assignment, not
  correctness, because every unit's actual pass/fail still comes from a
  real `lake env lean` run, not from the heuristic.

## The oracle + anti-cheat gate (`check_unit.py`)

For every unit type it checks two things:

1. **Scope**: the PR's diff (against `--base`, default `origin/main`) only
   touches files listed in the unit's `allowed_edits`.
2. **Anti-cheat**: the diff introduces none of: a new `sorry`, a new
   `axiom`, a new `allow(...)`, `#[ignore]`, `todo!()`, `unimplemented!()`,
   `unreachable_unchecked`, `native_decide`, or `admit`.

Then a type-specific oracle:

- `lean_sorry`: the named theorem no longer contains `sorry`, its
  **statement hash is unchanged** (a theorem that still type-checks after
  someone weakens its statement — e.g. adding a spurious hypothesis — is
  rejected; a real fix to a wrong statement must be escalated with a
  `spec-change` tag instead), and `lake env lean <file>` succeeds.
- `unsafe_safety`: every `unsafe {` in the file has a `SAFETY:` comment in
  the preceding 5 lines, and (if `--crate` given) `cargo check -p <crate>`
  passes.
- `static_mut`: no `static mut` remains in the file, and (if `--crate`
  given) `cargo test -p <crate>` passes.

All three paths (fails on unfixed `sorry`, passes on a real proof, rejects
a silently weakened statement) were exercised against a disposable `git
worktree` during development of this PR — not against tracked project
files — see the PR description for the transcript.

### A concrete example of what this catches

`docs/roadmap/units/examples/lean_sorry/..._arp_send_safety.json` targets
`arp_send_safety` in `specs/lean4/MVK/Phase4/ARP.lean`. That theorem's
statement is:

```
theorem arp_send_safety (skb) (ip) (result: Int) (h_pre: ...)
  : result <= 0
```

`result` is universally quantified and nothing in the hypotheses
constrains it — the statement is unprovable as written, independent of any
tactic. This is exactly the "sorry sits on a false or ill-posed theorem"
risk the plan calls out (section 7): a low-tier model should burn its 3
attempts, fail the oracle honestly, and escalate to T2 → T3 rather than
being pushed toward finding a way to make it "pass." No mechanical fix
exists here; the statement itself needs review.

## Placeholder triage results (`docs/roadmap/placeholder_triage.csv`)

Of the 141 placeholder crates (<=25 LOC):

| Decision | Count | Basis |
|---|---:|---|
| IMPLEMENT | 20 | named in the plan's boot-critical list |
| MERGE | 31 | matches the plan's `sys_*`/`driver_base_*`/`driver_block_*`/`driver_char_*`/`driver_tty_*` rule |
| REMOVE | 13 | matches the plan's `ext4_*`/`ipc_*`/`swap*`/`security_key*` rule |
| REVIEW | 77 | not covered by an explicit rule — needs a human/T3 decision, not a guess |

The plan itself says this triage needs a human call (section 8, item 5);
the script only mechanizes the parts that were already decided.

## How to run this locally

```bash
# Metrics
python3 scripts/metrics.py measure          # writes docs/roadmap/metrics/metrics.{json,md}
python3 scripts/metrics.py ratchet           # compares live tree against the committed baseline

# Regenerate derived docs
python3 scripts/units/triage_placeholders.py # docs/roadmap/placeholder_triage.csv
python3 scripts/units/emit_axioms.py         # specs/lean4/AXIOMS.md
python3 scripts/units/generate.py --summary-only   # docs/roadmap/units_summary.json

# Check one work unit (example: a hypothetical fixed ARP proof)
python3 scripts/check_unit.py --type lean_sorry \
  --file specs/lean4/MVK/Phase4/ARP.lean --theorem arp_send_safety \
  --base origin/main
```

## What this PR does *not* do

- Does not fix any of the 249 `sorry`, 259 stub functions, 664
  undocumented `unsafe` blocks, or 197 `static mut`.
- Does not act on any placeholder-crate decision (IMPLEMENT/MERGE/REMOVE)
  — the CSV is a proposal, not an executed change.
- Does not add Aeneas/hax/Kani (WS4) or touch boot code (WS5).
- Does not change `AGENTS.md`/`README.md` claims — that's a follow-up once
  the ratchet has run for a while and the numbers it reports are trusted.

Those are the next PRs, each sized to the plan's per-unit DoD (~300 lines,
oracle-gated, no ratchet regression).
