# Contributing to RunuX

**Wanted: Rust developers, Lean provers, kernel and security engineers, and
people running AI coding agents who want them to produce work that holds up.**

## Why this project, why now

Three problems are converging:

1. **Kernels and infrastructure remain mostly memory-unsafe.** Regulators now
   ask for evidence of how code is secured: the EU Cyber Resilience Act, and
   the memory-safety roadmap guidance from CISA and partner agencies.
2. **AI agents generate code, proofs, and papers faster than anyone checks
   them.** This repository is a documented example. An audit found inflated
   claims, placeholder crates counted as "modules", fake demo recordings, and
   an agent that quietly added forbidden axioms and left them out of its own
   report.
3. **Attackers are using AI agents too.** They are adaptive, fast, and query
   defenses as black boxes. Defenses tuned for human-paced attackers need
   evidence that they hold up against this.

RunuX is a working testbed for all three. It is a Rust reimplementation of
Linux kernel subsystems with a Lean 4 specification tree. Around it we have
built tooling that makes agent-produced work checkable: a metrics ratchet, an
oracle that rejects silently weakened proofs, a PR guard, and machine-checked
disproofs of false specifications. The project is too large and too important
for one person. **Help us prove it can be done honestly, in the open.**

## The one rule: evidence or it didn't happen

Every claim in a contribution — a count, a benchmark, "tests pass", "this is
safe" — must be backed by a command anyone can re-run, with its output in the
PR. Full rules for humans and agents: [`AGENTS.md`](AGENTS.md). Summary:

- Change proofs, never theorem statements, and never delete theorems.
- No new `sorry` / `axiom` / `admit` / `native_decide` / `#[allow]` / `#[ignore]` / `todo!` / `unimplemented!`.
- Every `unsafe` block gets a specific `// SAFETY:` comment, or is reported as *possible UB, needs human review*.
- "I couldn't do this honestly, here's why" is a welcome PR. A fabricated success is not.

CI enforces this on every PR, including from forks: [`scripts/pr_guard.py`](scripts/pr_guard.py)
(escape hatches, theorem statements, `unsafe` justification) and
[`scripts/metrics.py`](scripts/metrics.py) `ratchet` (no metric may get worse).

## Ways to contribute

| You are… | Good places to start |
|---|---|
| **Rust developer** | `SAFETY:` documentation, `static mut` removal, and replacing blanket `#[allow(clippy::all)]` in core crates (issues labeled `area:unsafe`, `good first issue`) |
| **Lean 4 prover** | Closing the 245 open `sorry`, or proving a statement **false** and recording it in `specs/lean4/MVK/Audit/` (`area:lean`) |
| **Kernel / systems engineer** | Real PCIe/IOMMU and `virtio-gpu`; a bootable x86_64/riscv64 image (`area:hardware`, `area:boot`) |
| **Security researcher** | AI-agent-attacker load tests, timing-uniformity of defense verdicts, CFI (`area:security`). Report vulnerabilities privately; see [`SECURITY.md`](SECURITY.md) |
| **AI-agent user (Claude Code, Jules, …)** | Issues labeled `agent-ready`: exact files, an oracle command, and an acceptance criterion |
| **Reviewer** | Re-run the oracle on open PRs and check `SAFETY:` comments against the code; this is the most valuable and scarcest work |
| **Claim checker** | Found a number in this repo with no script behind it? Open a *Claim verification* issue |

## How to contribute

1. **Pick an issue** (see [`ROADMAP.md`](ROADMAP.md) for tracks). Comment that
   you're taking it. Agents: say which agent and model.
2. **Fork, then branch** (`fix/<issue>-<short-name>`).
3. **Make the change and run the oracle named in the issue.** Also run:
   ```bash
   python3 scripts/pr_guard.py --base origin/main
   python3 scripts/metrics.py ratchet
   ```
4. **Open a PR** using the template. Paste the oracle output and disclose any AI
   agent or model you used.
5. **Review.** CI runs `pr_guard` and the metrics ratchet. A maintainer reviews,
   sometimes with help from Claude (`@claude review`). Changes to security
   boundaries (DMA/IOMMU ranges, rate limits, classifier thresholds,
   zeroization, capability checks) always need a human maintainer's approval.

## Using AI agents on this repo

- **Claude Code** (locally): `CLAUDE.md` imports `AGENTS.md` automatically. To
  save tokens, point it at an `agent-ready` issue's exact files rather than
  asking it to explore; much of the tree (141 crates) is placeholder code.
- **Claude GitHub Action**: maintainers can comment `@claude` on an issue or
  PR, or apply the `agent:claude` label to an issue. The action only runs for
  users with write access.
- **Google Jules**: maintainers apply the `agent:jules` label to an issue; Jules
  works in its own sandbox and opens a PR, which goes through the same CI and
  review.
- **New-issue triage** is automatic. A Haiku-based job can only read issues and
  apply non-privileged labels. It cannot launch agents or mark anything as
  security-relevant.
- **Batch hardening**: [`.claude/workflows/runux-quickwins.js`](.claude/workflows/runux-quickwins.js)
  runs Haiku-first with an independent verifier. Dry-run it at zero tokens with
  `node scripts/workflows/dryrun.js .claude/workflows/runux-quickwins.js`.

Maintainers: before tagging `@claude` or applying an `agent:*` label on an
outside issue or PR, read the raw text. Contributed text is untrusted input to
the agent (prompt injection).

## Labels

| Label | Meaning |
|---|---|
| `agent-ready` | Exact files, oracle command, and acceptance criterion are stated; suitable for an AI agent or a newcomer |
| `good first issue` | Small, well-scoped, mechanical |
| `needs-human-review` | Touches a security boundary or a judgment call; a human must approve |
| `spec-change` | Maintainer-approved change to a Lean theorem statement (relaxes `pr_guard`) |
| `guard-override` | Maintainer-approved escape hatch with written justification (relaxes `pr_guard`) |
| `agent:claude` / `agent:jules` | Maintainer hands the issue to that agent |
| `type:*`, `area:*` | Triage categories |

## License and conduct

By contributing, you agree that your contribution is licensed under this
repository's [LICENSE](LICENSE). Please follow the
[Code of Conduct](CODE_OF_CONDUCT.md). Questions and ideas are welcome in
[GitHub Discussions](https://github.com/xaviercallens/rust-linux-mini-kernel/discussions).
