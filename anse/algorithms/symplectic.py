"""
ANSE Symplectic Integrator & Hamiltonian Physics Engine.

Implements Velocity-Verlet symplectic integration for separable Hamiltonian systems:
H(q, p) = T(p) + V(q) = 1/2 * p^T * p + V(q)
Equations of motion:
dq/dt =  dH/dp = p
dp/dt = -dH/dq = -grad V(q)

Features:
- Native Rust C-ABI acceleration via ctypes (with automatic pure-Python fallback).
- Symplectic 2-form dq ^ dp preservation and strict energy drift bounds (|Delta H / H_0| < 1e-3).
- Poincaré section calculation for non-linear chaos detection (e.g. Hénon-Heiles).
- Multi-task Lyapunov exponent estimation.
- Explicit non-symplectic Euler baseline for DPO physical preference training.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import math
import os
from pathlib import Path
import sys
import time
from typing import Sequence

# ---------------------------------------------------------------------------
# C-ABI Dynamic Library Loader
# ---------------------------------------------------------------------------

_RUST_LIB: ctypes.CDLL | None = None


def _find_and_load_rust_lib() -> ctypes.CDLL | None:
    global _RUST_LIB
    if _RUST_LIB is not None:
        return _RUST_LIB

    search_dirs = [
        Path(__file__).resolve().parents[2] / "crates" / "anse_physics" / "target" / "release",
        Path(__file__).resolve().parents[2] / "crates" / "anse_physics" / "target" / "debug",
        Path("/usr/local/lib"),
        Path.cwd() / "crates" / "anse_physics" / "target" / "release",
    ]

    lib_names = ["libanse_physics.so", "libanse_physics.dylib", "anse_physics.dll"]

    for d in search_dirs:
        for name in lib_names:
            candidate = d / name
            if candidate.is_file():
                try:
                    lib = ctypes.CDLL(str(candidate))
                    # Setup function signatures
                    # 1. symplectic_integrate
                    lib.symplectic_integrate.argtypes = [
                        ctypes.c_int32,                          # potential_type
                        ctypes.c_double,                         # lambda
                        ctypes.c_size_t,                         # dim
                        ctypes.c_size_t,                         # steps
                        ctypes.c_double,                         # dt
                        ctypes.POINTER(ctypes.c_double),         # q_init
                        ctypes.POINTER(ctypes.c_double),         # p_init
                        ctypes.POINTER(ctypes.c_double),         # out_q
                        ctypes.POINTER(ctypes.c_double),         # out_p
                        ctypes.POINTER(ctypes.c_double),         # out_energies
                    ]
                    lib.symplectic_integrate.restype = ctypes.c_int32

                    # 2. symplectic_hamiltonian
                    lib.symplectic_hamiltonian.argtypes = [
                        ctypes.c_int32,                          # potential_type
                        ctypes.c_double,                         # lambda
                        ctypes.c_size_t,                         # dim
                        ctypes.POINTER(ctypes.c_double),         # q_ptr
                        ctypes.POINTER(ctypes.c_double),         # p_ptr
                        ctypes.POINTER(ctypes.c_double),         # out_energy
                    ]
                    lib.symplectic_hamiltonian.restype = ctypes.c_int32

                    # 3. symplectic_poincare
                    lib.symplectic_poincare.argtypes = [
                        ctypes.c_int32,                          # potential_type
                        ctypes.c_double,                         # lambda
                        ctypes.c_size_t,                         # dim
                        ctypes.c_size_t,                         # steps
                        ctypes.c_double,                         # dt
                        ctypes.POINTER(ctypes.c_double),         # q_init
                        ctypes.POINTER(ctypes.c_double),         # p_init
                        ctypes.c_size_t,                         # max_crossings
                        ctypes.POINTER(ctypes.c_double),         # cross_y
                        ctypes.POINTER(ctypes.c_double),         # cross_py
                        ctypes.POINTER(ctypes.c_size_t),         # out_count
                    ]
                    lib.symplectic_poincare.restype = ctypes.c_int32

                    _RUST_LIB = lib
                    return _RUST_LIB
                except (OSError, AttributeError):
                    continue

    return None


# ---------------------------------------------------------------------------
# Data Models & Enums
# ---------------------------------------------------------------------------

POTENTIAL_HARMONIC = 0
POTENTIAL_DOUBLE_WELL = 1
POTENTIAL_HENON_HEILES = 2

POTENTIAL_MAP = {
    "harmonic": POTENTIAL_HARMONIC,
    "double_well": POTENTIAL_DOUBLE_WELL,
    "henon_heiles": POTENTIAL_HENON_HEILES,
}


@dataclass(frozen=True)
class SymplecticResult:
    """Result of Hamiltonian trajectory integration."""

    trajectory_q: list[list[float]]
    trajectory_p: list[list[float]]
    energy_h: list[float]
    energy_drift: float
    poincare_crossings: list[tuple[list[float], list[float]]]
    lyapunov_exponent: float
    is_symplectic: bool
    backend: str
    duration_ms: float


# ---------------------------------------------------------------------------
# Pure Python Mathematical Physics Kernels
# ---------------------------------------------------------------------------

def _grad_v(potential_type: int, q: Sequence[float]) -> list[float]:
    """Analytical gradient of potential energy nabla V(q)."""
    dim = len(q)
    grad = [0.0] * dim
    if potential_type == POTENTIAL_HARMONIC:
        for i in range(dim):
            grad[i] = q[i]
    elif potential_type == POTENTIAL_DOUBLE_WELL:
        grad[0] = q[0] ** 3 - q[0]
        for i in range(1, dim):
            grad[i] = q[i]
    elif potential_type == POTENTIAL_HENON_HEILES:
        if dim >= 2:
            x, y = q[0], q[1]
            grad[0] = x + 2.0 * x * y
            grad[1] = y + x * x - y * y
            for i in range(2, dim):
                grad[i] = q[i]
        else:
            grad[0] = q[0]
    return grad


def _hamiltonian(potential_type: int, q: Sequence[float], p: Sequence[float]) -> float:
    """Compute total Hamiltonian H(q, p) = T(p) + V(q)."""
    kinetic = 0.5 * sum(x * x for x in p)
    potential = 0.0
    dim = len(q)
    if potential_type == POTENTIAL_HARMONIC:
        potential = 0.5 * sum(x * x for x in q)
    elif potential_type == POTENTIAL_DOUBLE_WELL:
        potential = 0.25 * (q[0] ** 2 - 1.0) ** 2
        if dim > 1:
            potential += 0.5 * sum(q[i] ** 2 for i in range(1, dim))
    elif potential_type == POTENTIAL_HENON_HEILES:
        if dim >= 2:
            x, y = q[0], q[1]
            potential = 0.5 * (x * x + y * y) + (x * x * y - (y ** 3) / 3.0)
            if dim > 2:
                potential += 0.5 * sum(q[i] ** 2 for i in range(2, dim))
        else:
            potential = 0.5 * (q[0] ** 2)
    return kinetic + potential


def _python_velocity_verlet(
    potential_type: int,
    q0: Sequence[float],
    p0: Sequence[float],
    dt: float,
    steps: int,
) -> tuple[list[list[float]], list[list[float]], list[float], float]:
    """Pure Python Symplectic Velocity-Verlet integrator."""
    dim = len(q0)
    cur_q = list(q0)
    cur_p = list(p0)

    traj_q = [list(cur_q)]
    traj_p = [list(cur_p)]

    h0 = _hamiltonian(potential_type, cur_q, cur_p)
    energies = [h0]
    max_drift = 0.0

    grad_v = _grad_v(potential_type, cur_q)

    for _ in range(steps):
        # 1. p(t + dt/2) = p(t) - (dt/2) * grad V(q(t))
        p_half = [cur_p[i] - 0.5 * dt * grad_v[i] for i in range(dim)]

        # 2. q(t + dt) = q(t) + dt * p(t + dt/2)
        next_q = [cur_q[i] + dt * p_half[i] for i in range(dim)]

        # 3. grad V(q(t + dt))
        next_grad_v = _grad_v(potential_type, next_q)

        # 4. p(t + dt) = p(t + dt/2) - (dt/2) * grad V(q(t + dt))
        next_p = [p_half[i] - 0.5 * dt * next_grad_v[i] for i in range(dim)]

        cur_q = next_q
        cur_p = next_p
        grad_v = next_grad_v

        ht = _hamiltonian(potential_type, cur_q, cur_p)
        energies.append(ht)
        drift = abs(ht - h0) / max(abs(h0), 1e-12)
        if drift > max_drift:
            max_drift = drift

        traj_q.append(list(cur_q))
        traj_p.append(list(cur_p))

    return traj_q, traj_p, energies, max_drift


# ---------------------------------------------------------------------------
# Multi-Task APIs
# ---------------------------------------------------------------------------

def compute_poincare_section(
    trajectory_q: Sequence[Sequence[float]],
    trajectory_p: Sequence[Sequence[float]],
    cross_dim: int = 0,
    cross_val: float = 0.0,
) -> list[tuple[list[float], list[float]]]:
    """
    Detect Poincaré surface of section crossings:
    Hyperplane: q[cross_dim] == cross_val with positive momentum p[cross_dim] > 0.
    """
    crossings: list[tuple[list[float], list[float]]] = []
    dim = len(trajectory_q[0])

    for i in range(len(trajectory_q) - 1):
        q_a = trajectory_q[i]
        q_b = trajectory_q[i + 1]
        p_a = trajectory_p[i]
        p_b = trajectory_p[i + 1]

        val_a = q_a[cross_dim] - cross_val
        val_b = q_b[cross_dim] - cross_val

        # Upward crossing (val_a <= 0.0 and val_b > 0.0) with p > 0
        if val_a <= 0.0 and val_b > 0.0:
            denom = val_b - val_a
            theta = (0.0 - val_a) / denom if abs(denom) > 1e-15 else 0.5
            p_cross_coord = p_a[cross_dim] + theta * (p_b[cross_dim] - p_a[cross_dim])
            if p_cross_coord > 0.0:
                q_interp = [q_a[d] + theta * (q_b[d] - q_a[d]) for d in range(dim)]
                p_interp = [p_a[d] + theta * (p_b[d] - p_a[d]) for d in range(dim)]
                crossings.append((q_interp, p_interp))

    return crossings


def estimate_lyapunov_exponent(
    potential: str | int = "henon_heiles",
    q0: Sequence[float] = (0.0, 0.2),
    p0: Sequence[float] = (0.3, 0.0),
    dt: float = 0.01,
    steps: int = 600,
    perturbation: float = 1e-8,
) -> float:
    """
    Estimate the maximal Lyapunov exponent lambda via orbit divergence:
    lambda = (1 / (N * dt)) * sum_k ln(||delta_k|| / d0)
    """
    pot_code = POTENTIAL_MAP[potential] if isinstance(potential, str) else potential
    dim = len(q0)

    # Reference orbit
    res1 = solve_symplectic_orbit(pot_code, q0, p0, dt=dt, steps=steps, compute_aux=False)

    # Perturbed orbit
    q0_pert = list(q0)
    q0_pert[0] += perturbation
    res2 = solve_symplectic_orbit(pot_code, q0_pert, p0, dt=dt, steps=steps, compute_aux=False)

    total_time = steps * dt
    dist_final = math.sqrt(
        sum((res1.trajectory_q[-1][d] - res2.trajectory_q[-1][d]) ** 2 for d in range(dim))
        + sum((res1.trajectory_p[-1][d] - res2.trajectory_p[-1][d]) ** 2 for d in range(dim))
    )

    if dist_final <= 0.0:
        return 0.0

    exponent = math.log(dist_final / perturbation) / max(total_time, 1e-9)
    return max(0.0, float(exponent))


def solve_symplectic_orbit(
    potential: str | int = "harmonic",
    q0: Sequence[float] = (1.0,),
    p0: Sequence[float] = (0.0,),
    dt: float = 0.01,
    steps: int = 1000,
    prefer_rust: bool = True,
    compute_aux: bool = True,
) -> SymplecticResult:
    """
    Integrate Hamiltonian system using symplectic Velocity-Verlet.
    Leverages native Rust C-ABI if available, or pure Python fallback.
    """
    pot_code = POTENTIAL_MAP[potential] if isinstance(potential, str) else potential
    dim = len(q0)
    assert len(p0) == dim, "Dimension mismatch between q0 and p0"

    rust_lib = _find_and_load_rust_lib() if prefer_rust else None

    t_start = time.perf_counter()

    if rust_lib is not None:
        backend = "rust_cabi"
        out_q_buf = (ctypes.c_double * (steps * dim))()
        out_p_buf = (ctypes.c_double * (steps * dim))()
        out_energy_buf = (ctypes.c_double * steps)()

        q0_c = (ctypes.c_double * dim)(*q0)
        p0_c = (ctypes.c_double * dim)(*p0)

        ret = rust_lib.symplectic_integrate(
            ctypes.c_int32(pot_code),
            ctypes.c_double(1.0),
            ctypes.c_size_t(dim),
            ctypes.c_size_t(steps),
            ctypes.c_double(dt),
            q0_c,
            p0_c,
            out_q_buf,
            out_p_buf,
            out_energy_buf,
        )
        if ret != 0:
            raise RuntimeError(f"Rust symplectic_integrate failed with code {ret}")

        # Unpack buffers
        traj_q = [
            [out_q_buf[i * dim + d] for d in range(dim)]
            for i in range(steps)
        ]
        traj_p = [
            [out_p_buf[i * dim + d] for d in range(dim)]
            for i in range(steps)
        ]
        energies = [out_energy_buf[i] for i in range(steps)]
        h0 = energies[0] if energies else 1.0
        energy_drift = max((abs(h - h0) / max(abs(h0), 1e-12)) for h in energies) if energies else 0.0
    else:
        backend = "python_pure"
        traj_q, traj_p, energies, energy_drift = _python_velocity_verlet(
            pot_code, q0, p0, dt, steps
        )

    duration_ms = (time.perf_counter() - t_start) * 1000.0

    poincare_crossings: list[tuple[list[float], list[float]]] = []
    lyap_exp = 0.0

    if compute_aux and steps >= 10:
        poincare_crossings = compute_poincare_section(traj_q, traj_p, cross_dim=0, cross_val=0.0)
        lyap_exp = estimate_lyapunov_exponent(pot_code, q0, p0, dt=dt, steps=min(steps, 400))

    is_symplectic = energy_drift < 1e-3

    return SymplecticResult(
        trajectory_q=traj_q,
        trajectory_p=traj_p,
        energy_h=energies,
        energy_drift=energy_drift,
        poincare_crossings=poincare_crossings,
        lyapunov_exponent=lyap_exp,
        is_symplectic=is_symplectic,
        backend=backend,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Non-Symplectic Explicit Euler Baseline (DPO Rejected Example)
# ---------------------------------------------------------------------------

def explicit_euler_integrate(
    potential: str | int = "harmonic",
    q0: Sequence[float] = (1.0,),
    p0: Sequence[float] = (0.0,),
    dt: float = 0.01,
    steps: int = 1000,
) -> SymplecticResult:
    """
    Explicit forward Euler integrator (NON-SYMPLECTIC baseline).
    Known to violate conservation of phase space volume and explode in energy.
    Used as the negative training signal (rejected) in DPO physical alignment.
    """
    pot_code = POTENTIAL_MAP[potential] if isinstance(potential, str) else potential
    dim = len(q0)

    cur_q = list(q0)
    cur_p = list(p0)
    traj_q = [list(cur_q)]
    traj_p = [list(cur_p)]

    h0 = _hamiltonian(pot_code, cur_q, cur_p)
    energies = [h0]
    max_drift = 0.0

    t_start = time.perf_counter()

    for _ in range(steps):
        grad = _grad_v(pot_code, cur_q)
        # Standard explicit Euler:
        # q_{t+1} = q_t + dt * p_t
        # p_{t+1} = p_t - dt * grad V(q_t)
        next_q = [cur_q[i] + dt * cur_p[i] for i in range(dim)]
        next_p = [cur_p[i] - dt * grad[i] for i in range(dim)]

        cur_q = next_q
        cur_p = next_p

        ht = _hamiltonian(pot_code, cur_q, cur_p)
        energies.append(ht)
        drift = abs(ht - h0) / max(abs(h0), 1e-12)
        if drift > max_drift:
            max_drift = drift

        traj_q.append(list(cur_q))
        traj_p.append(list(cur_p))

    duration_ms = (time.perf_counter() - t_start) * 1000.0

    return SymplecticResult(
        trajectory_q=traj_q,
        trajectory_p=traj_p,
        energy_h=energies,
        energy_drift=max_drift,
        poincare_crossings=[],
        lyapunov_exponent=0.0,
        is_symplectic=max_drift < 1e-3,
        backend="python_explicit_euler",
        duration_ms=duration_ms,
    )
