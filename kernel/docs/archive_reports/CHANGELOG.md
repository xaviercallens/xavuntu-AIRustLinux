# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [7.0.0-alpha] - 2025-01-19

### Added
- First alpha release of Rust Linux Mini Kernel
- **122 of 124 packages (98.4%)** successfully compile
- FFI-compatible Rust translations of Linux kernel networking components:
  - IPv6 core functionality (ip6_input, ip6_output, ip6_offload)
  - TCP/UDP networking (tcp_ipv6, udp, udpv6_offload)
  - Netfilter connection tracking (nf_conntrack_*)
  - IPsec/XFRM (xfrm6_*, esp6_*)
  - Routing and forwarding (fib6_*, route)
  - GRE and tunneling (ip6_gre, ip6_tunnel, ip6_vti)
  - IPv6 mobility (mip6)
  - Segment routing (seg6, seg6_*)
- Formal verification framework with symbolic execution support
- Comprehensive kernel type definitions (kernel_types crate)
- Example kernel implementation with hosted and bare-metal modes
- CI/CD pipeline with GitHub Actions
- VM bootable image builder support

### Fixed
- Systematic resolution of compilation errors across 11+ packages:
  - gre_offload (27 errors → 0)
  - xfrm6_output (13 errors → 0)
  - nf_conntrack_netlink (15 errors → 0)
  - ipv6_sockglue (11 errors → 0)
  - mip6 (10 errors → 0)
  - ip6_gre (9 errors → 0)
  - fib6_rules (4 errors → 0)
  - ip6mr, seg6, nf_conntrack_timestamp (2-3 errors each)
- Common patterns resolved:
  - Duplicate struct/constant definitions
  - Function safety (unsafe extern C → extern C with unsafe blocks)
  - Type casting and FFI boundaries
  - Missing imports and extern declarations
  - Markdown artifacts in source files

### Changed
- Migrated from proprietary Claude license to MIT License with Citation Requirement
- Updated all package metadata to reflect open-source status
- Enhanced documentation with citation requirements
- Added CITATION.cff for academic use

### Technical Details
- Base Linux kernel version: 5.10 LTS
- Rust edition: 2021
- no_std compatible for kernel environment
- Maintains C ABI compatibility for seamless kernel integration
- Supports formal verification with Verus/Lean 4 integration points

### Known Issues
- 2 packages remain with compilation errors (af_inet, fib_rules complex)
- Some placeholder implementations need full kernel integration
- Additional testing required for production use

### Breaking Changes
- This is an alpha release - API stability not guaranteed
- Expect significant changes in future releases

### Attribution
Original author: Xavier Callens
Project: Rust Linux Mini Kernel
Repository: https://github.com/xaviercallens/rust-linux-mini-kernel

This project translates portions of the Linux kernel networking stack from C
to Rust while maintaining FFI compatibility. Original Linux kernel code is
copyright of Linus Torvalds and contributors, licensed under GPLv2.

---

## Citation

If you use this software in academic work, please cite:

```bibtex
@software{callens2025rust,
  author = {Callens, Xavier},
  title = {Rust Linux Mini Kernel: FFI-Compatible Rust Translation of Linux Kernel Networking Stack},
  year = {2025},
  url = {https://github.com/xaviercallens/rust-linux-mini-kernel},
  version = {7.0.0-alpha}
}
```
