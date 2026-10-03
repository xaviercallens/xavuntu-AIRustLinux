# RunuX v12 "Verified Core": Implementation & Evolution Plan

**Status:** PLAN ONLY. Nothing in this document has been implemented.
> **Ordering superseded (2026-09-27):** execution order, business rationale, and token budgets now live in [`BUSINESS_CASE_PRIORITIZED_PLAN.md`](BUSINESS_CASE_PRIORITIZED_PLAN.md). The workstream content below is unchanged.
**Baseline commit:** `041622e` (v11.1.0), `main` aligned with `origin/main` (0 ahead / 0 behind), measured 2026-09-26.
**Audience:** maintainers and automated agent workflows. Most work units are sized for low-tier models such as Claude Haiku 4.5.

---

## 0. Baseline: measured vs. claimed

Every number below was measured on the baseline commit. Several public claims do not hold, and the plan starts by fixing that gap. The earlier audit artifact (2026-09-26) repeated the claims and is superseded by this table.

| Claim (README / AGENTS.md / traceability matrix) | Measured reality | Gap |
|---|---|---|
| "297 modules" | 316 crate dirs, 53,778 Rust LOC | 141 crates are ≤25-LOC placeholders (`*_init() -> 0`); 35 more have 26–100 LOC |
| "Zero compiler warnings" | `cargo check --workspace` gives 0 warnings | Achieved by suppression: 284 crates use `#![allow(clippy::all…)]`, 129 use `allow(dead_code/unused/warnings)` |
| "Zero `sorry`, zero axioms" across the 12 phases | 249 live `sorry` and 138 `axiom` in 36 Lean files, 432 theorems | Holds only for `RunuxDefenses.lean` (84 thm), `Phase13`, `Phase9`, `Phase12`, and a few more. Phase 3 (Netfilter) alone has 187 `sorry`. |
| Lean "structurally congruent" with Rust | No extraction link (no Aeneas/hax/Charon). 150 `requires!/ensures!` macros exist, but nothing checks them against the Lean specs. `kernel_types/src/verus_proofs.rs` exists | Proofs cover hand-written Lean models, not the Rust code. RunuxDefenses has 90 lines closed by one-line `simp/rfl/decide/omega` tactics, so the proofs are mostly shallow facts about definitions |
| "Every `unsafe` has `// SAFETY:`" | 722 `unsafe {}` blocks + 1,613 `unsafe fn`, but only 101 `SAFETY:` comments; 197 `static mut` | About 4% coverage |
| Stub-free core | 255 `extern "C" fn` with a constant body (`0`, `-1`, `null_mut()`); stub/TODO markers in 85 crates (204 lines) | Includes `reassembly`, `netfilter` v6 hooks, `nf_nat_masquerade`, `seg6_local`, `exthdrs`, `udp` tables |
| "Headless QEMU boot" / RISC-V boot | `scripts/qemu_boot_test.py` boots an **i686 demo kernel** (`examples/demo_kernel`) and checks for a banner. **Update:** `scripts/riscv_boot_test.sh` boots real workspace code (`arch/riscv64`) via OpenSBI on `qemu-system-riscv64` (real UART banner, clean SiFive test-finisher exit); `scripts/x86_64_boot_test.sh` boots real 64-bit long mode via GRUB Multiboot2 on `qemu-system-x86_64`, exercising real `kernel_types::SafePageFrame` logic (clean isa-debug-exit) | riscv64 subsystem init (PLIC, Sv39) is still print-only; x86_64 has no IDT/APIC/real drivers yet; neither is integrated into CI |
| Tested subsystems | `#[test]` present in 74/316 crates (335 tests); 2 fuzz targets (`fuzz_packet`, `fuzz_routing`) | No coverage measurement; placeholder crates have no tests |
| Sound unsafe in AI path | `ai_detector` `activation_slice(&self) -> &mut [i8; N]` (lib.rs:126–135) | Can produce aliasing `&mut` from `&self`: potential UB, needs Miri |
| GCP / SymBrain v4 benchmark figures | Only in docs; not reproducible from the repo's CI | Treat as unverified until a reproducible harness exists |

**What is real and worth building on:** `ebpf_firewall`, `ai_bridge`, `kernel_types`, `slab`, `ai_runtime`, `federated`, `page_alloc`, `ai_detector`, `immutable_logs`, and `turbo_quant` (≈750–1,550 LOC each, with tests), plus the fully closed `RunuxDefenses.lean` model, a working RISC-V cross-compile, 6 CI workflows, and Miri installed.

---

## 1. Goals

### North star
A small kernel core that boots on x86_64 and riscv64 and that you can actually run and actually trust. Every public claim should be backed by a CI-generated number. Where AI features exist, they propose and a verified guard disposes: no learned component is ever in the trusted path without a proven envelope.

### v12 goals (SMART)

| ID | Goal | Target | Deadline (from plan start) |
|---|---|---|---|
| G1 | Honest claims: README/AGENTS.md numbers generated from `metrics.json` | 100% of numeric claims sourced | Week 2 |
| G2 | Proof debt: live `sorry` in the default Lake target | 249 → 0 | Week 12 |
| G3 | Axiom hygiene: axioms only for documented hardware/C-boundary assumptions, listed in `AXIOMS.md` | 138 → ≤30, each justified | Week 12 |
| G4 | Rust↔Lean link: core-defense crates extracted to Lean (Aeneas or hax), and theorems restated on the extracted code | ≥5 crates, ≥40 theorems on extracted code | Week 16 |
| G5 | Stub elimination on the network data path | 0 constant-body functions in the P0 crate list (§3.2) | Week 8 |
| G6 | Placeholder decision: each of the 141 placeholder crates is implemented, merged, or removed | 141 → 0 undecided | Week 6 |
| G7 | Unsafe hygiene: `SAFETY:` coverage on `unsafe {}` blocks | 4% → 100% (core set), ≥80% (workspace) | Week 10 |
| G8 | Lint honesty: crates with blanket `allow(clippy::all)` | 284 → 0 in core set, ≤50 workspace | Week 10 |
| G9 | Real boot: workspace kernel boots to init banner + syscall smoke test in QEMU on x86_64 and riscv64 | 2/2 arches green in CI | Week 10 |
| G10 | Test depth: line coverage of the core set (§3.4) | ≥70% (measured via `cargo llvm-cov`) | Week 12 |
| G11 | Fuzzing: continuous fuzz targets on parsers | 2 → ≥12 targets, 0 open crashes, ≥1 CPU-hour each per release | Week 12 |
| G12 | Performance claims measured | TinyML verdict p99 < 15 µs, syscall pre-dispatch overhead p99 < 1 µs, both measured in QEMU+KVM and on ≥1 real board | Week 14 |

**Core set** (where the strict gates apply first): `kernel_types`, `syscall_table`, `ebpf_firewall`, `ai_detector`, `ai_bridge`, `immutable_logs`, `turbo_quant`, `slab`, `page_alloc`, `vmalloc`, `netfilter`, `reassembly`, `exthdrs`, `nf_nat_masquerade`, `udp`, `arp`, `fib_rules`, `arch_*` (after G6).

---

## 2. Metrics & acceptance criteria

All metrics come from one script, `scripts/metrics.py` (to be written in WS0), which emits `metrics.json`. CI **ratchets**: a PR may not make any metric worse. This is the main defence against low-tier models "passing" by cheating.

| Metric | Definition / command | Baseline | v12 target | Gate type |
|---|---|---|---|---|
| `lean.sorry` | non-comment `sorry` tokens in `specs/lean4/MVK/**` | 249 | 0 | ratchet + hard at v12 |
| `lean.axiom` | `^\s*axiom` decls | 138 | ≤30 | ratchet |
| `lean.axiom_undocumented` | axioms not listed in `AXIOMS.md` | 138 | 0 | hard |
| `lean.build` | `lake build` exit code | ? (to measure) | 0 | hard |
| `lean.thm_statement_hash` | SHA of each theorem statement (text before `:=`) | snapshot | unchanged unless PR is tagged `spec-change` | hard (anti-weakening) |
| `lean.extracted_thm` | theorems whose subject is Aeneas/hax-extracted code | 0 | ≥40 | ratchet |
| `rust.warnings` | `cargo check` + `cargo clippy -D warnings` without blanket allows | 0 (suppressed) | 0 (unsuppressed) | hard |
| `rust.blanket_allow` | crates with `allow(clippy::all)` | 284 | ≤50 | ratchet |
| `rust.const_stub_fns` | `extern "C" fn` whose body is a single constant | 255 | ≤40 (non-core only) | ratchet |
| `rust.stub_markers` | lines matching `stub|TODO|FIXME|simplified|placeholder` | 204 | ≤20 | ratchet |
| `rust.placeholder_crates` | crates ≤25 LOC | 141 | 0 | ratchet |
| `rust.safety_ratio` | `SAFETY:` comments / `unsafe {}` blocks | 0.14 | 1.0 core / 0.8 all | ratchet |
| `rust.static_mut` | `static mut` count | 197 | ≤20 | ratchet |
| `test.count` / `test.crates` | `#[test]` / crates with tests | 335 / 74 | ≥1,200 / all non-FFI-shim crates | ratchet |
| `test.coverage_core` | `cargo llvm-cov` line % over core set | unmeasured | ≥70% | ratchet |
| `miri.core` | `cargo miri test` over core set | unmeasured | 0 UB | hard |
| `fuzz.targets` / `fuzz.crashes` | count / open crashes | 2 / ? | ≥12 / 0 | ratchet / hard |
| `boot.x86_64` / `boot.riscv64` | QEMU boots workspace kernel, prints banner, runs `getpid`, `write`, blocked W^X `mprotect` | 0/0 | 1/1 | hard |
| `perf.tinyml_p99_us` | bench harness, 10k samples | unmeasured | < 15 | tracked, alert on regression > 10% |
| `perf.predispatch_p99_ns` | added latency per syscall | unmeasured | < 1,000 | tracked |
| `repro.build` | two clean builds give bit-identical artifacts | unmeasured | yes | hard at v12 |

**Definition of Done (per work unit):** the unit's oracle is green (§4.2), no metric regresses, no theorem statement changes without the `spec-change` tag, the diff is ≤ 300 lines, and it contains no new `allow(...)`, `sorry`, `axiom`, `#[ignore]`, `unimplemented!` or `todo!`.

---

## 3. Workstreams (fixing what exists)

### WS0: Truth & metrics gate (Week 1–2, blocking all others)
1. Write `scripts/metrics.py` to compute every metric in §2 and emit `metrics.json` plus a markdown table.
2. Add a CI job `metrics-ratchet` that compares against `metrics.baseline.json` on `main` and fails on regression.
3. Fix `specs/scripts/verify_specs.sh`: count only non-comment `sorry`, fail on >0 for files listed as "complete", and fail on `lake build` error (today it pipes to `/dev/null`).
4. Regenerate the README/AGENTS.md claims block from `metrics.json`; mark `ROADMAP_TRACEABILITY_MATRIX.md` as "Lean model verified, Rust linkage pending".
5. Snapshot theorem-statement hashes (`specs/lean4/.thm_hashes.json`).
- **Exit:** CI shows real numbers; the ratchet is live.
- **Model tier:** Haiku for steps 1, 4 and 5 (with a reference spec); Sonnet for CI wiring review.

### WS1: Proof debt burn-down (Week 2–12)
Prioritised by `sorry` count and criticality:

| Wave | Files | `sorry` | Approach |
|---|---|---|---|
| 1 | `Phase4/ARP`, `Phase5/IPv6`, `Phase1/ArchSetup`, `Phase1/InitMain` | 12 | warm-up; calibrate the loop |
| 2 | `Phase2/PageAlloc`, `Phase2/Slab` | 28 | memory safety first; high value |
| 3 | `Phase3/ConntrackUDP/Generic/ICMP/ICMPv6/DCCP/Core` | 79 | shared lemmas library `MVK/Lib/Conntrack.lean` first |
| 4 | `Phase3/ConntrackSCTP`, `NatCore`, `NatProto` | 85 | NAT invariants; likely needs restatement (tagged `spec-change`, human review) |
| 5 | `Phase4/AfInet`, `AfInet6`, `Routing/FibSemantics` | 45 | routing; many axioms to convert into definitions |

Per-`sorry` loop (low-tier model, §4): extract one `sorry` with context, try tactic candidates (`simp`, `omega`, `decide`, `aesop`, `induction … <;> simp_all`), and let Lean check. Escalate after N failures. Axiom reduction: convert each `axiom foo : T` into a `def`/`structure` field or a documented hardware assumption in `AXIOMS.md`.
- **Exit:** `lean.sorry = 0`, `lean.axiom ≤ 30`, `lean.build = 0`, statement hashes unchanged except reviewed `spec-change` PRs.

### WS2: Stub completion (Week 2–8)

#### 2.1 P0: network data path (these break real traffic)
| Crate | Current | Required behaviour | Oracle |
|---|---|---|---|
| `reassembly` | ~12 constant returns | RFC 791/8200 reassembly: overlap rejection (RFC 5722), 15 s/60 s timeout, memory cap per netns, checksum | unit vectors + `fuzz_reassembly` + Lean `Reassembly.lean` (new: "no overlapping bytes accepted", "memory ≤ cap") |
| `exthdrs` | hard-coded "stub" limits | RFC 8200 chain order, `max_dst_opts_cnt/len` from sysctl struct, HBH/DST/RH/FRAG | RFC test vectors + fuzz |
| `netfilter` v6 | `nf_ip6_fragment_stub`, `nf_ip6_route_input_stub`, `nf_ip6_br_fragment_stub` | delegate to `reassembly`/`route` | integration test through the hook chain |
| `nf_nat_masquerade` / `nf_nat_proto` | "Success stub", "simplified" checksum | RFC 1624 incremental checksum update | property test: incremental == full recompute (proptest) + Lean lemma |
| `udp` | stub global table / BPF flag | hash table with fallible allocation | unit + fuzz |
| `gre_demux` | RCU helper stubs | versioned GRE parse, protocol dispatch table | fuzz_gre |

#### 2.2 P1
`seg6_local` (RFC 8986 End, End.X, End.DT4/6), `nf_conntrack_h323_asn1` decoders (fuzz-first, historically CVE-prone), `mcast`, `ip6_vti`, `mip6`.

#### 2.3 Hardware TODOs
`rvv_simd` (read `vlenb` CSR under `cfg(target_arch="riscv64")`, with fallback), `ai_bridge` (device-tree probing instead of the hard-coded hardware assumption).

#### 2.4 Placeholder triage (G6)
For each of the 141 ≤25-LOC crates, pick exactly one decision, recorded in `docs/roadmap/placeholder_triage.csv`:
- **IMPLEMENT**: on the boot-critical path (`arch_entry`, `arch_irq`, `arch_pgtable`, `arch_traps`, `arch_tlb`, `sys_read/write/open/close/exit/getpid/mmap/munmap`, `time_tick`, `softirq`, `rbtree`, `kref`, `idr`, `percpu`, `panic`, `printk`-adjacent).
- **MERGE**: fold trivial shims into a parent crate (e.g. `sys_*` into `syscall_table`, `driver_base_*` into `driver_base`).
- **REMOVE**: out of scope for a minimal verified core (`ext4_*`, `ipc_*`, `swap*`, `security_keyring`, and similar). Keep them listed as "not provided" in the README.

Expected outcome: about 40 implement, 50 merge, 50 remove. The module count falls, and the claims become honest.

### WS3: Unsafe & lint hygiene (Week 3–10)
1. Fix `ai_detector::activation_slice` (`&self → &mut`): return a guard type holding `&mut self`, or use `UnsafeCell` with an exclusive-borrow token. Add a Miri test.
2. Replace `static mut` with `SpinLock<T>`, `AtomicX`, or `OnceCell`-style statics (a kernel-safe once cell).
3. Add a `// SAFETY:` note to every `unsafe {}` (one crate per work unit), then turn on `#![deny(clippy::undocumented_unsafe_blocks, unsafe_op_in_unsafe_fn)]` for that crate.
4. Remove blanket `allow(clippy::all)`. Fix issues or add narrow, justified allows at item level.
5. Run Miri in CI over the core set (`cargo miri test -p <crate>`).
- **Oracle:** clippy with the deny lints + Miri green.

### WS4: Rust↔Lean congruence (Week 6–16)
- Pick **Aeneas** (Rust → LLBC via Charon → Lean 4) as the primary path, with **hax** as the fallback. Both target Lean.
- Pilot crates: `immutable_logs` (Merkle append), `ai_bridge::ring_buffer` (SPSC), `ebpf_firewall` verdict merge + LMS state machine, and `nf_nat` checksum.
- Restate the RunuxDefenses theorems over the extracted functions. Keep the abstract model theorems and add refinement lemmas (`extracted ⊑ model`).
- Complement with **Kani** bounded model checking for `unsafe` pointer code (ring buffers, DMA descriptors, tensor arena) and extend the existing `verus_proofs.rs` only if Verus stays in the toolchain (pick one of Verus or Aeneas to avoid a split).
- Turn `requires!/ensures!` (150 sites) into checked contracts: `debug_assert!` in tests and Kani harness pre/postconditions.

### WS5: Real boot on x86_64 & riscv64 (Week 4–10)
1. Add a kernel binary crate `kernel_image` that links the core set, with `#[no_main]`, arch entry, and a linker script per arch.
2. riscv64: boot via OpenSBI (`-machine virt -bios default`), S-mode entry, UART 16550 console, Sv39 page tables, timer interrupt.
3. x86_64: Multiboot2/Limine entry, long mode, serial COM1, IDT, APIC timer.
4. Rewrite `qemu_boot_test.py` to be parameterized by `--arch`, check an ordered banner sequence (`[boot] mm ok`, `[boot] irq ok`, `[defense] armed`, `[init] syscall smoke ok`) and a clean `poweroff` exit code via the test device (`isa-debug-exit` / SBI `SRST`).
5. CI: install `qemu-system-{x86_64,riscv64}` and run both on every PR.
- **Oracle:** the QEMU test exits 0 with all banners in order within 20 s.

### WS6: Testing depth (continuous)
- Unit tests for every IMPLEMENT/MERGE crate, and property tests (`proptest`, host-only feature) for parsers and state machines.
- Fuzz targets (go from 2 to ≥12): `reassembly`, `exthdrs`, `gre`, `h323_asn1`, `sctp`, `dccp`, `icmpv6`, `nat_checksum`, `ebpf_verifier`, `merkle_append`, `syscall_args`, `tinyml_features`.
- Differential testing: compare Rust checksum, conntrack state transitions and NAT rewrites against Linux 5.10 behaviour captured as pcaps (golden vectors).
- Coverage via `cargo llvm-cov`, published in `metrics.json`.

### WS7: Performance, measured (Week 10–14)
- `benches/` harness running in QEMU with KVM and on one physical board (BPI-F3 / SpacemiT K1, which the docs already reference).
- Measure the TinyML verdict latency, syscall pre-dispatch overhead, Merkle append rate, packet path throughput (pps) with and without the firewall.
- Publish the results with hardware, commit, and seed. Remove any doc number that has no generating harness.

---

## 4. Workflow design for low-tier models

### 4.1 Model tiering

| Tier | Model | Use for | Never use for |
|---|---|---|---|
| T1 (bulk) | Claude Haiku 4.5 | single-`sorry` tactic search, `SAFETY:` comments, placeholder triage rows, test vector transcription, `static mut` → atomic, fuzz target scaffolds, metrics script pieces | changing theorem statements, architecture, deciding REMOVE for a boot-critical crate |
| T2 (design) | Claude Sonnet 5 | stub implementations (reassembly, exthdrs), Lean lemma libraries, boot bring-up, Aeneas integration, escalations from T1 | final sign-off on `spec-change` |
| T3 (review) | Claude Opus 5.5 / human | spec changes, axiom justification, security review of unsafe/Miri findings, release gate | bulk mechanical edits |

Rule of thumb: T1 gets work whose correctness a machine oracle can decide. Anything judged by taste goes to T2 or T3.

### 4.2 Oracle-gated loop (every work unit)

```
pick unit from queue (smallest, highest priority, deps satisfied)
  -> build context pack (file excerpt ≤ 400 lines, related defs, unit card)
  -> T1 attempt (≤ 3 tries, each try sees previous oracle error)
  -> ORACLE: unit-specific check  +  metrics ratchet  +  anti-cheat checks
       pass -> open PR (small), T3 spot-review 1 in 10 T1 PRs
       fail x3 -> escalate to T2 with full failure log (≤ 2 tries)
       fail -> mark BLOCKED with diagnosis, human queue
```

**Oracles per unit type**
| Unit type | Oracle |
|---|---|
| Lean `sorry` | `lake env lean <file>` succeeds; `sorry` count in file decreased; statement hash unchanged; `#print axioms <thm>` shows no new axioms |
| Axiom removal | same as above + axiom count decreased + all dependents still build |
| Stub function | crate unit tests + new tests for that function + clippy `-D warnings` + fuzz 60 s smoke |
| `SAFETY:` / unsafe | clippy `undocumented_unsafe_blocks` clean for crate + Miri tests pass |
| Placeholder triage | CSV row schema valid; REMOVE rows for boot-critical list rejected automatically |
| Boot | QEMU banner sequence test |

**Anti-cheat checks (automatic, non-negotiable)**
- No new `sorry`, `axiom`, `admit`, `native_decide`, `allow(...)`, `#[ignore]`, `todo!`, `unimplemented!`, `unreachable_unchecked`.
- No theorem statement edits (hash check) and no deletion of tests or theorems unless the PR is tagged by a human.
- No `unsafe` added without `SAFETY:`.
- The diff touches only files named in the unit card.

### 4.3 Unit card template (what a T1 model receives)

```yaml
id: WS1-W2-PageAlloc-thm-alloc_preserves_free_count
type: lean_sorry
file: specs/lean4/MVK/Phase2/PageAlloc.lean
target: "theorem alloc_preserves_free_count"
context_files: [MVK/Phase2/Common.lean]
allowed_edits: [specs/lean4/MVK/Phase2/PageAlloc.lean]   # proof body only
hints: ["try: unfold alloc; simp [Common.free_count]; omega"]
oracle: "lake env lean MVK/Phase2/PageAlloc.lean && ./scripts/check_unit.sh $id"
max_attempts: 3
escalate_to: T2
```

A generator script (`scripts/units/generate.py`) builds cards automatically from: `sorry` locations, constant-body functions, `unsafe` blocks lacking `SAFETY:`, `static mut` sites, and placeholder crates. That yields roughly 249 + 255 + ~620 + 197 + 141 ≈ **1,460 mechanical units**, most of them T1.

### 4.4 Orchestration
- Use a Workflow script per wave (pipeline: generate cards → T1 attempt → oracle → escalate), with at most 8–10 concurrent agents, each in its own git worktree.
- Batch one PR per crate or Lean file, capped at 300 lines. Humans merge; agents never push to `main`.
- Track state in `docs/roadmap/units_status.csv` (id, tier, attempts, status, PR), which feeds the dashboard.

### 4.5 Throughput & cost assumptions (to validate in Week 2 pilot)
| Metric | Pilot target |
|---|---|
| T1 first-pass success on `sorry` units (wave 1) | ≥ 40% |
| T1 success after 3 attempts | ≥ 65% |
| Escalation rate to T2 | ≤ 30% |
| Human-blocked rate | ≤ 5% |
| Median unit wall time | ≤ 10 min |
| Spot-review defect rate on merged T1 PRs | ≤ 2% |

If the pilot misses these targets, shrink unit size and improve the hints (for example, a shared tactic cookbook in `specs/lean4/TACTICS.md`) before scaling up.

---

## 5. New evolution features (next-generation kernel)

These come after WS0–WS5 exit gates. Each one has a verification story, not only a feature story.

| ID | Feature | Why it matters | Verification criterion | Metric |
|---|---|---|---|---|
| F1 | **Verified policy VM** (eBPF-subset) replacing ad-hoc firewall rules | Hot-loadable security policy without new kernel code | Lean-proved verifier: termination, memory safety, bounded stack; verifier extracted via Aeneas | 100% of loaded programs pass the proved verifier; 0 fuzz escapes |
| F2 | **Certified TinyML guard** | The AI detector cannot crash or stall the kernel | Integer interval analysis proves no overflow and output ∈ [0,1000]; WCET bound derived statically; weights hash-anchored in `.rodata` | proved WCET ≤ 15 µs @ reference clock; measured p99 < bound |
| F3 | **"AI proposes, guard disposes"** learned heuristics (scheduler hints, prefetch, rate limits) | Adaptive performance without trusting the model | Proven safety envelope: any model output is clamped to a verified range; fallback to the deterministic policy on timeout | 0 envelope violations; ≥ 10% p99 latency win on a benchmark, or feature disabled |
| F4 | **Capability-based syscalls** (CapBAC as primary, not add-on) | Least privilege by construction | Lean theorem: no syscall succeeds without a capability; monotone drop | 100% syscalls routed through the cap check |
| F5 | **Measured boot + attestation chain** tied to `immutable_logs` | Remote verifiable integrity | Merkle log extracted & proven append-only; TPM/SBI-based measurement | attestation quote verifies in CI QEMU run |
| F6 | **Reproducible builds + SBOM + signed artifacts** | Supply-chain trust | bit-identical double build; `cargo auditable`; `cargo deny` | `repro.build = yes`, 0 advisories |
| F7 | **AI-assisted proof & fuzz factory** (dev-time only, never in the TCB) | Keeps the proof debt at zero as code grows | Lean kernel is the sole judge; LLM-generated fuzz seeds are only inputs | `lean.sorry` stays 0 across releases; fuzz coverage ↑ |
| F8 | **Memory-safety hardware readiness** (RISC-V Pointer Masking / CHERI-RISC-V, x86 CET shadow stacks) | Defense in depth for residual `unsafe` | feature-gated; boot test with the feature enabled in QEMU | boots with CET/Zicfiss enabled |
| F9 | **Panic-free proof for the core set** | "No kernel panics" becomes a checked property | `no_panic` link-time check or Kani `#[kani::proof]` absence-of-panic harnesses | 0 reachable panics in the core set |
| F10 | **Formal isolation for the AI enclave IPC** (`ai_bridge`) | AI runtime compromise cannot reach kernel memory | Lean refinement proof over extracted ring buffer + Kani for DMA ownership | theorems on extracted code ≥ 10 |

---

## 6. Phased roadmap & exit criteria

| Phase | Weeks | Scope | Exit criteria (all must hold) |
|---|---|---|---|
| **P0 Truth** | 1–2 | WS0, workflow pilot (Lean wave 1 + 20 `SAFETY:` units) | `metrics.json` in CI with ratchet; README numbers generated; pilot KPIs measured |
| **P1 Foundations** | 3–6 | WS1 waves 2–3, WS2 P0 start, WS3 core set, WS2.4 placeholder triage, WS5 start | `lean.sorry ≤ 130`; placeholder decisions 141/141; Miri green on core set; `static mut ≤ 100` |
| **P2 Real kernel** | 7–10 | WS2 P0 done, WS5 boot, WS3 finish, WS4 pilot | both arches boot in CI; P0 crates stub-free; `safety_ratio` = 1.0 core; first 10 extracted theorems |
| **P3 Verified core** | 11–16 | WS1 waves 4–5, WS4 full, WS6, WS7 | `lean.sorry = 0`, `axiom ≤ 30` documented; ≥ 40 extracted theorems; coverage ≥ 70% core; perf numbers published |
| **P4 Evolution** | 17+ | F1, F2, F4, F5, F6 first; then F3, F8–F10 | per-feature criteria in §5 |

**Release gate for v12.0:** all P3 criteria met, all hard gates in §2 green, T3/human security review signed, and the traceability matrix regenerated with a "Rust-linked" column.

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Some `sorry` sit on false or ill-posed theorems (especially NAT/SCTP) | High | High | T1 cannot change statements; unprovable units escalate to T3 for `spec-change` review. Track `spec-change` count. |
| Aeneas/hax does not handle the FFI-heavy crates | Medium | High | Extract only pure-logic cores (split `*_core` modules without FFI); use Kani for the rest |
| Low-tier models game the oracles | Medium | High | anti-cheat checks §4.2, statement hashes, 10% spot review, ratchet |
| Scope creep from 316 crates | High | Medium | G6 triage reduces the surface; the core set gets strict gates first |
| Boot bring-up takes longer than planned (interrupts, paging) | Medium | Medium | riscv64 first (simpler platform), x86_64 second; reuse `examples/demo_kernel` learnings |
| Removing inflated claims hurts the project narrative | Low | Medium | Publish a "v12 honesty" changelog; verified numbers are the stronger story |

---

## 8. Immediate next actions (first 5 working days)

1. Write `scripts/metrics.py` and commit `metrics.baseline.json` from `041622e` (T1 with a spec, T2 review).
2. Fix `verify_specs.sh` to fail on live `sorry` in "complete" files and on `lake build` errors. Measure `lean.build`.
3. Generate unit cards for Lean wave 1 (12 `sorry`) and 20 `SAFETY:` units in `ebpf_firewall`; run the T1 pilot; record KPIs from §4.5.
4. Open an issue: `ai_detector::activation_slice` aliasing (`&self → &mut`), with a Miri repro test.
5. Draft `placeholder_triage.csv` (T1), then a human decides the boot-critical list.
6. Update README/AGENTS.md claims with measured numbers, and mark the traceability matrix as "model-verified, Rust linkage pending".
