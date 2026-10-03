---
name: lean4-formal-proofs
description: >-
  Executes, verifies, and audits Lean 4 mathematical specifications across all 12 formal verification phases of the RunuX kernel. Use when checking proof completeness, resolving proof obligations, eliminating 'sorry' stubs, or verifying theorem congruence with Rust kernel contracts.
---

# Lean 4 Formal Specification Verification Skill

## Overview
This skill provides the methodology, tooling, and audit procedures for running Lean 4 mathematical proofs in the **RunuX** kernel. The repository contains formal machine-checked specifications across 12 phases covering memory safety, CFS scheduler fairness, conntrack state transitions, IPv4/IPv6 routing termination, and GCP IDPF DMA drivers. Every proof in the repository must maintain **zero `sorry` tactics**.

---

## Formal Verification Workflows

### 1. Running the Full Specification Suite
To execute the workspace-wide verification script and update the status report:

```bash
# Run specification verification and generate PROOF_STATUS_REPORT.md
./specs/scripts/verify_specs.sh
```

### 2. Building via Lean 4 Lake Package Manager
To build and check the formal proofs directly using Lean 4:

```bash
cd specs/lean4
lake update
lake build
```

### 3. Auditing for Mathematical Stubs (`sorry`)
In Lean 4, a file that passes type-checking may still contain unresolved obligations if theorems use the `sorry` tactic. To audit the codebase for stubs:

```bash
# Search for any unresolved proof obligations across all specifications
grep -rn "sorry" specs/lean4/
```

#### Resolution Strategy:
1. Identify the failing theorem or lemma and its goal state.
2. Determine if the obligation requires:
   - **Inductive Invariant**: Strengthening the induction hypothesis on packet length or trie depth.
   - **Case Exhaustion**: Handling edge cases (e.g. empty buffers, zero-length prefixes, null handles).
   - **Arithmetic Bounding**: Applying `omega` or `linarith` tactics for pointer offset bounds.
3. Ensure the proven theorem preserves exact structural congruence with the corresponding Rust code.

### 4. Mapping Lean 4 Theorems to Rust Contracts
Specifications must mirror the invariants enforced in Rust:

| Kernel Domain | Rust Invariant | Lean 4 Proved Theorem |
| :--- | :--- | :--- |
| **CFS Scheduling** | `sched_fair::update_curr()` | `Theorem cfs_vruntime_monotonic` |
| **Memory Allocator** | `page_alloc::alloc_pages()` | `Theorem buddy_allocator_no_double_free` |
| **Routing** | `fib_trie::fib_table_lookup()` | `Theorem prefix_matching_terminates` |
| **IDPF Driver** | `SafeDmaQueue::enqueue()` | `Theorem dma_buffer_boundary_isolated` |
| **Conntrack** | `nf_conntrack_proto_tcp` | `Theorem tcp_state_machine_deterministic` |

---

## 12 Verification Phases Reference

* **Phase 1: Architecture Setup** (`InitMain.lean`, `Printk.lean`, `ArchSetup.lean`)
* **Phase 2: Memory Safety** (Bounded buffer access, slab allocator safety)
* **Phase 3: Conntrack Protocol** (TCP/UDP/ICMP/SCTP state machines, NAT core)
* **Phase 4: IPv4 Core** (ARP, ICMP, UDP, routing table correctness)
* **Phase 5: IPv6 Core** (IPv6 extension headers, flow labels)
* **Phase 6: Routing** (FIB trie operations, prefix matching termination)
* **Phase 7: Netfilter & Sockets** (Packet filtering chains, socket lifecycle)
* **Phase 8: Scheduling** (CFS vruntime monotonicity, $O(\log n)$ bounds)
* **Phase 9: Memory Management** (Buddy allocator, OOM safety)
* **Phase 10: VFS & Filesystem** (Inode locking, dcache consistency)
* **Phase 11: Hardware** (PCI bus probing, MMIO boundary isolation)
* **Phase 12: GCP Drivers** (IDPF zero-copy buffers, Hyperdisk DMA)

---

## Common Pitfalls
* **Toolchain Desynchronization**: Running a Lean version different from the one pinned in [`lean-toolchain`](file:///home/xavkal/xdev/rust-linux-mini-kernel/lean-toolchain).
* **Vacuous Truths**: Formulating a theorem with mutually contradictory hypotheses ($P \land \neg P \implies Q$), which proves trivially but provides zero safety guarantees.
* **Specification Drift**: Changing a Lean 4 struct without updating the corresponding `#[repr(C)]` Rust struct in `kernel_types`.
