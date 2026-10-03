"""
PhD-Level Multidisciplinary Benchmark Suite for ANSE.

Contains 30 rigorous test cases across three domains:
- 10 Rust Numerical Computing Kernels (compiled and benchmarked via rustc -O)
- 10 Pure Mathematics Formal Theorems (evaluated via SymPy / NumPy CAS)
- 10 Pure Theoretical Physics Formal Theorems (evaluated via physical invariant engines)
"""

from __future__ import annotations

__all__ = [
    "run_all_rust_benchmarks",
    "run_all_math_benchmarks",
    "run_all_physics_benchmarks",
]
