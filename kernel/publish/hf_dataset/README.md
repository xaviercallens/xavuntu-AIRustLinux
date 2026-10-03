---
license: cc-by-4.0
language:
- en
pretty_name: "Claims vs. Evidence: RunuX audit and oracle-gated LLM proof-completion pilot"
tags:
- formal-verification
- lean4
- rust
- llm-agents
- software-auditing
- reproducibility
size_categories:
- n<1K
---

# Claims vs. Evidence — RunuX audit & LLM proof-completion pilot

Supporting data for the preprint *Claims vs. Evidence: A Measured Audit of an
AI-Assisted Rust Kernel and an Oracle-Gated Workflow for LLM Proof Completion*
(Xavier Callens, 2026). The paper PDF and LaTeX source are included.

Source repository: <https://github.com/xaviercallens/rust-linux-mini-kernel>
(tag `v11.3.1`).

## Files

| File | Content |
|---|---|
| `claims_vs_evidence.pdf` / `.tex` | The preprint |
| `metrics.baseline.json` | Static metrics at baseline commit `041622e` (v11.1.0), produced by `scripts/metrics.py` |
| `units_status.csv` | One row per pilot proof obligation: tier, outcome (`fixed`, `spec_defect_proved`, `open`), attempts, PR |
| `units_summary.json` | Count of generated work units by type (1,292 at baseline) |
| `SpecDefects.lean` | Lean 4 proofs that two specification statements are false (depends only on `propext`) |
| `AXIOMS.md` | Register of the 138 axioms in the specification tree |
| `placeholder_triage.csv` | IMPLEMENT / MERGE / REMOVE / REVIEW proposal for 141 placeholder crates |

## Headline numbers (baseline)

- 316 crates, 53,779 Rust LOC; 141 crates ≤ 25 LOC
- 284 crates with blanket `allow(clippy::all)`
- 723 `unsafe` blocks, 101 `// SAFETY:` comments (ratio 0.14)
- 36 Lean files, 432 theorems, 138 axioms, 249 `sorry` (245 after the pilot)

## Pilot outcomes (12 open obligations)

4 closed (independently re-verified), 2 proved false as stated, 6 open.
Cost: 8 agents, 538,799 subagent tokens, 337 tool calls, 34.3 min.

## Reproduce

```bash
git clone https://github.com/xaviercallens/rust-linux-mini-kernel && cd rust-linux-mini-kernel
git checkout v11.3.1
python3 scripts/metrics.py measure --out /tmp/now.json            # post-pilot numbers (245 sorry)

# baseline numbers: run the v11.3.1 scripts against the v11.1.0 tree
git worktree add /tmp/base v11.1.0     # = commit 041622e
cp scripts/metrics.py scripts/lean_tools.py scripts/rust_tools.py /tmp/base/scripts/
python3 /tmp/base/scripts/metrics.py measure --out /tmp/base.json --md /tmp/base.md

cd specs/lean4 && lake build MVK.Audit.SpecDefects                # counterexample proofs
```

## Limitations

Single-project case study; small pilot (n = 12); heuristic static metrics.
The audit, tooling, and paper were produced with AI assistance (Anthropic
Claude models) under the author's direction.

## Citation

Published on Zenodo: [10.5281/zenodo.22985926](https://doi.org/10.5281/zenodo.22985926)

```bibtex
@misc{callens2026claims,
  author    = {Callens, Xavier},
  title     = {Claims vs. Evidence: A Measured Audit of an AI-Assisted Rust Kernel
               and an Oracle-Gated Workflow for LLM Proof Completion},
  year      = {2026},
  publisher = {Zenodo},
  version   = {v11.3.1},
  doi       = {10.5281/zenodo.22985926},
  url       = {https://doi.org/10.5281/zenodo.22985926}
}
```

## Contributing

The project is open to Rust, Lean, and security contributors and to AI agents:
see [ROADMAP.md](https://github.com/xaviercallens/rust-linux-mini-kernel/blob/main/ROADMAP.md)
and [CONTRIBUTING.md](https://github.com/xaviercallens/rust-linux-mini-kernel/blob/main/CONTRIBUTING.md).
