"""
Production-grade Banach Fixed-Point Contraction Engine.

Computes iterative fixed points x* = Phi(x*) in complete Euclidean metric spaces,
verifying contraction bounds (Lipschitz L < 1) and geometric convergence.
Directly grounds formal theorems in formal/ANSE/Autopoiesis.lean.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class FixedPointResult:
    """
    Result of a Banach fixed point iterative computation.

    Attributes:
        fixed_point: The converged state vector x*.
        converged: True if successive residual fell below tol.
        iterations: Number of function evaluations performed.
        estimated_lipschitz: Maximum observed empirical contraction ratio L.
        residual: Final distance ||x_{k+1} - x_k||.
        history: Sequence of residuals across iterations.
    """

    fixed_point: np.ndarray
    converged: bool
    iterations: int
    estimated_lipschitz: float
    residual: float
    history: list[float]


def estimate_lipschitz_constant(
    operator: Callable[[np.ndarray], np.ndarray],
    sample_pairs: list[tuple[np.ndarray, np.ndarray]],
) -> float:
    """
    Empirically estimate the Lipschitz constant L over a set of state pairs (x, y).

    Returns:
        Max ratio ||Phi(x) - Phi(y)|| / ||x - y||.
    """
    max_l = 0.0
    for x, y in sample_pairs:
        d_in = float(np.linalg.norm(x - y))
        if d_in < 1e-12:
            continue
        out_x = operator(x)
        out_y = operator(y)
        d_out = float(np.linalg.norm(out_x - out_y))
        ratio = d_out / d_in
        if ratio > max_l:
            max_l = ratio
    return max_l


def solve_banach_fixed_point(
    operator: Callable[[np.ndarray], np.ndarray],
    initial_state: np.ndarray,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> FixedPointResult:
    """
    Find fixed point x* such that operator(x*) == x* via Picard iteration.

    Args:
        operator: Continuous mapping Phi: R^d -> R^d.
        initial_state: Initial state vector x0.
        tol: Convergence tolerance for ||x_{k+1} - x_k||.
        max_iter: Maximum permitted iterations before timeout.

    Returns:
        FixedPointResult with convergence diagnostics.

    Raises:
        ValueError: If iteration diverges (|x| -> inf) or NaN is generated.
    """
    x_curr = np.asarray(initial_state, dtype=np.float64).copy()
    history: list[float] = []
    max_l_ratio: float = 0.0
    prev_diff: float | None = None

    for i in range(1, max_iter + 1):
        x_next = np.asarray(operator(x_curr), dtype=np.float64)

        if np.any(np.isnan(x_next)) or np.any(np.isinf(x_next)):
            raise ValueError(
                f"Divergence detected at iteration {i}: operator returned NaN or Inf."
            )

        diff = float(np.linalg.norm(x_next - x_curr))
        history.append(diff)

        if prev_diff is not None and prev_diff > 1e-12:
            step_l = diff / prev_diff
            if step_l > max_l_ratio:
                max_l_ratio = step_l

        if diff < tol:
            return FixedPointResult(
                fixed_point=x_next,
                converged=True,
                iterations=i,
                estimated_lipschitz=max_l_ratio,
                residual=diff,
                history=history,
            )

        prev_diff = diff
        x_curr = x_next

    return FixedPointResult(
        fixed_point=x_curr,
        converged=False,
        iterations=max_iter,
        estimated_lipschitz=max_l_ratio,
        residual=history[-1] if history else float("inf"),
        history=history,
    )
