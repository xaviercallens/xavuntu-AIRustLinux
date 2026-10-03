# Rule: Rust Kernel Development Standards (110/100 Elite Standard)

When reading, modifying, or creating Rust code in the **RunuX** kernel workspace, you must adhere strictly to these engineering standards:

## 1. Zero-Cost Abstractions & FFI Wrappers
- **Opaque C Types**: For C structs that Rust should only hold pointers to, declare them with `#[repr(C)]`, a zero-sized array `_p: [u8; 0]`, and `PhantomData` to enforce strict compiler variance:
  ```rust
  #[repr(C)]
  pub struct OpaqueDevice {
      _p: [u8; 0],
      _marker: core::marker::PhantomData<(*mut u8, core::marker::PhantomPinned)>,
  }
  ```
- **Newtype Wrapper Pattern**: Never pass around raw `*mut T` pointers in high-level kernel logic. Wrap them in safe Newtypes (`SafeSkb`, `SafeSock`, `SafePageFrame`, `SafeDmaQueue`) with private inner fields and safe public methods.
- **RAII and `Drop`**: Implement `Drop` on safe wrappers to automate C deallocators (`kfree()`, `dev_put()`, `free_page()`).

## 2. Kernel Memory Allocation & OOM Handling
- **No Panicking Allocations**: The kernel cannot panic on memory exhaustion. All memory allocations must be fallible.
- **Return `Result<T, AllocError>`**: Propagate Linux error codes (e.g. `-ENOMEM`, `-EINVAL`, `-EBUSY`) up the call stack.
- **Strict Lifetimes**: Bind kernel objects to explicit lifetimes (`'a`) ensuring that child resources (e.g. socket filters, packet buffers) cannot outlive their owning parent structures.

## 3. Strict `#![no_std]` and ABI Compatibility
- **Header Directives**: Every crate must declare `#![no_std]`, `#![deny(clippy::all)]`, and `#![warn(clippy::pedantic)]`.
- **Bitfield Packing**: Rust does not natively support C bitfields. Pack bitfield structs manually into fixed-width integers (e.g., `u8` or `u16`) matching GCC's ABI layout, and provide inline zero-cost accessors:
  ```rust
  #[repr(C)]
  pub struct iphdr {
      pub version_ihl: u8, // 4 bits version + 4 bits IHL
      pub tos: u8,
      // ...
  }
  impl iphdr {
      #[inline(always)]
      pub fn version(&self) -> u8 { self.version_ihl >> 4 }
      #[inline(always)]
      pub fn ihl(&self) -> u8 { self.version_ihl & 0x0f }
  }
  ```
- **Unaligned Memory Access**: Use `core::ptr::addr_of_mut!` when accessing `static mut` or unaligned struct fields. Creating a mutable reference (`&mut`) to an unaligned pointer is Undefined Behavior in Rust.

## 4. Cache & Build Hygiene
- **Isolated Target Directory**: Avoid build cache contention and disk exhaustion by setting `CARGO_TARGET_DIR` to a dedicated scratch or temporary path when running checks.
- **Zero Warnings Tolerance**: Any warning produced during `cargo check` or `cargo clippy` is considered a build failure.
