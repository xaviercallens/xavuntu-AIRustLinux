---
name: lean4-spec-verification
description: >-
  Provides steps and methodologies for running Lean 4 verification checks, parsing proof statistics, and tracing mathematical stubs (sorry) inside formal kernel specifications.
---

# Lean 4 Formal Specification Verification Skill

## Overview
This skill details the execution, analysis, and transition of formal mathematical specifications written in Lean 4 for the **Rust Linux Minimum Viable Kernel (MVK)**. It provides a structured methodology to trace proof obligations, run verification scripts, check type correctness, and resolve mathematical stubs (`sorry`) to achieve 100% formal verification completeness.

---

## Verification Workflows

### 1. Running Specification Verification
To check type-correctness across all 19 specifications in the repository, run the workspace verification script:
```bash
./specs/scripts/verify_specs.sh
```
This script type-checks all specification `.lean` files and updates the proof status report at `./specs/PROOF_STATUS_REPORT.md`.

### 2. Tracing and Auditing Stubs (`sorry` metrics)
Type-correctness in Lean 4 means the specification defines valid logical constraints. However, parts of the proofs may be temporarily stubbed using the `sorry` tactic.
* **Audit Steps**:
  1. Parse the output of `verify_specs.sh` or check the generated status report.
  2. Locate stubs under specific specifications (e.g. `Printk.lean` or `Common.lean`).
  3. Formulate the proof strategy by listing the inductive hypotheses or helper lemmas required to resolve the `sorry`.
  4. Ensure any modification to Lean 4 specifications preserves exact logical mapping to their corresponding Rust functional code.

---

## Common Mistakes
* **Lean Version Mismatch**: Running a different version of Lean than defined in `lean-toolchain`. Always use the project-defined toolchain.
* **Ignoring Stubs**: Confusing type-checking success with completed proof obligations. A spec that typechecks but has `sorry` statements is only partially verified.
* **Mismatched Invariants**: Modifying a Lean 4 specification structure so it no longer represents the functional Rust implementation. Specifications and Rust implementations must remain structurally congruent.
