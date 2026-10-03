# MVK v8.4.0 Formal Specifications

## Overview

This document describes the formal specifications for the Minimum Viable Kernel (MVK), written in Lean 4 for formal verification. These specifications enable:

- **Formal verification** of correctness properties
- **Contract-based design** with explicit pre/post conditions
- **Proof-driven development** with mechanized proofs
- **Safety guarantees** backed by mathematical proofs
- **Test generation** from specifications

## Specification Structure

### Directory Organization

```
specs/lean4/
├── MVK.lean                    # Root module
├── lakefile.lean              # Lean 4 build configuration
├── phase1/                    # Phase 1 boot modules
│   ├── Printk.lean           # Serial console driver
│   ├── ArchSetup.lean        # x86_64 architecture setup
│   └── InitMain.lean         # Kernel entry point
├── memory/                    # Memory management (future)
├── process/                   # Process management (future)
├── syscalls/                  # System calls (future)
└── filesystem/                # VFS and filesystems (future)
```

## Phase 1: Boot Modules

### 1. Printk (Serial Console Driver)

**File:** `specs/lean4/phase1/Printk.lean`

**Purpose:** Formally specify serial port initialization and output operations for kernel logging.

**Key Components:**

- **Hardware Constants:**
  - `SERIAL_PORT = 0x3F8` (COM1)
  - `TX_READY_BIT = 0x20` (transmitter ready flag)

- **State Representation:**
  ```lean
  structure SerialState where
    initialized : Bool
    tx_ready : Bool
    port : UInt16
  ```

- **Main Operations:**
  - `printk_init_spec` - Initialize 16550 UART (9600 baud, 8N1)
  - `serial_write_byte_spec` - Write single byte with polling
  - `printk_str_spec` - Write byte buffer to serial port

**Formal Properties:**

1. **Initialization Correctness**
   - Theorem: `printk_init_ensures_ready`
   - After initialization, serial port is configured correctly

2. **Output Preservation**
   - Axiom: `printk_preserves_content`
   - Output bytes match input bytes exactly

3. **Termination**
   - Axiom: `printk_terminates`
   - All operations complete in finite time

4. **Safety Properties**
   - `buffer_size_safe` - No buffer overflows (max 4096 bytes)
   - `null_pointer_no_modification` - Null pointers handled safely
   - `zero_length_no_modification` - Zero-length writes are no-ops

5. **Invariants:**
   - Initialization implies correct port configuration
   - TX ready implies initialized state
   - Null pointer causes no state changes
   - Zero length causes no state changes

**Contract:** `PrintkStrContract`
- **Requires:** Non-null pointer OR zero length, valid length, initialized serial port
- **Ensures:** All bytes written, state preserved for null/zero cases
- **Frame:** Port address never changes, initialization flag preserved

---

### 2. InitMain (Kernel Entry Point)

**File:** `specs/lean4/phase1/InitMain.lean`

**Purpose:** Specify the kernel boot sequence state machine and initialization order.

**Key Components:**

- **Boot State Machine:**
  ```lean
  inductive BootState
    | Uninitialized    -- Before any init
    | SerialReady      -- Serial console ready
    | ArchReady        -- Architecture setup complete
    | Halted           -- Final state (infinite loop)
  ```

- **Kernel State:**
  ```lean
  structure KernelState where
    boot_state : BootState
    serial : Printk.SerialState
    arch : ArchSetup.ArchState
    messages_printed : List String
  ```

- **Boot Phases:**
  - `boot_phase_serial` - Initialize serial console
  - `boot_phase_arch` - Initialize architecture
  - `boot_phase_halt` - Enter infinite loop
  - `start_kernel_spec` - Complete boot sequence

**Formal Properties:**

1. **Termination**
   - Axiom: `boot_terminates`
   - Boot sequence always reaches terminal state

2. **Correctness**
   - Theorem: `boot_success_implies_halted`
   - Successful boot ends in Halted state

3. **State Progression**
   - Theorem: `boot_state_progression`
   - Boot never skips states (Uninitialized → SerialReady → ArchReady → Halted)

4. **Message Output**
   - Theorem: `boot_prints_all_messages`
   - All expected messages are printed on success

5. **Safety Properties:**
   - `no_panic_before_arch` - No early termination before architecture init
   - `serial_stays_initialized` - Serial remains ready after setup
   - `init_order_correct` - Serial initialized before architecture

**Contract:** `StartKernelContract`
- **Requires:** Uninitialized state, valid hardware
- **Ensures:** Halted on success, messages printed, subsystems initialized
- **Invariants:** Monotonic progress, no state regression
- **Frame:** No external state modifications beyond hardware I/O

---

### 3. ArchSetup (x86_64 Architecture Setup)

**File:** `specs/lean4/phase1/ArchSetup.lean`

**Purpose:** Specify x86_64 architecture initialization, currently focused on interrupt control.

**Key Components:**

- **Architecture State:**
  ```lean
  structure ArchState where
    interrupts_disabled : Bool
    gdt_loaded : Bool         -- Future: GDT setup
    idt_loaded : Bool         -- Future: IDT setup
    paging_enabled : Bool     -- Future: Paging
    success : Bool
  ```

- **Main Operations:**
  - `arch_setup_init_spec` - Disable interrupts (Phase 1)
  - `x86_cli` - Clear interrupt flag (external)

**Formal Properties:**

1. **Safety**
   - Theorem: `interrupts_disabled_after_init`
   - Success implies interrupts are disabled

2. **Correctness**
   - Axiom: `init_always_succeeds`
   - Phase 1 initialization never fails

3. **Idempotence**
   - Theorem: `init_idempotent`
   - Multiple calls produce same result

4. **Determinism**
   - Axiom: `init_deterministic`
   - Same input always produces same output

5. **Future Compatibility:**
   - `phase1_compatible_with_future` - Current spec extends to future phases
   - `init_monotonic` - Each phase only adds, never removes initialization

**Contract:** `ArchSetupInitContract`
- **Requires:** x86_64 architecture, early boot environment
- **Ensures:** Interrupts disabled, success flag set, Phase 1 minimal (no GDT/IDT/paging yet)
- **Invariants:** Success implies disabled interrupts
- **Frame:** Only CPU interrupt flag modified

---

## Proof Obligations

### Summary Statistics

| Module      | Theorems | Proven | Outstanding | Completion |
|-------------|----------|--------|-------------|------------|
| printk      | 4        | 2      | 2           | 50%        |
| init_main   | 6        | 0      | 6           | 0%         |
| arch_setup  | 4        | 0      | 4           | 0%         |
| **Total**   | **14**   | **2**  | **12**      | **14%**    |

### Detailed Proof Obligations

#### Printk Module

**✅ Proven:**
1. `null_pointer_no_modification` - Null pointer safety
2. `zero_length_no_modification` - Zero length safety

**⏳ Outstanding:**
1. `printk_init_ensures_ready` - Initialization postcondition
2. `interrupts_disabled_after_init` - Safety property

**Axioms (Need Proofs):**
- `printk_preserves_content` - Output correctness
- `printk_terminates` - Termination guarantee
- `buffer_size_safe` - Buffer overflow prevention

#### InitMain Module

**⏳ Outstanding:**
1. `boot_success_implies_halted` - Correctness property
2. `boot_state_progression` - State machine property
3. `boot_prints_all_messages` - Output property
4. `serial_stays_initialized` - Invariant preservation
5. `no_panic_before_arch` - Safety property
6. `init_order_correct` - Initialization order

**Axioms (Need Proofs):**
- `boot_reaches_terminal_state` - Reachability
- `boot_terminates` - Termination

#### ArchSetup Module

**⏳ Outstanding:**
1. `interrupts_disabled_after_init` - Safety property
2. `init_idempotent` - Idempotence
3. `init_produces_valid_state` - Well-formedness
4. `phase1_establishes_safety` - Critical invariant

**Axioms (Need Proofs):**
- `init_always_succeeds` - Correctness
- `init_deterministic` - Determinism
- `init_terminates` - Termination

---

## Verification Workflow

### 1. Building Specifications

```bash
cd specs/lean4
lake build
```

### 2. Type Checking

```bash
lake env lean --version
lake env lean MVK
```

### 3. Interactive Proof Development

```bash
# Open in VS Code with Lean 4 extension
code specs/lean4/phase1/Printk.lean
```

### 4. Exporting Proof Obligations

```bash
lake env lean --export=proof_obligations.json MVK
```

---

## Integration with Development

### Contract-First Development

1. **Write specification** - Define contracts and properties in Lean
2. **Implement in Rust** - Write code matching the specification
3. **Generate tests** - Derive test cases from contracts
4. **Prove properties** - Complete formal proofs
5. **Validate** - Verify implementation matches specification

### Test Generation

Specifications can generate:
- **Property-based tests** - From axioms and theorems
- **Boundary condition tests** - From preconditions
- **Invariant tests** - From state invariants
- **Regression tests** - From proven properties

### Continuous Verification

CI/CD integration:
- Type check specifications on every commit
- Track proof completion percentage
- Generate proof obligation reports
- Validate implementation against specs

---

## Future Work

### Phase 2: Memory Management

Specifications to add:
- Page allocator (`page_alloc`)
- Slab allocator (`slab`)
- Virtual memory (`vmalloc`)
- Memory mapping (`mmap`)

### Phase 3: Process Management

Specifications to add:
- Process creation (`fork`)
- Scheduler (`sched_core`, `sched_fair`)
- Context switching
- Signal handling

### Phase 4: System Calls

Specifications to add:
- System call table and dispatch
- Core syscalls (read, write, open, close)
- Process syscalls (fork, exec, exit, wait)
- Memory syscalls (mmap, munmap, brk)

### Phase 5: Filesystem

Specifications to add:
- VFS layer (inode, dentry, file operations)
- ext4 filesystem
- Procfs and sysfs

---

## References

### Lean 4 Resources

- [Lean 4 Documentation](https://leanprover.github.io/lean4/doc/)
- [Theorem Proving in Lean 4](https://leanprover.github.io/theorem_proving_in_lean4/)
- [Lean 4 API Documentation](https://leanprover-community.github.io/mathlib4_docs/)

### Formal Methods

- Hoare Logic for contracts
- Temporal logic for state machines
- Separation logic for memory safety

### Related Projects

- [seL4 Microkernel](https://sel4.systems/) - Fully verified microkernel
- [CertiKOS](http://flint.cs.yale.edu/certikos/) - Certified concurrent OS kernel
- [Verve OS](https://www.microsoft.com/en-us/research/project/verve/) - Verified operating system

---

## Contributing

To add new specifications:

1. Create module file in appropriate directory
2. Define state structures and operations
3. Specify contracts (requires/ensures/invariants)
4. State theorems and properties
5. Add proofs (or mark as `sorry` for future work)
6. Update this documentation
7. Add to `MVK.lean` root module

---

## License

Specifications are licensed under GPL-2.0, matching the kernel implementation.

---

*Generated for MVK v8.4.0 - Phase 1 Boot Specifications*
*Last Updated: 2026-05-19*
