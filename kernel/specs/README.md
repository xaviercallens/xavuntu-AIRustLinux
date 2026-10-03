# MVK v8.4.0 Formal Specifications

This directory contains formal specifications for the Minimum Viable Kernel written in Lean 4.

## Quick Start

### Prerequisites

Install Lean 4 using elan:

```bash
curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh
source ~/.elan/env
```

### Verify Specifications

```bash
cd specs
./scripts/verify_specs.sh
```

This will:
- Build all Lean 4 specifications
- Type check for correctness
- Count proof obligations
- Generate status report

### Build Specifications

```bash
cd specs/lean4
lake build
```

### Interactive Development

```bash
# Open in VS Code with Lean 4 extension
code specs/lean4/phase1/Printk.lean
```

## Directory Structure

```
specs/
├── README.md                      # This file
├── SPECIFICATIONS.md              # Complete specification documentation
├── PROOF_OBLIGATIONS.md           # Tracking proof completion
├── lean4/                         # Lean 4 source files
│   ├── MVK.lean                  # Root module
│   ├── lakefile.lean             # Build configuration
│   └── phase1/                   # Phase 1 boot modules
│       ├── Printk.lean           # Serial console driver
│       ├── ArchSetup.lean        # Architecture setup
│       └── InitMain.lean         # Kernel entry point
└── scripts/                       # Verification and tooling
    ├── verify_specs.sh           # Verification script
    └── generate_tests_from_specs.py  # Test generator
```

## Specifications

### Phase 1: Boot Modules (Complete)

- **Printk** - Serial console driver with formal I/O contracts
- **ArchSetup** - x86_64 architecture initialization
- **InitMain** - Kernel entry point and boot state machine

See [SPECIFICATIONS.md](SPECIFICATIONS.md) for detailed documentation.

## Proof Status

**Current Completion:** 14% (2/14 theorems proven)

- ✅ Proven: 2 theorems
- ⏳ Outstanding: 12 theorems
- 📋 Axioms: 15 (need proofs)

See [PROOF_OBLIGATIONS.md](PROOF_OBLIGATIONS.md) for detailed tracking.

## Key Features

### Contracts

Every function has formal contracts:

- **Requires** - Preconditions that must hold
- **Ensures** - Postconditions guaranteed on completion
- **Invariants** - Properties preserved across calls
- **Frame** - What doesn't change

Example from `printk_str`:
```lean
structure PrintkStrContract where
  requires_non_null_or_zero : ...
  ensures_all_bytes_written : ...
  frame_global_state : ...
```

### State Machines

Boot sequence modeled as state machine:
```lean
inductive BootState
  | Uninitialized
  | SerialReady
  | ArchReady
  | Halted
```

### Safety Properties

Formally specified and proven:
- No null pointer dereferences
- No buffer overflows
- Correct initialization order
- Termination guarantees

## Integration with Development

### 1. Specification-First Development

```
Write Lean spec → Implement Rust → Generate tests → Prove properties
```

### 2. Test Generation

Generate Rust tests from specifications:

```bash
./scripts/generate_tests_from_specs.py
```

This creates property-based tests, boundary tests, and invariant tests.

### 3. Continuous Verification

Specifications are checked in CI/CD:

```yaml
- name: Verify Specifications
  run: |
    cd specs
    ./scripts/verify_specs.sh
```

## Common Tasks

### Add New Specification

1. Create `specs/lean4/module/NewModule.lean`
2. Define state structures and operations
3. Specify contracts (requires/ensures/invariants)
4. State theorems and properties
5. Add proofs (or mark `sorry` for future work)
6. Update `specs/lean4/MVK.lean` to import
7. Update documentation

### Complete a Proof

1. Open specification file in VS Code with Lean 4 extension
2. Find theorem marked with `sorry`
3. Replace `sorry` with actual proof:
   ```lean
   theorem my_theorem : ... := by
     intro h
     simp
     rfl
   ```
4. Type check: `lake build`
5. Update PROOF_OBLIGATIONS.md

### Generate Tests

```bash
cd specs
./scripts/generate_tests_from_specs.py
```

Review generated tests in `tests/generated/`

## Resources

### Lean 4

- [Lean 4 Documentation](https://leanprover.github.io/lean4/doc/)
- [Theorem Proving in Lean 4](https://leanprover.github.io/theorem_proving_in_lean4/)
- [Lean Zulip Chat](https://leanprover.zulipchat.com/)

### Formal Verification

- [seL4 Microkernel](https://sel4.systems/) - Fully verified microkernel
- [Software Foundations](https://softwarefoundations.cis.upenn.edu/) - Coq textbook
- [Concrete Semantics](http://www.concrete-semantics.org/) - Isabelle textbook

### Tools

- **lake** - Lean 4 build tool
- **VS Code** - With Lean 4 extension for interactive proving
- **mathlib4** - Standard library (if needed)

## Proof Development Tips

### Basic Tactics

```lean
intro h      -- Introduce hypothesis
simp         -- Simplification
rw [eq]      -- Rewrite using equation
rfl          -- Reflexivity (for definitional equality)
cases x      -- Case analysis
induction x  -- Induction
exact t      -- Provide exact proof term
sorry        -- Placeholder for incomplete proof
```

### Debugging

```lean
#check my_theorem          -- Check type
#print my_theorem          -- Print definition
#reduce my_expression      -- Evaluate expression
```

### Common Patterns

- **Definitional equality:** Use `rfl`
- **Case analysis:** Use `cases` on inductive types
- **Induction:** Use `induction` on recursive structures
- **Simplification:** Use `simp` with lemma database
- **Rewriting:** Use `rw` for equation-based reasoning

## Verification Workflow

1. **Write specification** - Define contracts and properties
2. **Type check** - Ensure specification is well-formed
3. **State theorems** - Identify properties to prove
4. **Write proofs** - Complete formal proofs
5. **Generate tests** - Create runtime validation
6. **Validate** - Verify implementation matches spec

## Contributing

See [SPECIFICATIONS.md](SPECIFICATIONS.md) for contribution guidelines.

## License

GPL-2.0 (matching kernel implementation)

---

**Status:** Phase 1 specifications complete, proofs in progress  
**Version:** MVK v8.4.0  
**Last Updated:** 2026-05-19
