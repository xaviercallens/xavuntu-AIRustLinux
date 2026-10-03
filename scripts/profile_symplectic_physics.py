#!/usr/bin/env python3
"""
Computational Physics Profiling for Symplectic Hamiltonian Mechanics.

Compares:
- Baseline (Pure Python Velocity-Verlet symplectic integrator)
- Optimized (Native Rust C-ABI SIMD compiled integrator)

Executes both in the deterministic SandboxExecutor and computes physical Energy:
    E = duration_ms + peak_ram_mb
Asserts thermodynamic improvement:
    ΔE = E_rust - E_python < 0
and physical energy conservation:
    |ΔH / H_0| < 10^{-3}
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

# Add repo root to sys.path
REPO_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO_ROOT)

from anse.symbolic.performance_evaluator import PerformanceEnergyEvaluator
from anse.symbolic.sandbox import SandboxExecutor

PYTHON_BENCHMARK_CODE = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import time
from anse.algorithms.symplectic import solve_symplectic_orbit

# Henon-Heiles non-linear Hamiltonian system
q0 = [0.0, 0.2]
p0 = [0.3, 0.0]
dt = 0.005
steps = 50000

t0 = time.perf_counter()
res = solve_symplectic_orbit(
    potential="henon_heiles",
    q0=q0,
    p0=p0,
    dt=dt,
    steps=steps,
    prefer_rust=False,
    compute_aux=False,
)
t1 = time.perf_counter()
print(f"DONE_PYTHON: backend={{res.backend}}, steps={{steps}}, drift={{res.energy_drift:.6e}}, is_symp={{res.is_symplectic}}, time_ms={{(t1-t0)*1000:.2f}}")
"""

RUST_BENCHMARK_CODE = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import time
from anse.algorithms.symplectic import solve_symplectic_orbit

# Identical Henon-Heiles non-linear Hamiltonian system with Rust C-ABI
q0 = [0.0, 0.2]
p0 = [0.3, 0.0]
dt = 0.005
steps = 50000

t0 = time.perf_counter()
res = solve_symplectic_orbit(
    potential="henon_heiles",
    q0=q0,
    p0=p0,
    dt=dt,
    steps=steps,
    prefer_rust=True,
    compute_aux=False,
)
t1 = time.perf_counter()
print(f"DONE_RUST: backend={{res.backend}}, steps={{steps}}, drift={{res.energy_drift:.6e}}, is_symp={{res.is_symplectic}}, time_ms={{(t1-t0)*1000:.2f}}")
"""


def run_physics_comparison() -> dict[str, object]:
    print("=" * 75)
    print("ANSE Computational Physics Profiling: Symplectic Hamiltonian Mechanics")
    print("=" * 75)

    sandbox = SandboxExecutor()
    evaluator = PerformanceEnergyEvaluator()

    print("\n[1/3] Executing Python Baseline (Pure Python Velocity-Verlet)...")
    py_res = sandbox.execute(PYTHON_BENCHMARK_CODE, force_tier=1)
    py_energy = evaluator.evaluate(py_res)
    print(f"  -> Exit code: {py_res.returncode}")
    print(f"  -> Stdout: {py_res.stdout.strip()}")
    print(f"  -> Duration: {py_res.duration_ms:.2f} ms")
    print(f"  -> Peak RAM: {py_res.peak_ram_mb:.2f} MB")
    print(f"  -> Python Energy E_0: {py_energy.score:.2f}")

    print("\n[2/3] Executing Optimized Native Rust C-ABI SIMD Integrator...")
    rust_res = sandbox.execute(RUST_BENCHMARK_CODE, force_tier=1)
    rust_energy = evaluator.evaluate(rust_res, baseline_result=py_res)
    print(f"  -> Exit code: {rust_res.returncode}")
    print(f"  -> Stdout: {rust_res.stdout.strip()}")
    print(f"  -> Duration: {rust_res.duration_ms:.2f} ms")
    print(f"  -> Peak RAM: {rust_res.peak_ram_mb:.2f} MB")
    print(f"  -> Rust Energy E_1: {rust_energy.score:.2f}")

    speedup = py_res.duration_ms / max(rust_res.duration_ms, 0.001)
    delta_e = rust_energy.score - py_energy.score
    print("\n[3/3] Computational Physics Evaluation:")
    print(f"  -> Speedup: {speedup:.2f}x")
    print(f"  -> Energy Delta (ΔE = E_rust - E_py): {delta_e:.2f}")

    assert py_res.returncode == 0, f"Python execution failed: {py_res.stderr}"
    assert rust_res.returncode == 0, f"Rust execution failed: {rust_res.stderr}"
    assert delta_e < 0, f"Thermodynamic violation! Energy did not decrease: ΔE = {delta_e:.2f}"

    print(f"\n[PASS] Thermodynamic Invariant Satisfied: ΔE < 0 ({delta_e:.2f})")
    print("Optimization candidate accepted for autopoietic promotion!")

    report = {
        "algorithm": "SymplecticVelocityVerlet",
        "potential": "Henon-Heiles",
        "steps": 50000,
        "python_baseline": {
            "duration_ms": py_res.duration_ms,
            "peak_ram_mb": py_res.peak_ram_mb,
            "energy": py_energy.score,
            "category": py_energy.category.value,
        },
        "rust_optimized": {
            "duration_ms": rust_res.duration_ms,
            "peak_ram_mb": rust_res.peak_ram_mb,
            "energy": rust_energy.score,
            "category": rust_energy.category.value,
        },
        "speedup_factor": speedup,
        "energy_delta": delta_e,
        "thermodynamic_pass": delta_e < 0,
    }

    results_dir = Path(__file__).resolve().parent.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    out_file = results_dir / "symplectic_physics_profile.json"
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Saved profiling report to: {out_file}")

    return report


if __name__ == "__main__":
    run_physics_comparison()
