# Contributing to rust-linux-mini-kernel

First off, thank you for considering contributing to the `rust-linux-mini-kernel` project! It's people like you that make the open-source community such a fantastic place to learn, inspire, and create.

This project is an ambitious initiative to translate 121 Linux kernel networking subsystems from C to Rust. Due to the highly experimental nature of this codebase, your contributions to testing, error fixing, and kernel validation are incredibly valuable.

## Table of Contents
1. [Where to Start](#where-to-start)
2. [How to Contribute](#how-to-contribute)
3. [Development Workflow](#development-workflow)
4. [Coding Guidelines](#coding-guidelines)
5. [Reporting Bugs](#reporting-bugs)
6. [Community & Discussions](#community--discussions)

---

## Where to Start
If you're new to the project, the best place to start is by looking at the compilation issues. Currently, we use Azure Codex (SocrateAgor) to do bulk translations, but manual intervention is often required.

Look for issues tagged with:
- `good first issue`: Simple compilation fixes, syntax adjustments, and FFI annotations.
- `help wanted`: Complex macro conversions or type translations.
- `documentation`: Adding per-module READMEs or inline documentation.

## How to Contribute

### 1. Compilation Error Fixing
Since much of the code is AI-translated, many modules fail to compile due to missing C-types, unsafe macro expansions, or no_std violations.
- **Goal:** Get the remaining failing modules to pass `cargo check`.
- **How:** Review the `cargo_errors.txt` or run `cargo check --workspace` to find the next error in the queue. Apply manual fixes, ensuring FFI compatibility (`#[repr(C)]`).

### 2. Validation and Kernel Integration
We need help verifying that these modules actually work when loaded into a Linux kernel.
- **Goal:** Test compiled `.ko` equivalents or static libraries inside a custom QEMU kernel build.
- **How:** See the `KERNEL_INTEGRATION_GUIDE.md` (if available) or help us write it by documenting your integration process.

### 3. Writing Tests
Rigorous testing is required for kernel-level code.
- **Goal:** Write unit tests and property-based tests (using `proptest`) for the FFI structures and logical conversions.

## Development Workflow
1. **Fork the repository** on GitHub.
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/rust-linux-mini-kernel.git
   ```
3. **Create a new branch** for your feature or bug fix:
   ```bash
   git checkout -b feature/my-awesome-fix
   ```
4. **Make your changes** and run checks:
   ```bash
   cargo check --workspace
   cargo clippy --workspace -- -D warnings
   cargo fmt
   ```
5. **Commit your changes** with a clear and descriptive commit message.
6. **Push to your fork** and submit a Pull Request!

## Coding Guidelines
- **FFI Compliance:** All structs interfacing with C must be marked with `#[repr(C)]`.
- **`no_std`:** Kernel modules do not have access to the standard library. Ensure your modules are tagged with `#![no_std]` and do not rely on `std::`.
- **Unsafe Code:** Any use of `unsafe` must be clearly documented with a `// SAFETY: ...` comment explaining why it is sound.
- **Formatting:** Code must be formatted with `cargo fmt`.

## Reporting Bugs
If you find a bug (in the generated Rust code, the build pipeline, or anywhere else), please open an issue using the provided templates. Include as much context as possible, such as:
- The module name
- The exact compiler error
- Your rustc version

## Community & Discussions
We highly encourage collaboration!
- **GitHub Discussions:** We use GitHub Discussions for Q&A, brainstorming, and architectural decisions. Please drop by and introduce yourself!
- **Issues:** Use the Issue tracker for actionable bugs and planned tasks.

By contributing, you agree that your contributions will be licensed under the project's GPL-2.0 License.
