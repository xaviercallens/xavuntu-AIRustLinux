---
name: kernel-security-hardening
description: >-
  Audits and executes kernel security hardening procedures including Miri undefined behavior analysis, KASAN memory monitoring, cargo-fuzz libFuzzer campaigns, and safety invariant proofs. Use when auditing unsafe blocks, running security regressions, or preparing release security gates.
---

# Kernel Security Hardening & Exploit Mitigation Skill

## Overview
This skill provides structured procedures to audit and verify memory safety, eliminate Undefined Behavior (UB), and enforce defense-in-depth mitigations across the **RunuX** kernel. It integrates dynamic interpretation (Miri), kernel address sanitization (KASAN), coverage-guided fuzzing, and cryptographic dependency scanning.

---

## Security Verification Workflows

### 1. Dynamic Undefined Behavior (UB) Detection via Miri
Miri interprets Rust Mid-level IR (MIR) to detect pointer provenance bugs, memory leaks, uninitialized memory reads, and aliasing violations:

```bash
# Run unit tests through Miri (requires nightly)
cargo +nightly miri test -p kernel_types
cargo +nightly miri test -p core
```

#### Key Miri Flags for Kernel Auditing:
* `-Zmiri-strict-provenance`: Enforces strict integer-to-pointer cast rules.
* `-Zmiri-symbolic-alignment-check`: Catches unaligned pointer dereferences even on platforms that permit unaligned reads in hardware.

### 2. Kernel Address Sanitizer (KASAN) Monitoring
Run the dedicated KASAN monitor script to track shadow memory allocation and watch for out-of-bounds slab writes:

```bash
# Execute KASAN continuous monitoring
./scripts/kasan_monitor.sh
```

Ensure that all page frames and slab caches are tracked in the KASAN bitmap (`crates/kasan`). Any detected access to a poisoned byte triggers an immediate kernel diagnostic abort before memory corruption can spread.

### 3. Coverage-Guided Fuzzing (libFuzzer)
Run the fuzzing harnesses targeting packet parsing and FIB route lookup:

```bash
cd fuzz

# 1. Fuzz raw network packet ingress (TCP/IP/Netfilter headers)
cargo +nightly fuzz run fuzz_packet -- -max_total_time=60 -workers=4

# 2. Fuzz FIB routing table lookups and trie mutations
cargo +nightly fuzz run fuzz_routing -- -max_total_time=60 -workers=4
```

### 4. Supply-Chain & Advisory Audit
Verify that no transitive or direct dependencies carry known vulnerabilities from the RustSec Advisory Database:

```bash
cargo audit
```

### 5. `unsafe` Block Invariant Checklist
When writing or auditing an `unsafe` block:
1. **Scope Reduction**: The block must enclose only the exact FFI call, hardware register write (`read_volatile` / `write_volatile`), or raw pointer conversion.
2. **Mandatory Comment**: The comment must explicitly start with `// SAFETY:` and satisfy the triple requirement:
   - **Pointer Validity**: Explain why the pointer is guaranteed non-null and points to initialized memory.
   - **Alignment**: Confirm memory alignment guarantees.
   - **Aliasing & Lifetime**: Prove no aliasing `&mut` reference exists concurrently.
3. **Contract Invariants**: Guard the input parameters with design-by-contract assertions:
   ```rust
   debug_assert!(!ptr.is_null(), "Pointer cannot be null");
   debug_assert!(len <= MAX_PACKET_LEN, "Packet length exceeds MTU");
   ```

---

## Common Pitfalls
* **Masking UB with Transmute**: Using `core::mem::transmute` across types of differing sizes or layout requirements. Use explicit pointer casts or safe conversions (`From`/`TryFrom`).
* **Ignoring Fuzz Timeouts**: Treating a fuzz timeout as a non-issue. Timeouts often indicate algorithmic complexity attacks (e.g. infinite loop in packet parsing).
* **Missing Invariant Comments**: Merging `unsafe` blocks without `// SAFETY:` comments breaks the repository's security compliance gate.
