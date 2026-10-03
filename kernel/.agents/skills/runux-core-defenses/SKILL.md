---
name: runux-core-defenses
description: >-
  Audits, verifies, and executes the RunuX Core Defenses active interception pipeline, LMS state machine transitions, TinyML real-time classification, Lean 4 formal contract congruence, and requirement sequence ID traceability.
---

# RunuX Core Defenses Operational Skill

## Overview
This skill defines standard operating procedures, audit checklists, and verification workflows for the **RunuX Core Defenses** active interception pipeline. The defense pipeline sits in Ring 0 before the dispatch table of the 297 kernel modules, coordinating:
1. `crates/syscall_table` pre-dispatch interception (`REQ-RCD-001`).
2. `crates/ai_bridge` lock-free SPSC audit ring buffer (`REQ-RCD-002`).
3. `crates/ebpf_firewall` W^X and integer Shannon entropy enforcement (`REQ-RCD-003`, `REQ-RCD-005`).
4. `crates/ai_detector` bare-metal sub-15 µs quantized INT8 classification (`REQ-RCD-004`).
5. `crates/immutable_logs` heapless Merkle audit tree with monotonic sequence IDs (`REQ-RCD-006`).
6. LMS Dynamic Security Policy State Machine (`REQ-RCD-007`).
7. Pessimistic Security Precedence (`REQ-RCD-008`).
8. Lean 4 Formal Specification Invariants with Zero `sorry` (`REQ-RCD-009`).
9. Multi-Architecture x86_64 and RISC-V `#![no_std]` Verification (`REQ-RCD-010`).

---

## Standard Workflows

### 1. Unified Automated Quality Gate & Traceability Matrix
The primary workflow is automated via `scripts/workflow.py`:

```bash
# Run the complete end-to-end quality gate
python3 scripts/workflow.py --all

# Generate or update the requirement traceability matrix
python3 scripts/workflow.py --matrix

# Verify only Lean 4 formal specifications
python3 scripts/workflow.py --verify-lean

# Verify only Rust unit tests for all REQ-RCD items
python3 scripts/workflow.py --verify-tests

# Verify multi-architecture cross-compilation
python3 scripts/workflow.py --verify-arch
```

### 2. Auditing Formal Proof Congruence
Ensure that every functional invariant in `crates/` is mapped to a corresponding Lean 4 theorem in `specs/lean4/MVK/RunuxDefenses.lean`:

```bash
# Run Lean 4 Lake build
cd specs/lean4 && lake build

# Audit for proof stubs (zero tolerance for sorry)
grep -rn "sorry" specs/lean4/MVK/RunuxDefenses.lean

# Run the official verification script
./specs/scripts/verify_specs.sh
```

### 3. Auditing Ring 0 Ingress Latency
Verify that active defense interception satisfies the sub-15 µs real-time SLA:

```bash
# Execute the microbenchmark and chaos test suite
python3 scripts/test_runux_defenses.py
```
*Target*: Mean latency must remain $< 2.00 \ \mu\text{s}$ per syscall, and TinyML scoring must execute in $< 15.0 \ \mu\text{s}$.

### 4. Requirement Sequence ID Checklist

When modifying or extending defense features, verify adherence to the sequence ID scheme:
* `REQ-RCD-001`: Does `crates/syscall_table` intercept before module dispatch?
* `REQ-RCD-002`: Does `crates/ai_bridge` maintain bounded indexing without dynamic allocation?
* `REQ-RCD-003`: Are `mprotect` and `mmap` simultaneously requesting write and exec blocked?
* `REQ-RCD-004`: Does `crates/ai_detector` score inside $[0, 1000]$ without exceeding 15 µs?
* `REQ-RCD-005`: Does high Shannon entropy ($\ge 7.2$ bits) trigger deep inspection?
* `REQ-RCD-006`: Does each audit event increment the sequence ID and update the Merkle root?
* `REQ-RCD-007`: Are policy escalations monotonic and de-escalations gated by root signatures?
* `REQ-RCD-008`: Does `BlockKill` unconditionally dominate in multi-rule evaluations?
* `REQ-RCD-009`: Is the theorem proved in Lean 4 with zero `sorry`?
* `REQ-RCD-010`: Does the crate build cleanly on both x86_64 and RISC-V?
