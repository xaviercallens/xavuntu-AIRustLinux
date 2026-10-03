# FAQ

**Is RunuX a real, production Linux kernel replacement?**
No. It's a research testbed: Rust reimplementations of pieces of Linux
kernel subsystems, a partial Lean 4 proof tree, and open tooling for making
AI-assisted contributions verifiable. See the README's *Measured Status*
for exactly what's implemented vs. placeholder.

**Why does the README talk so much about the project's own past mistakes?**
Because an audit found several of its own claims didn't survive
measurement, and the fix wasn't just correcting the numbers once — it was
building tooling (`scripts/metrics.py`, `scripts/pr_guard.py`) that keeps
that from silently happening again. See `paper/claims_vs_evidence.tex`.

**Can I just open a PR without an issue?**
Yes, but a PR that doesn't match an existing `agent-ready` issue's oracle
and acceptance criterion will take longer to review, because a reviewer has
to establish those first. Small, obviously-scoped fixes are fine without one.

**I'm using an AI agent (Claude, Copilot, Cursor, ...) to write my PR — is
that OK?**
Yes, and please say so in the PR (the template asks). Read `AGENTS.md`
first: no fabricated claims, no weakened theorem statements, no escape
hatches, and every `unsafe` block needs a specific justification or an
honest "possible UB" note. `scripts/pr_guard.py` checks the mechanical
parts of this on every PR.

**Why did an agent leave an `unsafe` block uncommented instead of "fixing"
it?**
Because it couldn't verify the block was sound — see issues #60 and #64 for
two real examples. That's the correct, wanted outcome. A confident but
fabricated `SAFETY:` comment is worse than an honest gap.

**How do I get Claude or Jules to work on an issue?**
You can't trigger them directly as an outside contributor — that's
deliberate (see `SECURITY.md` on prompt injection). Comment on the issue
explaining why it's a good fit for an agent, and a maintainer can apply the
`agent:claude` or `agent:jules` label.

**I found a number in the docs with nothing backing it up.**
That's a real, welcome contribution. Open a *Claim verification* issue
(there's a template for it) with where the claim is and what you checked.
