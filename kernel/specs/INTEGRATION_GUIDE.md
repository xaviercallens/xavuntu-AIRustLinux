# Formal Specification Integration Guide

## Overview

This guide explains how the Lean 4 formal specifications integrate with the Rust implementation of MVK v8.4.0.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Development Workflow                   │
└─────────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Lean 4 Specs │    │ Rust Code    │    │ Unit Tests   │
│              │    │              │    │              │
│ - Contracts  │◄───┤ - impl       │◄───┤ - validation │
│ - Properties │    │ - unsafe     │    │ - coverage   │
│ - Proofs     │    │ - FFI        │    │ - property   │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │   CI/CD         │
                  │   Verification  │
                  └─────────────────┘
```

## Module Mapping

### 1. Printk Module

**Rust Implementation:** `crates/printk/src/lib.rs`  
**Lean Specification:** `specs/lean4/phase1/Printk.lean`

**Mapping:**

| Rust Function | Lean Specification | Contract |
|---------------|-------------------|----------|
| `printk_init()` | `printk_init_spec` | Returns 0, initializes serial |
| `printk_str(ptr, len)` | `printk_str_spec bytes len state` | Handles null, zero-length safely |
| `serial_write_byte(byte)` | `serial_write_byte_spec byte state` | Polls TX ready, writes byte |

**Key Properties:**

- ✅ `null_pointer_no_modification` - Proven in Lean, tested in Rust
- ✅ `zero_length_no_modification` - Proven in Lean, tested in Rust
- ⏳ `printk_preserves_content` - Axiom in Lean, needs I/O capture test
- ⏳ `buffer_size_safe` - Axiom in Lean, needs boundary test

**Integration Points:**

```rust
// Rust: crates/printk/src/lib.rs:28
pub unsafe extern "C" fn printk_str(s: *const u8, len: usize) {
    if !s.is_null() && len > 0 {  // ✓ Matches Lean precondition
        // ... implementation
    }
}
```

```lean
-- Lean: specs/lean4/phase1/Printk.lean:83
def printk_str_spec (bytes_opt : Option (List UInt8)) (len : Nat)
  (state : SerialState) : IO SerialState := do
  match bytes_opt with
  | none => return state  -- ✓ Matches Rust null check
  | some bytes =>
    if len = 0 then return state  -- ✓ Matches Rust zero check
    -- ...
```

### 2. InitMain Module

**Rust Implementation:** `crates/init_main/src/lib.rs`  
**Lean Specification:** `specs/lean4/phase1/InitMain.lean`

**Mapping:**

| Rust Function | Lean Specification | Contract |
|---------------|-------------------|----------|
| `start_kernel()` | `start_kernel_spec` | Never returns, halts |
| Boot sequence | `boot_phase_serial`, `boot_phase_arch`, `boot_phase_halt` | State machine |

**Key Properties:**

- ⏳ `boot_success_implies_halted` - Success reaches Halted state
- ⏳ `boot_state_progression` - Never skips states
- ⏳ `no_panic_before_arch` - No early termination

**Integration Points:**

```rust
// Rust: crates/init_main/src/lib.rs:29
pub unsafe extern "C" fn start_kernel() -> ! {
    printk_init();  // ✓ Phase 1: Serial
    // ...
    arch_setup_init();  // ✓ Phase 2: Architecture
    // ...
    loop { /* halt */ }  // ✓ Phase 3: Halted
}
```

```lean
-- Lean: specs/lean4/phase1/InitMain.lean:67
def start_kernel_spec (initial : KernelState) : IO (KernelState × BootResult) := do
  let (state1, result1) ← boot_phase_serial initial  -- ✓ Phase 1
  -- ...
  let (state2, result2) ← boot_phase_arch state1     -- ✓ Phase 2
  -- ...
  let state3 ← boot_phase_halt state2                -- ✓ Phase 3
```

### 3. ArchSetup Module

**Rust Implementation:** `crates/arch_setup/src/lib.rs`  
**Lean Specification:** `specs/lean4/phase1/ArchSetup.lean`

**Mapping:**

| Rust Function | Lean Specification | Contract |
|---------------|-------------------|----------|
| `arch_setup_init()` | `arch_setup_init_spec` | Disables interrupts, returns 0 |
| `asm!("cli")` | `x86_cli` | CPU instruction (axiom) |

**Key Properties:**

- ⏳ `interrupts_disabled_after_init` - Safety critical
- ⏳ `init_idempotent` - Multiple calls safe
- ⏳ `init_always_succeeds` - No failure in Phase 1

**Integration Points:**

```rust
// Rust: crates/arch_setup/src/lib.rs:17
pub unsafe extern "C" fn arch_setup_init() -> c_int {
    core::arch::asm!("cli");  // ✓ Matches x86_cli axiom
    0  // ✓ Always succeeds in Phase 1
}
```

```lean
-- Lean: specs/lean4/phase1/ArchSetup.lean:22
def arch_setup_init_spec : IO ArchState := do
  x86_cli  -- ✓ Matches Rust CLI instruction
  return { interrupts_disabled := true, success := true, ... }  -- ✓ Returns success
```

## Contract Verification Workflow

### Step 1: Write Specification

```lean
-- Define contract
structure FunctionContract where
  requires : List Precondition
  ensures : List Postcondition
  invariants : List Invariant
```

### Step 2: Implement in Rust

```rust
/// # Safety
///
/// Preconditions (from Lean spec):
/// - ptr must be valid or null
/// - len must match buffer size
pub unsafe extern "C" fn function(ptr: *const u8, len: usize) {
    // Implementation matching spec
}
```

### Step 3: Generate Tests

```bash
./specs/scripts/generate_tests_from_specs.py
```

Creates:
- Precondition validation tests
- Postcondition verification tests
- Invariant preservation tests
- Property-based tests from theorems

### Step 4: Prove Properties

```lean
theorem my_property : ... := by
  intro h
  simp
  -- ... proof steps
```

### Step 5: Validate in CI

```yaml
- name: Verify Specifications
  run: cd specs && ./scripts/verify_specs.sh

- name: Run Tests
  run: cargo test --package module_name
```

## Testing Strategy

### 1. Unit Tests (Rust)

**Location:** `crates/*/src/lib.rs` (in `#[cfg(test)]` modules)

**Purpose:**
- Test individual functions
- Mock external dependencies
- Validate basic correctness

**Example:**
```rust
#[test]
fn test_printk_str_null_pointer() {
    unsafe {
        printk_str(core::ptr::null(), 100);
    }
    // Should not crash (validated by spec)
}
```

### 2. Property Tests (Generated)

**Location:** `tests/generated/*_spec_tests.rs`

**Purpose:**
- Validate axioms at runtime
- Test proven theorems for implementation match
- Boundary condition testing

**Example:**
```rust
#[test]
fn test_null_pointer_safety_proven() {
    // This property is formally proven in Lean 4
    unsafe {
        let initial_state = get_printk_state();
        printk_str(core::ptr::null(), 100);
        let final_state = get_printk_state();
        assert_eq!(initial_state, final_state,
            "Null pointer should not modify state (proven)");
    }
}
```

### 3. Integration Tests

**Location:** `tests/*.rs`

**Purpose:**
- Test module interactions
- Validate state machine progression
- End-to-end boot sequence

**Example:**
```rust
#[test]
fn test_boot_sequence_order() {
    // Validates: boot_state_progression theorem
    let states = capture_boot_states();
    assert!(states == [Uninitialized, SerialReady, ArchReady, Halted]);
}
```

## Continuous Integration

### Verification Pipeline

```yaml
verify-specifications:
  - Install Lean 4
  - Build specifications
  - Type check
  - Run verification script
  - Check for proof regressions

validate-implementation:
  - Setup Rust toolchain
  - Run unit tests
  - Check function signatures
  - Validate against specs

track-proof-progress:
  - Calculate metrics
  - Generate badges
  - Create progress reports
```

### Failure Conditions

1. **Specification doesn't type check** → Fix Lean syntax/types
2. **Proof regression** (more `sorry`) → Complete outstanding proofs
3. **Function signature mismatch** → Update implementation or spec
4. **Test failure** → Fix implementation or spec

## Best Practices

### 1. Specification-First Development

```
1. Write Lean specification with contracts
2. State key properties as theorems
3. Implement Rust code matching spec
4. Generate and run tests
5. Complete proofs incrementally
```

### 2. Keep Specs and Code in Sync

- Update spec when changing implementation
- Regenerate tests after spec changes
- Run verification in CI on every commit

### 3. Document Assumptions

```lean
-- Hardware assumption: Serial port exists at 0x3F8
axiom serial_port_exists : ...
```

```rust
/// # Safety
///
/// Assumes: Serial port hardware present at 0x3F8
```

### 4. Incremental Verification

- Start with simple properties (reflexivity, equality)
- Build up to complex invariants
- Use `sorry` as placeholder, track in PROOF_OBLIGATIONS.md

### 5. Test What You Can't Prove

Some properties are difficult to prove formally but can be tested:

- **Termination** - Use timeouts in tests
- **I/O behavior** - Mock and capture
- **Performance** - Benchmarks with bounds

## Debugging Integration Issues

### Specification Doesn't Build

```bash
cd specs/lean4
lake build --verbose
```

Check:
- Syntax errors in Lean files
- Missing imports
- Type mismatches

### Tests Fail Despite Proven Theorem

**Cause:** Implementation doesn't match specification

**Fix:**
1. Compare Rust function to Lean spec
2. Check preconditions are enforced
3. Verify postconditions are established
4. Look for off-by-one errors, null handling

### CI Verification Fails

```bash
# Run locally first
cd specs
./scripts/verify_specs.sh --verbose
```

Common issues:
- Lean not installed in CI
- File paths incorrect
- Missing dependencies

## Future Enhancements

### Phase 2: Advanced Integration

1. **Extraction** - Generate Rust from Lean (research)
2. **Refinement** - Prove implementation refines specification
3. **Verification Conditions** - Auto-generate from contracts
4. **Property-Based Testing** - QuickCheck from Lean properties

### Phase 3: Full Verification

1. **Memory Safety** - Prove no buffer overflows, use-after-free
2. **Concurrency** - Verify synchronization, deadlock freedom
3. **Security** - Prove information flow properties
4. **Performance** - Verify time/space complexity bounds

## Resources

### Documentation

- [Lean 4 Manual](https://leanprover.github.io/lean4/doc/)
- [Theorem Proving in Lean 4](https://leanprover.github.io/theorem_proving_in_lean4/)
- [MVK Specifications](SPECIFICATIONS.md)
- [Proof Obligations](PROOF_OBLIGATIONS.md)

### Tools

- **lake** - Lean 4 build system
- **VS Code** - With Lean 4 extension for interactive proving
- **cargo test** - Rust testing framework

### Examples

- **seL4** - Fully verified microkernel (Isabelle/HOL)
- **CertiKOS** - Certified OS kernel (Coq)
- **Verve OS** - Verified OS (Boogie/Dafny)

## Support

For issues with specifications or integration:

1. Check [PROOF_OBLIGATIONS.md](PROOF_OBLIGATIONS.md) for status
2. Review [SPECIFICATIONS.md](SPECIFICATIONS.md) for details
3. Run verification locally: `./specs/scripts/verify_specs.sh`
4. Open issue with CI logs and error messages

---

**Last Updated:** 2026-05-19  
**Version:** MVK v8.4.0  
**Specification Phase:** 1 (Boot modules complete)
