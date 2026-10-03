# LICENSE FAQ: Licensing Interaction and Compliance

This FAQ clarifies the licensing relationship, distribution constraints, and legal boundaries for the **Rust Linux Minimum Viable Kernel (MVK)**. 

---

## 1. Context & Motivation

### Q1: Why is MVK licensed under MIT (with Citation & Attribution) while the original Linux Kernel is GPL-2.0-only?
**A:** The Rust code in MVK represents a clean-room reimplementation, semantic translation, and architectural modeling of core Linux networking and kernel subsystems in Rust. 
* The **MIT License** governs the *expressive Rust source code* created for this project, allowing academic researchers, developers, and downstream integrators the maximum flexibility to study, modify, and reuse the Rust translations.
* The **Citation & Attribution requirements** are included to protect academic integrity, ensuring that Xavier Callens receives proper credit for these complex translations and proofs when referenced in research publications, papers, or downstream derivative works.

### Q2: Does MVK contain actual C source code from the Linux Kernel?
**A:** **No.** MVK does not distribute or copy original C source code from the Linux kernel. It interacts with the Linux kernel through FFI (Foreign Function Interface) headers and implements translated Rust equivalents of core subsystems. However, because the translations directly model the structure, logic, and algorithms of the Linux kernel (such as CFS scheduling, Netfilter rules, and IPv4/IPv6 routing), MVK's modules are legally and architecturally considered **derivative works** of the original Linux kernel under copyright law when integrated.

---

## 2. Compilation, Linking, and Copyleft Interaction

### Q3: What happens when I compile MVK and link it into a running Linux kernel?
**A:** When compiled as built-in kernel subsystems or Loadable Kernel Modules (LKMs) and linked with the Linux kernel, the resulting binary is a unified work. Under the copyleft terms of the **GNU General Public License, Version 2 (GPLv2)**:
1. The **entire collective work** must be distributed under the terms of the GPLv2.
2. The permissive rights granted by the MIT license are subsumed by the stronger copyleft requirements of the GPLv2 for the combined binary.
3. Therefore, downstream users distributing a compiled kernel or module containing MVK code **must** license and distribute the complete work under the GPLv2.

### Q4: Are MVK modules legally compliant with standard kernel symbol exports?
**A:** **Yes.** MVK modules adhere to standard kernel symbol rules:
* Many critical kernel APIs and networking internals are marked with `EXPORT_SYMBOL_GPL` in the standard Linux kernel.
* To link against these symbols, a module must declare its license as GPL-compatible (e.g., `MODULE_LICENSE("GPL")` or `MODULE_LICENSE("GPL v2")`).
* Distributing a compiled module linked against `EXPORT_SYMBOL_GPL` symbols under a non-GPL-compatible license would violate the Linux kernel's copyright and fail loading due to safety checks.

---

## 3. Permissive vs. Copyleft Dual-Licensing Boundaries

### Q5: How are the different directories in MVK licensed?
To resolve the legal gray area, MVK uses a dual-licensing boundary:
1. **The Permissive ABI Tier (`crates/kernel_types`)**:
   * Contains opaque mock structures, FFI layout definitions, and standard clean-room type mappings.
   * Licensed under the **MIT License**. This allows developers to safely import types, build custom testing frameworks, or link user-space tools without triggering copyleft requirements.
2. **The Subsystem Tier (`crates/net`, `crates/fs`, `crates/sched_cfs`, etc.)**:
   * Implements functional kernel logic directly translated from, and tightly coupled with, Linux kernel algorithms.
   * When distributed as part of a functioning kernel module, these subsystems are governed by **GPL-2.0-only** copyleft terms to ensure total compliance with standard upstream kernel distribution guidelines.

```
┌────────────────────────────────────────────────────────┐
│             Rust Linux MVK Codebase                    │
├──────────────────────────┬─────────────────────────────┤
│   kernel_types (ABI)     │   Subsystems (FS/Net/Sched) │
│   [MIT or GPL-2.0-only]  │      [GPL-2.0-only Only]    │
└──────────────────────────┴─────────────────────────────┘
```

---

## 4. Downstream Rights and Academic Citation

### Q6: Can I use MVK code in a proprietary, closed-source kernel module?
**A:** **No.** While the Rust source code itself is under the MIT license, any functional module that links with the Linux kernel's internal structures or symbols (especially `EXPORT_SYMBOL_GPL` symbols) becomes a derivative work of the GPLv2 kernel. Thus, you cannot distribute a closed-source, proprietary kernel module that incorporates MVK functional code. 

### Q7: How do I satisfy both the MIT Citation requirement and the GPLv2 copyleft terms?
**A:** They are fully compatible:
* **Academic/Research context**: When writing a paper, thesis, or technical report referencing this work, cite the repository using the BibTeX or CFF entry in `CITATION.cff`.
* **Software distribution context**: Keep the `LICENSE` file (containing the MIT license and citation request) intact in your source tree. Under the GPLv2, you must distribute the source code of your changes. Retaining the original copyright notice and MIT text complies with both the MIT license's preservation requirement and the GPLv2's attribution rules.

### Q8: Does the academic citation requirement constitute a "further restriction" under GPLv2 Section 6?
**A:** **No.** The citation requirement is a standard request for academic attribution and integrity, similar to standard copyright notices. It does not limit the rights to copy, modify, or distribute the software under the GPLv2. To ensure absolute compliance, the source code remains freely redistributable, and downstream distributors are simply requested to maintain the original author's attribution and citations in accordance with academic standards.

---

*Disclaimer: This document is for informational purposes and does not constitute formal legal advice. For commercial applications, please consult with legal counsel specializing in open-source licensing.*
