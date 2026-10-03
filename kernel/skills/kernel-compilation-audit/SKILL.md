---
name: kernel-compilation-audit
description: >-
  Provides methodology and tools for auditing, compiling, and fixing errors or warning diagnostics in `#![no_std]` and FFI-heavy systems programming environments.
---

# Kernel Compilation & FFI Structure Layout Audit

## Overview
This skill implements a rigorous, architecture-aware methodology for compilation audits and structural layout verification in the **Rust Linux Minimum Viable Kernel (MVK)**. When migrating kernel modules, small compiler padding differences or incorrect pointer conversions can lead to silent data corruption. This skill details how to run target builds safely, parse complex compilation errors, and guarantee 100% GCC binary ABI compatibility.

---

## Quick Start

### 1. Build and Audit compilation status
Always redirect Cargo check operations to the safe target-dir to avoid conflict and build cache pollution:
```bash
CARGO_TARGET_DIR="/Users/xcallens/.gemini/antigravity-ide/gravity/scratch/target" cargo check --workspace --quiet
```

---

## Audit Workflows

### 1. Parsing FFI Type Incompatibilities
In systems programming, compiler errors frequently stem from mismatching types between generated bindings and Rust-native module structures. 
* **Action Plan**:
  1. Identify the conflicting type in the compiler output (e.g. `__be16` vs `u16`).
  2. Map type shadows by using exact wrapper casts or `as` conversions instead of changing underlying FFI structs.
  3. Ensure that all raw pointer translations are insulated inside `unsafe` blocks accompanied by a formal `// SAFETY:` invariant statement.

### 2. Ensuring Struct Layout Layout Integrity (Anti-Padding)
C structure matching requires explicit compiler layout attributes. Rust's compiler adds padding by default to optimize field access, which breaks network packet boundaries.
* **Audit Checklist**:
  * Verify `#[repr(C)]` is defined on all FFI matching structures.
  * For structures utilizing C bitfields, pack the variables manually into a single byte matching GCC's ABI layout exactly:
    ```rust
    #[repr(C)]
    pub struct iphdr {
        pub version_ihl: u8, // Packed bitfield: version (4 bits) + ihl (4 bits)
        pub tos: u8,
        // ...
    }
    ```
  * Expose safe, zero-cost accessors:
    ```rust
    impl iphdr {
        #[inline(always)]
        pub fn version(&self) -> u8 { self.version_ihl >> 4 }
        #[inline(always)]
        pub fn ihl(&self) -> u8 { self.version_ihl & 0x0f }
    }
    ```

---

## Common Mistakes
* **Cache Pollution**: Forgetting to specify the scratch target directory, leading to full-disk errors or locked build processes.
* **Padding Mismatch**: Assuming `#[repr(C)]` is sufficient to handle bitfields. Always manually pack and check struct sizes.
* **Raw Pointer Dereferencing**: Accessing raw pointers without proving alignment guarantees.
