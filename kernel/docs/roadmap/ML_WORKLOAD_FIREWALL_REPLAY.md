# Replaying Real ML Workload Traces Through `ebpf_firewall`/`ai_detector` (M4, Round 2)

**Status: real, n=620,934 real events replayed through real,
unmodified code. The headline finding is not "the classifier has a
false-positive problem" — it's that the classifier appears to have
never been trained at all.** Read past the summary numbers before
citing this document; the framing matters more than the percentages.

This is the second half of Candidate C / M4 from
`TPU_ACCELERATOR_IMPROVEMENT_PLAN.md`, following
`ML_WORKLOAD_SYSCALL_TRACES.md`'s trace collection. It replays those
same two benign JAX/TPU workloads (`device_enum`, `matmul_512x512`,
n=10 runs each) through this project's actual `ebpf_firewall::evaluate_syscall`
and `ai_detector::evaluate_pid_event` — the real Rust functions, not a
reimplementation or simulation of them.

## What was fixed first

The original trace capture (`ML_WORKLOAD_SYSCALL_TRACES.md`) did not
record the calling instruction pointer, which `ebpf_firewall`'s
kernel-address-spoofing check needs (`ctx.ip == 0 || ctx.ip >= kernel_base`).
Rather than feed that check a fabricated placeholder IP or skip it
silently, the same two workloads were **re-captured** with `strace -f
-tt -i` (real IPs), same n=10 each, on a second bounded spot TPU VM
(`v5litepod-1`, `us-west4-a`, deleted after ~15 minutes). `capture_traces.sh`
now captures `-i` by default so future runs get this for free.

## The replay harness

`examples/firewall_replay` reads a structured events CSV (produced by
`scripts/telemetry/parse_replay_events.py` from the raw `strace`
output — real pid, real syscall number looked up against this
machine's own `/usr/include/x86_64-linux-gnu/asm/unistd_64.h`, real
instruction pointer, and real `PROT_*` flags parsed out of `mmap`/
`mprotect` call arguments) and replays every event, in captured order,
through both real detection layers. **`entropy_score` is honestly left
at 0** for every event (`SyscallAuditEvent::new` never sets it) — no
real Shannon entropy over buffer contents was computed, since strace's
default output doesn't capture buffer contents and fabricating one
would defeat the purpose of testing against real data. This means the
entropy-triggered `InspectDeep` path in `CoreDefenseFilter` is not
exercised by this round; a real gap, stated here rather than implied
away.

Total: 620,934 real events across 20 runs (10 per workload).

## Layer 1: `ebpf_firewall::evaluate_syscall` (the rule-based filter) — clean and explicable

| Metric | Value |
|---|---|
| Total flagged | 20 / 620,934 (0.0032%) |
| Verdict breakdown | 20 `InspectDeep`, 0 `BlockKill`, 0 `Rollback` |
| Pattern | **Exactly 1 per run, every single run, 20/20** |

Every single flag is the same real call: `memfd_create("xla-jit-exec", 0)`
— XLA's JIT compiler creating an anonymous memory-backed file to hold
compiled TPU program code. `CoreDefenseFilter` unconditionally flags
any `memfd_create` or `ptrace` call as `InspectDeep` (see
`crates/ebpf_firewall/src/lib.rs`). Zero W^X violations
(`mprotect`/`mmap` with `PROT_WRITE|PROT_EXEC` together) were found in
any of the 620,934 real events — a genuinely clean result on that
check specifically.

**This is a real, honest design tension, not a bug**: anonymous
executable-memory creation via `memfd_create` is exactly the pattern a
firewall watching for fileless-malware/shellcode-injection techniques
should flag — and it's also exactly what a JIT compiler for any
high-performance ML framework legitimately does. The rule as written
cannot tell these apart from syscall metadata alone. This is a real
example of the false-positive-vs-detection tradeoff this kind of rule
makes, demonstrated with real data instead of asserted abstractly.

## Layer 2: `ai_detector`'s TinyML classifier — the real finding

| Metric | Value |
|---|---|
| Total flagged | 762 / 620,934 (0.1227%) |
| Verdict breakdown | 297 `BlockKill`, 55 `Rollback`, 410 `InspectDeep` |
| Runs with zero flags | 9 / 20 |
| Runs with substantial flags | 11 / 20 (one run alone: 263 `InspectDeep` events) |
| Syscalls most associated with `BlockKill` | `mbind` (153), `mmap` (144) |

Full breakdown: [`ml_workload_traces/firewall_replay_results/firewall_replay_summary.csv`](ml_workload_traces/firewall_replay_results/firewall_replay_summary.csv)
(per-run tallies) and [`firewall_replay_flags.csv`](ml_workload_traces/firewall_replay_results/firewall_replay_flags.csv)
(every individual non-`Pass` verdict with context).

**Why this is the more important finding, and why the framing matters:**
`L1_WEIGHTS`/`L1_BIAS`/`L2_WEIGHTS`/`L2_BIAS` in `crates/ai_detector/src/lib.rs`
are introduced only as "Statically compiled TinyML Model Weights in
.rodata" — there is no training script, no dataset, no evaluation
metric, and no documentation anywhere in this repository describing
how these specific numbers were derived. Grepped for directly; found
nothing. The most defensible reading is that **these are placeholder
values that make the tensor-arena/quantization plumbing exercisable,
not a fitted model.**

Given that, the wildly inconsistent behavior across nominally-identical
runs of the *same* benign workload (0 flags in 9 runs; up to 33
`BlockKill` verdicts in others) is not evidence that a trained
classifier has a high false-positive rate on accelerator workloads —
it's evidence that **an arbitrary, untrained weight matrix produces an
arbitrary function of its inputs**, and real syscall-number sequences
from real ML workloads happen to hit large activations for some
specific window contents (e.g. certain `mbind`/`mmap` sequences) and
not others, for reasons that don't reflect any learned notion of
"anomalous." The real, actionable conclusion is: **any meaningful
false-positive/detection-rate evaluation of `ai_detector` is blocked on
training it first** — this replay cannot and does not substitute for
that. That's a bigger, more useful finding for the roadmap than a
tuning number would have been.

## What this does and doesn't show

- **Does show:** the rule-based firewall layer's real, deterministic,
  fully-explicable behavior on two real ML workloads (620,934 real
  events) — clean except for one specific, understood, by-design
  tension (JIT compilation vs. anonymous-executable-memory detection).
  Does show that the classifier layer's weights have no evident
  training provenance, demonstrated by feeding them real data and
  observing behavior inconsistent with a fitted model responding to
  real signal.
- **Doesn't show:** the "sub-15µs" classifier latency target (not
  measured here at all — this is an offline batch replay, not a
  timed kernel-path measurement). Doesn't show anything about the
  entropy-based `InspectDeep` path (no real entropy was computed; see
  above). Doesn't show what `ai_detector` *would* do if properly
  trained — that requires an actual training pipeline and a labeled
  dataset, neither of which exists yet. Doesn't include any malicious
  or synthetic attack traces (still not attempted, per the original
  M4 scoping in `TPU_ACCELERATOR_IMPROVEMENT_PLAN.md`).

## Cost

One additional spot `v5litepod-1` TPU VM (the original M4 trace
collection VM had already been deleted; re-capturing with `-i` needed
a fresh one), ~15 minutes lifetime, deleted immediately after
download. The replay itself is pure offline computation — no cloud
resources needed for that part at all.

## Reproduce this yourself

```bash
# Capture (needs TPU access):
bash docs/roadmap/ml_workload_traces/capture_traces.sh   # now captures -i by default

# Parse (needs an x86_64 Linux machine for the syscall-number table):
python3 scripts/telemetry/parse_replay_events.py ~/ml_traces \
  --workloads device_enum:device_enum matmul_512x512:matmul \
  --runs 10 --out /tmp/replay_events.csv

# Replay (pure computation, no cloud/hardware needed):
cargo build --release -p firewall_replay
./target/release/firewall_replay /tmp/replay_events.csv /tmp/results
```

## Next round (not started)

Training `ai_detector`'s classifier on a real, labeled dataset (benign
traffic like this, plus real or realistic attack traces) before any
FPR/TPR number from it can be trusted; only then would a repeat of
this exact replay produce a meaningful evaluation rather than a
demonstration of untrained-weight behavior. Synthesizing labeled
attack traces (per the original M4 scope) remains separate,
open-ended, unstarted work.
