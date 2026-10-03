"""
Exponential Moving Average (EMA) utilities for the JEPA target encoder.

Lean 4 ref: ANSE.JEPA.ema_step — θ̄ ← τ · θ̄ + (1 − τ) · θ
Lean 4 ref: TargetEncoder.momentum — hmom : 0 < τ ∧ τ ≤ 1
Lean 4 ref: ema_converges_step — proved by rfl
"""

from __future__ import annotations

import math

import torch.nn as nn


def ema_update(
    target: nn.Module,
    source: nn.Module,
    tau: float,
) -> None:
    """Update target encoder parameters toward source (context) encoder.

    Lean 4 ref::

        ema_step τ hτ ctx_enc tgt_enc :=
          fun h_in => τ • tgt_enc h_in + (1 − τ) • ctx_enc h_in

    Implements the parameter-space equivalent:
        θ̄ ← τ · θ̄ + (1 − τ) · θ

    Args:
        target: Target encoder whose parameters are updated *in-place*.
        source: Context encoder providing the "fresh" parameters.
        tau: Momentum coefficient.  Must satisfy 0 < τ ≤ 1.

    Raises:
        ValueError: If tau is outside (0, 1].
    """
    if tau <= 0.0 or tau > 1.0:
        raise ValueError(
            f"EMA momentum τ must satisfy 0 < τ ≤ 1, got τ={tau}. "
            "Lean 4 ref: TargetEncoder.hmom : 0 < momentum ∧ momentum ≤ 1"
        )

    # Target encoder never accumulates gradients: update raw ``.data`` in-place.
    for p_tgt, p_src in zip(target.parameters(), source.parameters()):
        p_tgt.data.mul_(tau).add_(p_src.data, alpha=1.0 - tau)


def cosine_ema_schedule(
    step: int,
    total_steps: int,
    tau_start: float = 0.996,
    tau_end: float = 1.0,
) -> float:
    """Cosine annealing schedule for EMA momentum τ.

    Produces τ values from tau_start → tau_end following a cosine curve.
    Used by eb_jepa (FAIR/Meta AI) for stable target encoder training.

    Args:
        step: Current training step (0-indexed).
        total_steps: Total number of training steps.
        tau_start: Initial momentum (default: 0.996).
        tau_end: Final momentum (default: 1.0).

    Returns:
        Momentum value τ for the given step.

    Raises:
        ValueError: If step or total_steps are invalid.
    """
    if total_steps <= 0:
        raise ValueError(f"total_steps must be > 0, got {total_steps}")
    if step < 0:
        raise ValueError(f"step must be >= 0, got {step}")

    # Clamp step to total_steps (past the end → return tau_end)
    step = min(step, total_steps)

    progress = step / total_steps
    # Cosine annealing: starts slow, accelerates, then slows again
    tau = tau_end - (tau_end - tau_start) * (1.0 + math.cos(math.pi * progress)) / 2.0
    return tau
