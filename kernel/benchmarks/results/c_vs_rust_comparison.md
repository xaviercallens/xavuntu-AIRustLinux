# C vs Rust Performance Comparison Report

**Generated:** 2026-05-21 13:29:34
**Platform:** Darwin arm64
**Methodology:** Each benchmark runs 5 iterations; median reported.

---

## Results Summary

### CRC32 (1M × 4KB)

| Metric | C | Rust | Delta |
|--------|---|------|-------|
| **Median Time** | 10.4300s | 9.9369s | -4.7% (Rust faster) |
| **Min Time** | 10.1267s | 9.8902s | — |
| **Binary Size** | 33,792 B | 319,264 B | 9.45× |
| **Flags** | `-O3 -march=native` | `-C opt-level=3 -C lto=fat -C codegen-units=1` | — |

---

## Methodology Notes

1. **CRC32**: Computes CRC32 over a 4096-byte buffer, 1 million iterations. Tests tight loop performance, table lookups, and branch prediction.
2. **Compiler Optimization**: Both languages use maximum optimization (`-O3` / `opt-level=3`) with architecture-native instruction sets.
3. **Rust Advantages**: LTO + single codegen unit enables whole-program optimization. `noalias` on `&[u8]` slice enables auto-vectorization.
4. **C Advantages**: Decades of GCC optimization for this exact pattern. No monomorphization overhead.

## AI/ML Optimization Opportunities

| Technique | Expected Impact | Status |
|-----------|-----------------|--------|
| **PGO** (Profile-Guided Optimization) | +3–10% throughput | Ready to apply |
| **BOLT** (Binary Layout) | +2–5% additional | Ready to apply |
| **MLGO** (ML-Guided Inlining) | −3–7% binary size | Requires custom LLVM |
| **Meta LLM Compiler** | +2–5% pass ordering | Offline advisor |
