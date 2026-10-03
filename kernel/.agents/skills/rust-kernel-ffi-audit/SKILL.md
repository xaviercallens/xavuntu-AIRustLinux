---
name: rust-kernel-ffi-audit
description: >-
  Audits, compiles, and verifies C ABI struct layouts, manual bitfield packing, pointer alignment, and multi-architecture target builds (x86_64 and RISC-V) across all 297 RunuX kernel crates. Use when fixing compilation errors, checking FFI struct padding, or adding new kernel subsystem crates.
---

# Rust Kernel Compilation & FFI Structure Layout Audit

## Overview
This skill provides a rigorous, architecture-aware methodology for compiling, auditing, and debugging `#![no_std]` Rust modules in the **RunuX** kernel. When translating or maintaining kernel subsystems, compiler padding discrepancies, incorrect pointer provenance, or missing FFI bindings can cause silent memory corruption. This skill guarantees 100% C ABI compatibility and zero-warning compilation across x86_64 and RISC-V architectures.

---

## Workflows

### 1. Workspace Multi-Target Compilation Audit
Always redirect `cargo check` operations to a dedicated scratch target directory to prevent lock contention, root cache pollution, and disk exhaustion:

```bash
# 1. Native / x86_64 compilation check
CARGO_TARGET_DIR="/tmp/runux_target" cargo check --workspace --quiet

# 2. RISC-V 64-bit cross-compilation check (SpacemiT K1/K3)
CARGO_TARGET_DIR="/tmp/runux_target" cargo check --workspace --target riscv64gc-unknown-none-elf --quiet

# 3. Deny-all linting check
CARGO_TARGET_DIR="/tmp/runux_target" cargo clippy --workspace -- -D warnings
```

### 2. C ABI Struct Matching & Bitfield Packing
C structure matching requires explicit compiler layout attributes. Rust's compiler adds alignment padding by default, which corrupts network packet headers and device DMA boundaries.

#### Audit Checklist:
1. **Explicit `#[repr(C)]`**: Verify every FFI-shared struct declares `#[repr(C)]`.
2. **Manual Bitfield Packing**: Rust lacks native bitfield syntax. Pack C bitfields manually into fixed-width integers:
   ```rust
   #[repr(C)]
   pub struct iphdr {
       pub version_ihl: u8, // Packed: version (high 4 bits) + IHL (low 4 bits)
       pub tos: u8,
       pub tot_len: u16,
       pub id: u16,
       pub frag_off: u16,
       pub ttl: u8,
       pub protocol: u8,
       pub check: u16,
       pub saddr: u32,
       pub daddr: u32,
   }

   impl iphdr {
       #[inline(always)]
       pub fn version(&self) -> u8 { self.version_ihl >> 4 }
       #[inline(always)]
       pub fn ihl(&self) -> u8 { self.version_ihl & 0x0f }
       #[inline(always)]
       pub fn set_version_ihl(&mut self, version: u8, ihl: u8) {
           self.version_ihl = ((version & 0x0f) << 4) | (ihl & 0x0f);
       }
   }
   ```
3. **Compile-Time Size Assertions**: Guarantee exact byte sizes matching C headers:
   ```rust
   const _: () = assert!(core::mem::size_of::<iphdr>() == 20);
   ```

### 3. Safe Wrapper & Newtype Patterns
Never expose raw pointers in module-level APIs. Encapsulate raw C handles inside zero-cost Newtypes with RAII `Drop` deallocation:

```rust
pub struct SafeSkb {
    ptr: *mut kernel_types::sk_buff,
}

impl SafeSkb {
    /// # Safety
    /// Caller must guarantee `raw` is a valid, allocated sk_buff pointer.
    pub unsafe fn from_raw(raw: *mut kernel_types::sk_buff) -> Option<Self> {
        if raw.is_null() {
            None
        } else {
            Some(Self { ptr: raw })
        }
    }

    #[inline(always)]
    pub fn as_ptr(&self) -> *const kernel_types::sk_buff {
        self.ptr
    }
}

impl Drop for SafeSkb {
    fn drop(&mut self) {
        // SAFETY: The inner pointer is guaranteed valid and non-null
        unsafe {
            kernel_types::kfree_skb(self.ptr);
        }
    }
}
```

### 4. Handling Unaligned Pointer Access
Dereferencing unaligned pointers or creating mutable references (`&mut`) to unaligned struct fields is immediate Undefined Behavior:
```rust
// WRONG: Creates an unaligned reference
// let ref_val = &mut (*raw_ptr).unaligned_field;

// CORRECT: Uses addr_of_mut! and unaligned writes
use core::ptr::addr_of_mut;
unsafe {
    core::ptr::write_unaligned(addr_of_mut!((*raw_ptr).unaligned_field), new_value);
}
```

---

## Common Pitfalls
* **Shared Target Dir**: Running `cargo build` without setting `CARGO_TARGET_DIR`, leading to multi-gigabyte build bloat in the workspace.
* **Implicit Alignment**: Assuming `#[repr(C)]` eliminates padding between mixed-width fields (e.g. `u8` followed by `u32`). Check offsets with `core::mem::offset_of!`.
* **Panicking Unwraps**: Using `.unwrap()` or `.expect()` inside `#![no_std]` crates. Use `?` operator or explicit `match` propagating `-EINVAL` / `-ENOMEM`.
