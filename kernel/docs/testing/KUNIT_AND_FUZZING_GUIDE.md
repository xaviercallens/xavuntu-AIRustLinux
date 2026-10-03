# Developer's Guide to KUnit & Network Stack Fuzzing in Rust MVK

This guide provides instructions on how to run, write, and expand the runtime validation suite in the **Rust Linux Minimum Viable Kernel (MVK)**.

---

## 1. Unit & Integration Testing via Mock KUnit Harness

MVK integrates a custom `no_std`-compatible KUnit mock testing framework. This allows unit tests to run in two tiers:
1. **Host-Side (User-Space) Testing**: Runs on standard macOS/Linux hosts via `cargo test` using POSIX mock bindings.
2. **Kernel-Space Testing**: Compiles directly into standard kernel loadable modules, exporting tests into custom link sections (`.kunit_test_suites`) read by the Linux kernel's KUnit runner.

### How to Write a KUnit Test Suite

Test suites are registered using the `kunit_unsafe_test_suite!` macro defined in `kernel_types`.

```rust
use kernel_types::*;

// 1. Define individual test case functions
fn test_case_success(_test: *mut kunit) -> Result<(), &'static str> {
    // Assertions and logic
    Ok(())
}

fn test_case_failure(_test: *mut kunit) -> Result<(), &'static str> {
    Err("Condition did not hold!")
}

// 2. Instantiate the suite
kunit_unsafe_test_suite!(
    my_subsystem_suite,
    None, // init function pointer (Option)
    None, // exit function pointer (Option)
    [
        test_case_1 => test_case_success,
        test_case_2 => test_case_failure,
    ]
);
```

### Running Host-Side Integration Tests

Due to specific macOS sandboxing/AMFI rules on APFS external volumes, you **must** redirect the build target directory to the host's internal SSD when testing on Apple Silicon:

```bash
cargo test -p kernel_types --test integration_tests --target-dir /Users/xcallens/.gemini/antigravity/scratch/target
```

---

## 2. Network Stack Fuzzing via `cargo-fuzz` & `libFuzzer`

To discover edge cases, parser errors, out-of-bounds reads, or potential memory corruption in translated networking layers, MVK has a dedicated fuzzing package.

### Prerequisites

You need standard nightly Rust and the cargo-fuzz extension:
```bash
rustup toolchain install nightly
cargo install cargo-fuzz
```

### Fuzzing Architecture

The fuzzer is located under [fuzz/](file:///Volumes/MacCleanerStorage/xdev/xavux/rust-linux-mini-kernel/fuzz/) as an independent workspace. It targeting the core networking struct definitions and mock parser:
- Fuzzes `iphdr` IP version and IHL packed bitfield decoding.
- Fuzzes `ipv6hdr` address parsing and payload bounds calculation.
- Feeds randomized inputs to simulated `sk_buff` packet buffers.

### Running the Fuzzer

To run the packet parser fuzzer locally:
```bash
cd fuzz
cargo +nightly fuzz run fuzz_packet
```

To verify that the fuzzer compiles cleanly without starting execution:
```bash
cargo check --manifest-path fuzz/Cargo.toml --target-dir /Users/xcallens/.gemini/antigravity/scratch/target
```
