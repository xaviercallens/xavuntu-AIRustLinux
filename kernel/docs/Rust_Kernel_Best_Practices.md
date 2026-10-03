# Rust Kernel Best Practices (110/100 Elite Standard)

## 1. Zero-Cost Abstractions & Safe Wrappers
- **Opaque C Types**: For C structs that Rust should only hold pointers to, define them using `#[repr(C)]` with a zero-sized array and `PhantomData` to enforce strict type checking and variance at compile-time without adding overhead.
  ```rust
  #[repr(C)]
  pub struct OpaqueDevice {
      _p: [u8; 0],
      _marker: core::marker::PhantomData<(*mut u8, core::marker::PhantomPinned)>,
  }
  ```
- **The Newtype Pattern**: NEVER expose raw `*mut T` pointers. Wrap them in a newtype struct, keeping the inner pointer private, and expose only safe methods. 
- **RAII and `Drop`**: Implement the `Drop` trait on your safe wrappers to automate C cleanup functions (e.g., calling `kfree()` or `dev_put()`), ensuring memory safety and preventing leaks without manual lifecycle management.

## 2. Memory Allocation and OOM Handling
- **No Panics Allowed**: The kernel cannot panic upon memory exhaustion, as it takes down the entire system. All allocations must be **fallible**.
- **Result vs Panic**: Return `Result<T, AllocError>` instead of panicking. If an allocation fails, gracefully propagate the `-ENOMEM` code back up the call stack to userspace.
- **Strict Lifetimes**: Bind kernel objects (like sockets or devices) to Rust's lifetime (`'a`) system. This proves at compile time that no kernel object outlives the structure that owns it, eliminating Use-After-Free vulnerabilities natively.

## 3. Advanced Tooling & Static Analysis
- **Granular `clippy.toml`**: Go beyond standard linting by tuning `clippy.toml` for kernel idiosyncrasies (e.g., custom `cognitive-complexity-threshold`).
- **Zero-Tolerance CI**: Enforce `#![deny(clippy::all)]` and `#![warn(clippy::pedantic)]` in CI pipelines. Warnings must be treated as breaking errors.
- **Klint Integration**: Utilize advanced, kernel-specific static analysis tools like `Klint` to prove that functions do not sleep while holding atomic spinlocks (a fatal kernel error invisible to standard Rust tooling).

## 4. FFI (Foreign Function Interface) Invariants
- **`core::ptr::addr_of_mut!`**: Always use `addr_of_mut!` for `static mut` and unaligned field accesses. Creating a mutable reference (`&mut`) to an unaligned pointer is Undefined Behavior in Rust.
- **Unsafe Boundaries**: Keep `unsafe` blocks exclusively for the direct C-function invocation. Never perform complex business logic inside an `unsafe` block. Document every block with a specific safety invariant (e.g., `// SAFETY: The C API guarantees the pointer is valid and properly aligned here.`).

## 5. Real-World Inspiration
- Apply these paradigms modeling real-world successes, such as Asahi Linux's GPU driver abstractions (wrapping memory management and DRM schedulers safely) and Google Android's Rust rewrite of the Binder IPC subsystem.
