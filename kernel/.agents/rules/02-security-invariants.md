# Rule: Kernel Security Invariants & Exploit Mitigation

When writing, reviewing, or modifying code in **RunuX**, you must enforce the following security invariants:

## 1. Unsafe Code Boundaries & Mandatory Proof Comments
- **Minimize `unsafe` Scope**: `unsafe` blocks must be kept minimal, wrapping only the exact foreign function call or hardware instruction. Never enclose business logic, loops, or complex branching in an `unsafe` block.
- **Mandatory `// SAFETY:` Invariant**: Every `unsafe` block must be preceded by a formal comment explaining why the operation is sound:
  ```rust
  // SAFETY: The skb pointer is non-null, 64-bit aligned, and owned by the current
  // execution context with exclusive write access proven by the SafeSkb wrapper.
  unsafe {
      c_bindings::kfree_skb(self.raw_ptr);
  }
  ```
- **Prohibited in Algorithmic Crates**: Non-hardware crates (e.g. routing algorithms, FIB lookup, hash tables) must enforce `#![forbid(unsafe_code)]`.

## 2. Undefined Behavior (UB) & Pointer Provenance
- **Miri Compliance**: All unit test suites must pass clean under the Mid-level IR Interpreter (Miri). Zero pointer provenance violations, strict-aliasing breaks, or uninitialized memory reads are allowed.
- **KASAN Memory Poisoning**: Track shadow memory validity on all slab/slub allocations. Guard pages must be verified before and after buffer boundaries.

## 3. Exploit Mitigations
- **Kernel Address Space Layout Randomization (KASLR)**: No hardcoded physical or virtual memory addresses in module logic.
- **Kernel Control-Flow Integrity (kCFI)**: Function pointer dispatches must adhere to exact clang/LLVM type signatures to prevent IDT or syscall table hijack attacks.
- **Least-Privilege Architectural Decoupling**: Isolate user-facing parsers (e.g. packet ingress, netlink attributes) from Ring-0 core scheduling structures so parsing bugs cannot yield privileged compromise.

## 4. Supply Chain & Vulnerability Gates
- Every newly introduced external dependency must be audited using `cargo audit`. No crate with an active RustSec advisory may be merged into the dependency tree.
