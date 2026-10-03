# RunuX vs. AI-Agent Cyber Attacks — Improvement Plan

**Status:** PLAN ONLY. Nothing in this document has been implemented.
**Baseline:** `v11.3.0` (pending merge of PR #31), commit `041622e` for the
Core Defenses claims audited below.
**Execution model:** every workstream here is written as a unit list meant
to run through `Workflow` with low-tier models (Haiku for generation/
mechanical hardening, Sonnet for design and escalations), reusing the
oracle-gated harness built in `docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md`
(`scripts/check_unit.py`, `scripts/units/generate.py`). No agent should be
launched from this document without a human first reading it.

---

## 1. Why "AI-agent attacker" is a distinct threat model

RunuX's existing Core Defenses (`crates/ebpf_firewall`, `crates/ai_detector`,
`crates/syscall_table`, `crates/immutable_logs`, 40 requirements,
`specs/lean4/MVK/RunuxDefenses.lean`, 84 theorems) were designed around a
**human-paced, pattern-based** attacker: someone crafting one exploit,
running it, observing the result, and iterating over minutes to days.
An autonomous AI agent attacker changes four assumptions the current design
leans on:

| Assumption baked into the current defenses | What an AI-agent attacker breaks |
|---|---|
| Attack attempts arrive at human-reaction speed (the adaptive rate limiter and watchdog are tuned/tested at that pace) | An agent can generate, mutate, and fire thousands of syscall/packet variants per second, faster than a human ever probed the rate limiter |
| Payloads resemble known shapes (NOP sleds, fixed entropy signatures) | An LLM can generate semantically novel, low-entropy, non-repeating obfuscations that don't match the `high_entropy_never_passes` / NOP-sled heuristics (REQ-RCD-005, REQ-RCD-024) on the first try |
| A defense's trigger threshold is fixed and un-probed | An agent can treat the classifier as a black-box oracle, binary-search the decision boundary of the frozen INT8 TinyML model (REQ-RCD-004), and craft inputs just under threshold |
| The defender only needs to stop a *chain*, not identify *which layer* stopped it | An agent that can distinguish "blocked by entropy filter" vs. "blocked by TinyML" vs. "blocked by syscall table" from response timing/error shape can fingerprint the stack and route around the weakest layer |

None of this means the existing 40 requirements are wrong — `blockkill_absorbs_all` (REQ-RCD-008) and the pessimistic-verdict design are exactly the right shape for defense-in-depth. The gap is that **nothing in the current Lean models or Rust tests represents an adaptive, high-frequency, black-box-querying adversary.** Every existing proof assumes a single audited event, not a *campaign* of millions of adaptively chosen events.

## 2. What's actually in place today (honest baseline)

Reusing this session's earlier audit (`RUNUX_V12_VERIFIED_CORE_PLAN.md` §0) rather than re-trusting the traceability matrix's "✅ VERIFIED" column at face value:

| Capability | Real status |
|---|---|
| Ring 0 pre-dispatch interception, W^X enforcement, entropy scan, Merkle audit, LMS policy machine (REQ-001–009) | Proven in the **abstract Lean model** (`RunuxDefenses.lean`, 84 theorems, 0 sorry, 0 axioms). No Aeneas/hax extraction link to the actual Rust in `crates/ebpf_firewall`/`crates/syscall_table` — the proofs describe a model of the design, not the shipped code (same gap flagged in the v12 plan §1 goal G4). |
| TinyML anomaly classifier (REQ-004, REQ-021, REQ-027, REQ-033) | Frozen INT8 perceptron, static tensor arena, quantized-weight checksum verifier. **No adversarial-robustness evaluation exists anywhere in the repo** — the proofs bound activation ranges and latency, not resistance to a deliberately crafted evasive input. |
| Deductive Floor / Routing-Stall prevention (REQ-016, SymBrain v4) | σ_ded ≥ 0.30 enforced and proven. This is itself a defense against one AI-on-AI failure mode (an ambiguous/adversarial query driving the router to zero deductive weight) — the closest thing already in the repo to "AI agent attacking an AI component." Worth generalizing rather than replacing. |
| Federated multi-gate verification (REQ-017) | Bounds VRAM headroom and differential-privacy budget for volunteer nodes. No Sybil-resistance or malicious-majority analysis — a coordinated set of AI-agent-operated "volunteer" nodes is not modeled. |
| Adaptive threat decay / rate limiting (REQ-027), watchdog (REQ-035) | Proven monotonic/bounded in the abstract model. Never load-tested at agent-plausible request rates (10³–10⁵ attempts/sec); no data on real behavior under that regime exists. |
| ROP/polymorphic detection (REQ-024) | Pattern-based (NOP-sled length, entropy). No defense against control-flow hijacks that don't produce a detectable pattern — this is precisely what hardware CFI (already listed as v12 plan feature F8, not yet built) would address structurally instead of by pattern-matching. |

**Bottom line:** the architecture (pessimistic multi-gate merge, Ring 0 interception, immutable audit) is sound and reusable. What's missing is (a) an explicit adaptive/high-frequency/black-box attacker model, (b) evidence the existing gates hold under it, and (c) a few structural additions (CFI, response-uniformity, model integrity) that pattern-matching alone can't provide.

## 3. Goals

| ID | Goal | Metric | Why this metric |
|---|---|---|---|
| D1 | TinyML classifier resists black-box evasion search | Adversarial success rate ≤ X% within a query budget matched to the rate limiter's trip point (i.e., the limiter must fire before a boundary-search converges) | Ties two existing but previously-unconnected mechanisms (classifier threshold, rate limiter) into one measured guarantee |
| D2 | Defenses hold at AI-agent request rates | Verdict correctness and latency (p99 < 15 µs per REQ-004) unchanged at 10³–10⁵ req/s, not just the single-event benchmarks that exist today | Closes the "human-paced" assumption gap directly |
| D3 | No cross-layer fingerprinting via timing/response shape | Statistical indistinguishability (e.g., no significant timing difference, Kolmogorov–Smirnov or similar) between "blocked by entropy filter" vs. "blocked by TinyML" vs. "blocked by syscall table" | An agent that can fingerprint the stack can route around its weakest layer; defense-in-depth is only as strong as its most distinguishable layer |
| D4 | Model supply-chain integrity beyond a bare checksum | Signed manifest + reproducible-build hash verified before any quantized weight is loaded, checked in Lean | REQ-033 checks weight bytes are untampered; it does not check the weights came from the build you think they did |
| D5 | Federated gate resists a coordinated/Sybil AI-operator set | Formal bound: verdict correctness holds for any coalition below a stated fraction of nodes | REQ-017 has no adversary-count parameter today |
| D6 | Structural control-flow defense, not just pattern-matching | CFI/shadow-stack (x86 CET / RISC-V Zicfiss) boots and blocks a synthetic ROP chain that the entropy/NOP heuristics miss by construction | Directly targets "LLM-generated exploit doesn't look like a known pattern" |
| D7 | Patch-speed matches disclosure-speed | Time from a `cargo audit` advisory landing to a merged, oracle-verified patch, measured and tracked | An AI agent can weaponize a new CVE faster than a human triage cycle; the same oracle-gated low-tier-model workflow that closes proof debt can close this gap for dependencies |

## 4. Proposed new requirements (REQ-AID-\* series)

Numbered to sit alongside, not replace, REQ-RCD-001–040.

| ID | Title | Subsystem | Maps to goal |
|---|---|---|---|
| REQ-AID-001 | Query-budget-aware classifier: track cumulative black-box query pressure per source and couple it to the adaptive rate limiter's decay state, not just per-event score | `crates/ai_detector`, `crates/ebpf_firewall` | D1, D2 |
| REQ-AID-002 | Constant-shape verdict path: pad/normalize response timing and error codes so entropy-filter, TinyML, and syscall-table rejections are indistinguishable to the caller | `crates/ebpf_firewall`, `crates/syscall_table` | D3 |
| REQ-AID-003 | Signed weight manifest + reproducible-build hash gate, checked before `ai_detector` loads frozen weights | `crates/ai_detector` | D4 |
| REQ-AID-004 | Sybil-bounded federated verdict: formalize a maximum-malicious-fraction parameter and prove verdict soundness holds below it | `crates/federated` | D5 |
| REQ-AID-005 | Hardware CFI/shadow-stack integration (x86 CET, RISC-V Zicfiss) as a feature-gated build, with a synthetic-ROP boot test that the entropy heuristic is shown *not* to catch, to prove this is additive, not redundant | `crates/arch_setup`, new `crates/cfi_guard` | D6 |
| REQ-AID-006 | Load-test harness reproducing 10³–10⁵ req/s synthetic agent traffic against the full defense pipeline in QEMU, feeding results into `scripts/metrics.py` as a new tracked metric (`defense.p99_latency_at_load`) | `scripts/`, CI | D2 |
| REQ-AID-007 | Dependency-CVE oracle-gated patch workflow: `cargo audit` finding → generated unit → T1/T2 patch attempt → oracle (build + tests + no new advisories) → PR, timestamped end-to-end | `scripts/units/`, `scripts/check_unit.py` | D7 |
| REQ-AID-008 | Generalize the Deductive Floor pattern (σ_ded ≥ 0.30) to any AI-mediated decision surface RunuX exposes, as a reusable "cognitive floor" contract, so a future AI component doesn't have to reinvent REQ-016 | `crates/ai_detector`, docs | Reuse, not a new metric |

## 5. Workflow decomposition (for later execution, not now)

This mirrors `scripts/units/generate.py`'s existing four unit types
(`lean_sorry`, `unsafe_safety`, `static_mut`, `placeholder_triage`) with new
types this plan would need. **None of these generators exist yet — this
section specifies what to build, not a run to launch.**

| New unit type | Generates one unit per… | Oracle |
|---|---|---|
| `adversarial_probe` | (classifier, threshold band) pair from `ai_detector`'s weight table | A black-box query-budget search script; unit fails if evasion succeeds within the budget matched to D1 |
| `timing_uniformity` | pair of rejection paths (e.g., entropy-filter vs. TinyML) | Statistical timing-distinguishability test (T1 can implement the harness; the statistical test itself must be a fixed, reviewed script, not agent-judged) |
| `cve_patch` | one `cargo audit` advisory | `cargo build` + existing crate tests + `cargo audit` clean, exactly like `check_unit.py`'s existing build/test oracles |
| `load_bench` | one (defense-layer, request-rate) pair | Latency/correctness assertion against the QEMU load harness (REQ-AID-006) |

Tiering follows the existing model: T1 (Haiku) for load-harness plumbing and mechanical CVE patches (version bumps, non-breaking API fixes); T2 (Sonnet) for anything touching the classifier threshold, the CFI integration, or the federated Sybil bound, since those require judgment the pilot already showed T1 lacks on non-mechanical goals (`docs/roadmap/units_status.csv`: T1 closed 1/12 proof obligations unassisted; the harder, more judgment-heavy work went to T2). Any unit that would change a security *threshold* (rate-limiter trip point, classifier decision boundary, Sybil-fraction bound) requires a human/T3 sign-off before merge, regardless of which tier produced it — these are exactly the kind of statement-level changes the anti-weakening hash check (already built for Lean) doesn't cover for numeric security parameters, and no automated oracle should be trusted alone to loosen a security bound.

## 6. Sequencing

| Phase | Scope | Exit criterion |
|---|---|---|
| P0 — Measure first | Build `load_bench` (REQ-AID-006) and the adversarial-probe harness (D1) against the *current* system, with no changes yet | A number exists for "how does RunuX behave under AI-agent-speed/adversarial load today" — currently zero such numbers exist |
| P1 — Structural gaps | REQ-AID-002 (timing uniformity), REQ-AID-003 (signed manifest) | Both are additive, don't touch security thresholds, and are safe for T1/T2 without T3 gate |
| P2 — Threshold-sensitive | REQ-AID-001 (query-budget coupling), REQ-AID-004 (Sybil bound) | Requires the P0 measurements as input; requires T3 sign-off per §5 |
| P3 — Structural hardening | REQ-AID-005 (CFI) | Largest engineering lift; depends on v12 plan's boot-image work (WS5) existing first, since CFI needs a real bootable target, not the current demo-kernel QEMU harness |
| P4 — Process | REQ-AID-007 (CVE-speed patch workflow) | Can start anytime; it's infrastructure, not a security-threshold change, and directly extends the already-built `check_unit.py` oracle pattern |

## 7. What this plan deliberately does not claim

- It does not claim RunuX is currently vulnerable to any specific AI-agent exploit — no such exploit was attempted or found. It claims the *evidence needed to say it's resistant doesn't exist yet*, which is a narrower and checkable statement.
- It does not propose replacing the existing 40 REQ-RCD requirements or their Lean proofs. It proposes measuring them under a harder adversary model and adding a small number of structural gaps (CFI, signed manifests, timing uniformity) that pattern-based detection cannot close by construction.
- It does not assume "AI agent attacker" requires new cryptography or a new architecture — the existing pessimistic-multi-gate design is the right shape; the gap is evidence and a few specific extensions, not a redesign.

---

## 8. RunuX-GWAYA Evolution: The Zero-Trust, AI-Native Kernel (Architectural Proposal)

**Status:** ARCHITECTURAL PROPOSAL RECORDED — NOT YET IMPLEMENTED.  
**Reference Document:** See verbatim proposal at [`RUNUX_GWAYA_AI_NATIVE_KERNEL.md`](./RUNUX_GWAYA_AI_NATIVE_KERNEL.md) (and root `docs/proposals/RUNUX_GWAYA_AI_NATIVE_KERNEL.md`).

Building on the GWAYA Compound AI System, Laya-LoRA semantic gatekeeper, and Cyber-Physical (v5) manuscripts, the RunuX-GWAYA architecture formalizes the evolution into a Zero-Trust, AI-Native Operating System:

1. **Edge-Native Laya-LoRA Semantic Firewall (System 1)**:
   - Quantized 149M INT8 ONNX payload (~150MB) embedded at Ring 0 / eBPF boundary.
   - Microsecond (<50ms) intent evaluation on high-privilege requests (`execve`, socket bindings).
   - Strict `seccomp-bpf` FFI isolation boundary around the ONNX C-runtime.
2. **Split Conformal Routing ($1 - \alpha = 0.95$)**:
   - $\mathcal{C}(x) = \{\text{BLOCK}\}$: Energy barrier ($E = 10^6$), instant `EPERM` drop, agent quarantine.
   - $\mathcal{C}(x) = \{\text{PASS}\}$: Zero-delay fast-path execution.
   - $\mathcal{C}(x) = \{\text{PASS, BLOCK}\}$: Escalation to System 2 MCTS sandbox (Qwen3.8-27B) safe simulation.
3. **Cyber-Physical Thermodynamic Defense**:
   - Intel RAPL 5-sample trimmed-mean OS scheduler to filter non-deterministic OS spikes.
   - Formal Lean 4 mechanical kill-switch (`cpu_energy_bounded` invariant) enforcing preemptive `SIGKILL` at $E > 10^6 \mu\text{J}$.
4. **Agentic Swarm Runtime Optimization**:
   - Thread-Safe Agent Singleton Memory Management (Double-Checked Locking at IPC/VMA layer, zero-copy VMA) to prevent context duplication and cache thrashing.
   - Microsecond `spawn_ephemeral_sandbox()` syscall with $\mathcal{O}(1)$ queue complexity and UCB1 degenerate tree guards.
5. **Continuous Autopoiesis**:
   - 20-dataset multidisciplinary curriculum PRMs, ChromaDB LTM trace logging, and System 2 idle-cycle synthesis with formal Lean 4 hot-patch verification.
