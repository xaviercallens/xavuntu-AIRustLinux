# GPLv2 Compliance & Interaction Guide for Rust MVK

This guide outlines the legal and architectural compliance model for the **Rust Linux Minimum Viable Kernel (MVK)**. Because MVK implements, refactors, and translates core Linux kernel subsystems, it is legally and technically a derivative work of the Linux kernel (licensed under standard `GPL-2.0-only` copyleft terms).

---

## 1. The Legal Reality of Derivative Kernel Works

The Linux kernel is licensed under the **GNU General Public License version 2 (GPLv2) only**, with a standard system call exception for user-space applications. However, code that runs inside kernel space as a loadable kernel module (LKM) or built-in subsystem:
- Must respect the copyleft nature of GPLv2.
- Cannot be distributed under proprietary or overly restrictive licenses (e.g., standard MIT with citation requirements that forbid standard redistribution).
- Interacts directly with symbols exported via `EXPORT_SYMBOL` or `EXPORT_SYMBOL_GPL`.

Therefore, the Rust Linux MVK repository has transitioned to standard **`GPL-2.0-only` copyleft licensing** to ensure seamless compliance with standard upstream kernel distribution guidelines.

---

## 2. Architectural Separation & Dual-Licensing Rules

For contributors wishing to maintain dual-licensed FFI wrappers under more permissive licenses (like `MIT` or `Apache-2.0`), the following boundaries must be strictly observed:

### Permissive User-Space Mock Tier
- Code located in pure FFI types with zero functional logic (e.g., mock structural declarations in `crates/kernel_types`) can be dual-licensed under standard `MIT OR GPL-2.0-only` if they contain only clean-room definitions of ABI layouts.
- Pure user-space test harnesses that do not call kernel-space FFI can remain permissively licensed.

### Copyleft Subsystem Tier (GPL-2.0-only Mandatory)
- Any subsystem that implements kernel-space functions (e.g., scheduler algorithms in `crates/sched_cfs`, netfilter logic in `crates/nf_nat_proto`, multicast snooping in `crates/mcast_snoop`) is tightly coupled to internal Linux structures and **must** remain licensed under the standard `GPL-2.0-only` terms.

```
┌────────────────────────────────────────────────────────┐
│             Rust Linux MVK Codebase                    │
├──────────────────────────┬─────────────────────────────┤
│   kernel_types (ABI)     │   Subsystems (FS/Net/Sched) │
│   [MIT or GPL-2.0-only]  │      [GPL-2.0-only Only]    │
└──────────────────────────┴─────────────────────────────┘
```

---

## 3. Kernel Symbol Linking Compliance

When compiling Rust MVK as a loadable kernel module, we must pay close attention to `EXPORT_SYMBOL_GPL` versus `EXPORT_SYMBOL`:
1. **GPL-Only Symbols**: Functions or macros representing core kernel internal state (e.g., namespaces, netfilter internals) are marked with `EXPORT_SYMBOL_GPL` in standard C headers. A module using these symbols **must** declare `MODULE_LICENSE("GPL")` or `MODULE_LICENSE("GPL v2")`. If it does not, the kernel loader will fail with symbol resolution errors (`SIGKILL` or symbol load denied).
2. **Rust FFI Bindings**: All FFI modules in Rust MVK are compiled with `#[no_mangle]` and `pub unsafe extern "C"` to export symbols compliant with the kernel's module linking standard.

---

## 4. Upstream Integration Checklist

Before attempting to upstream any Rust MVK subsystem to the official Linux kernel or deploying it in commercial environments:
- [x] Set `license = "GPL-2.0"` in all workspace member `Cargo.toml` manifests.
- [x] Include standard `SPDX-License-Identifier: GPL-2.0-only` header comments in all Rust source files.
- [x] Ensure that no proprietary or non-GPL-compatible dependencies are added to the workspace.
- [x] Verify that custom macro definitions do not circumvent the kernel's memory-safety guarantees or taint the kernel.
