# Rust Linux Mini Kernel - Formal Specifications

This directory contains formal specifications for the Rust-based Linux kernel networking modules.

## Overview

The specifications use Lean-inspired notation to formally describe:
- Type definitions and invariants
- Safety properties and proof obligations
- Protocol correctness requirements
- ABI compatibility guarantees

## Specifications

### 1. Kernel Types Specification

**File:** [KERNEL_TYPES_SPECIFICATION.md](KERNEL_TYPES_SPECIFICATION.md)

Formal specification of all Linux kernel FFI types used in the Rust implementation:

- **Core FFI Types** - C primitive type mappings with size and alignment guarantees
- **Network Addresses** - IPv4 (`in_addr`), IPv6 (`in6_addr`), and netfilter address structures
- **Protocol Headers** - IPv4, IPv6, UDP, ESP header specifications with validity predicates
- **Socket Structures** - `inet_sock`, `ipv6_pinfo`, `udp_sock` with safety invariants
- **Packet Buffers** - `sk_buff` specification with linked-list properties
- **Netfilter** - Connection tracking structures and state machines
- **Safety Properties** - Memory safety, type safety, and concurrency safety axioms

**Key Properties:**
```lean
axiom repr_c_layout : ∀ (T : Type), has_repr_c(T) → c_compatible_layout(T)
axiom pointer_safety : ∀ (T : Type) (p : *T), p = null ∨ valid_ptr(p)
axiom temporal_safety : ∀ (T : Type) (p : *T), freed(p) → ¬accessible(p)
```

### 2. Scenario B Specifications

**Directory:** [../scenario_b_specs/](../scenario_b_specs/)

JSON-formatted specifications from the C++ to Rust translation pipeline:

- **orchestrator_spec.json** - Type mappings and ownership patterns (13KB)
- **datastructures_spec.json** - Container type specifications (17KB)
- **spectorust_report.json** - Translation metrics and convergence data
- **common_spec.json** - Common utility type mappings
- **pricingengine_spec.json** - Pricing engine domain logic
- **searchengine_spec.json** - Search algorithm specifications
- **cachemanager_spec.json** - Cache coherency specifications
- **dataloader_spec.json** - Data loading invariants
- **yamldataloader_spec.json** - YAML parsing specifications
- **testframework_spec.json** - Test framework contracts
- **intensivetestframework_spec.json** - Load testing specifications

See [scenario_b_specs/README.md](../scenario_b_specs/README.md) for details.

## Verification Approach

### Type-Level Verification

Rust's type system provides static guarantees:

```rust
#[repr(C)]  // Guarantees C-compatible layout
pub struct iphdr {
    pub version: __u8,  // Type-checked at compile time
    pub tot_len: __be16,  // Endianness tracked in types
    // ...
}
```

### Runtime Verification

Critical invariants are checked at runtime:

```rust
pub fn validate_ipv4_header(hdr: &iphdr) -> Result<(), Error> {
    if hdr.version != 4 {
        return Err(Error::InvalidVersion);
    }
    if hdr.ihl < 5 {
        return Err(Error::InvalidHeaderLength);
    }
    // ...
}
```

### Formal Methods Integration

Future work may include:
- Lean 4 theorem prover integration
- Coq verification of critical properties
- SMT solver integration for constraint checking

## Specification Language

### Notation

- `axiom` - Assumed property (verified by implementation)
- `def` - Defined predicate or function
- `Prop` - Proposition (true/false statement)
- `Type` - Type classification
- `∀` (forall) - Universal quantification
- `∃` (exists) - Existential quantification
- `→` (implies) - Logical implication
- `∧` (and) - Logical conjunction
- `∨` (or) - Logical disjunction
- `¬` (not) - Logical negation

### Example Specification

```lean
-- Define what it means for an IPv4 address to be a loopback address
def is_loopback (addr : in_addr) : Prop :=
  (addr.s_addr & 0xFF000000) = 0x7F000000

-- Property: All loopback addresses start with 127
axiom loopback_prefix :
  ∀ (addr : in_addr), is_loopback(addr) → (addr.s_addr >> 24) = 127
```

## Implementation Mapping

Each specification corresponds to concrete Rust implementations:

| Specification | Implementation | Status |
|--------------|----------------|--------|
| Core FFI Types | `crates/kernel_types/src/lib.rs` | ✅ Complete |
| IPv4 Header | `crates/kernel_types/src/lib.rs:80-92` | ✅ Complete |
| IPv6 Header | `crates/kernel_types/src/lib.rs:94-108` | ✅ Complete |
| Socket Structures | `crates/kernel_types/src/lib.rs:137-172` | ✅ Complete |
| Packet Buffer | `crates/kernel_types/src/lib.rs:248-262` | ✅ Complete |
| Netfilter | `crates/kernel_types/src/lib.rs:276-307` | ✅ Complete |

## Verification Status

### Completed

- ✅ Type definitions match kernel headers
- ✅ Size and alignment verified via `cargo check`
- ✅ ABI compatibility enforced by `#[repr(C)]`
- ✅ Pointer safety through Rust's type system

### In Progress

- 🔄 Runtime validation functions
- 🔄 Protocol correctness proofs
- 🔄 Concurrency safety verification

### Future Work

- ⏳ Formal verification with Lean 4
- ⏳ Automated property testing with QuickCheck
- ⏳ Fuzzing integration for safety properties

## Usage

These specifications serve multiple purposes:

1. **Development Reference** - Guide for implementing kernel modules
2. **Verification Target** - Properties to verify during testing
3. **Documentation** - Formal documentation of invariants
4. **Code Review** - Checklist for reviewing implementations

## Contributing

When adding new kernel types or modules:

1. Write formal specification using Lean notation
2. Document all invariants and safety properties
3. Map specification to Rust implementation
4. Add verification tests for key properties
5. Update this README with new specifications

## References

### Formal Methods

- [Lean 4 Documentation](https://leanprover.github.io/lean4/doc/)
- [The Lean 4 Theorem Prover](https://leanprover.github.io/)
- [Software Foundations](https://softwarefoundations.cis.upenn.edu/)

### Linux Kernel

- [Linux Kernel Documentation](https://www.kernel.org/doc/html/latest/)
- [Linux Networking Stack](https://wiki.linuxfoundation.org/networking/start)
- [Netfilter Documentation](https://www.netfilter.org/documentation/)

### Rust FFI

- [The Rustonomicon - FFI](https://doc.rust-lang.org/nomicon/ffi.html)
- [Rust Reference - Type Layout](https://doc.rust-lang.org/reference/type-layout.html)
- [repr(C) Specification](https://doc.rust-lang.org/reference/type-layout.html#the-c-representation)

---

**Maintained by:** Xavier Callens  
**Project:** rust-linux-mini-kernel  
**Repository:** https://github.com/xaviercallens/rust-linux-mini-kernel  
**License:** GPL-2.0 (matching Linux kernel)
