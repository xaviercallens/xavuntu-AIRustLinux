# Minimum Viable Kernel (MVK) - Collaboration & Reproducibility Proposal

**Call for Collaboration: Hardening the Rust-Based Linux Microkernel**

The Minimum Viable Kernel (MVK) project has successfully demonstrated that it is possible to mathematically eliminate spatial and temporal memory vulnerabilities in a bare-metal architecture using Rust and Lean 4 formal verification. 

As we prepare for the **v9.1 Security Hardening Release**, we are officially opening the repository for community collaboration, peer review, and academic reproduction.

---

## 1. How to Reproduce the MVK Empirical Results

We strongly encourage independent security researchers and systems engineers to reproduce our benchmarks and formal verification proofs. All infrastructure relies on open-source toolchains.

### Prerequisites
*   **Rust Toolchain:** `nightly-2026-05-15` (required for `no_std` and `Miri`).
*   **Lean 4:** v4.29.1 (for formal verification proofs).
*   **Hardware:** An x86_64 virtualization environment (QEMU) or a GCP `c2-standard-4` bare-metal instance (for cycle-accurate performance benchmarks).

### Reproduction Steps

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git
   cd rust-linux-mini-kernel
   ```

2. **Verify the Lean 4 Mathematical Proofs:**
   This step guarantees the algebraic soundness of the kernel's hardware initialization phase.
   ```bash
   cd specs/lean4
   lake build
   ```
   *Expected Result:* A successful compilation (exit code 0) proving that no memory-unsafe transitions exist in the modeled state machine.

3. **Run the Dynamic Undefined Behavior (UB) Interpreter:**
   Validate that the `unsafe` boundaries do not violate strict aliasing or pointer provenance rules.
   ```bash
   cargo miri test
   ```

4. **Execute the Bare-Metal Kernel in QEMU:**
   ```bash
   cargo run --release
   ```
   *Expected Result:* The kernel will boot, initialize the `printk` serial console, set up the GDT/IDT, and enter a safe halt loop.

---

## 2. Proposed Improvements & Next Steps (v9.1)

The foundation built on Rust's Ownership Model provides absolute temporal and spatial safety. However, the architectural design must evolve to mitigate logical flaws and hardware-level exploitation. We propose the following advancements for the v9.1 release:

### A. Hardware-Boundary Fuzzing (`libFuzzer` / `syzkaller`)
While the safe Rust subset is memory-safe, the hardware interaction boundaries (e.g., `asm!` blocks, Memory-Mapped I/O) require `unsafe` blocks. 
*   **Proposal:** We need contributors to write rigorous `cargo-fuzz` targets to stress-test the entry and exit points of these `unsafe` abstractions, blindly bombarding them with malformed edge cases to ensure they handle invalid states gracefully.

### B. Microkernel Privilege De-escalation
Currently, the entire MVK operates in Ring-0 (highest privilege).
*   **Proposal:** Refactor device drivers (such as the network stack and serial console) to execute in Ring-3 user space. We invite OS architects to help design a high-throughput, zero-copy Inter-Process Communication (IPC) mechanism utilizing our new `RcuPointer<T>` primitive to pass messages between Ring-3 and Ring-0 safely.

### C. Advanced Exploit Mitigations
*   **Proposal:** Implement Kernel Address Space Layout Randomization (KASLR) and Kernel Control-Flow Integrity (kCFI). We are seeking LLVM compiler experts to help configure the `target.json` and bootloader stubs to dynamically randomize the kernel's physical memory mapping at boot.

### D. Extending Lean 4 Formal Verification
*   **Proposal:** The current proofs cover Phase 1 (Serial initialization and Interrupt disabling). We need mathematical logicians to help write Lean 4 algebraic models for the Virtual File System (VFS) and the `io_uring` asynchronous packet ingress pathways.

---

## 3. How to Contribute

We operate under a standard open-source workflow:
1. Review the open issues labeled `good first issue` or `security`.
2. Fork the repository and create a feature branch.
3. Ensure your branch passes the GitHub Actions CI/CD pipeline, which now strictly enforces `cargo-audit` (supply chain security) and `Miri` (UB detection).
4. Submit a Pull Request with a detailed explanation of your security patch or architectural enhancement.

*We look forward to collaborating with you to build the most secure operating system in the world.*
