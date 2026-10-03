"""
ANSE 2.0 — Upgrade 2: Zeroth-Order Plasticity via MeZO.

Solves the Edge Hardware Wall:
- Standard backprop stores activations and optimizer states, requiring 3-4x inference VRAM.
- MeZO (Memory-Efficient Zeroth-Order Optimization) computes parameter updates using
  ONLY two forward passes with pseudo-random perturbations.
- Allows continuous biological learning directly on laptops or edge devices with
  EXACTLY identical memory overhead as standard read-only inference.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


@dataclass
class MeZOStepResult:
    """Telemetry from a single Zeroth-Order MeZO optimization step."""

    step: int
    loss_positive: float
    loss_negative: float
    projected_gradient: float
    loss_delta: float
    peak_memory_bytes: int
    duration_ms: float


class MeZOOptimizer:
    """
    Memory-Efficient Zeroth-Order Optimizer (MeZO).
    Operates without allocating gradient tensors or retaining computation graphs.
    """

    def __init__(
        self,
        model: nn.Module,
        lr: float = 1e-4,
        epsilon: float = 1e-3,
        weight_decay: float = 1e-5,
    ) -> None:
        self.model = model
        self.lr = lr
        self.epsilon = epsilon
        self.weight_decay = weight_decay
        self.step_count = 0

    @torch.no_grad()
    def step(
        self,
        loss_fn: Callable[[], torch.Tensor],
        seed: int | None = None,
    ) -> MeZOStepResult:
        """
        Executes a single MeZO update step using strictly two forward passes:
        1. Perturb parameters: theta <- theta + epsilon * z
        2. Evaluate L+ = loss_fn()
        3. Perturb parameters: theta <- theta - 2 * epsilon * z
        4. Evaluate L- = loss_fn()
        5. Restore parameters: theta <- theta + epsilon * z
        6. Compute scalar directional derivative: g = (L+ - L-) / (2 * epsilon)
        7. Update parameters in-place: theta <- theta - lr * (g * z + weight_decay * theta)

        All operations run under torch.no_grad(). Zero gradient tensors are allocated.
        """
        t0 = time.perf_counter()
        self.step_count += 1

        # Use seed or auto-generate seed to generate identical perturbation on the fly
        rand_seed = seed if seed is not None else int(torch.randint(0, 2**31 - 1, (1,)).item())

        # 1. Forward perturbation: theta <- theta + epsilon * z
        torch.manual_seed(rand_seed)
        for p in self.model.parameters():
            if p.requires_grad:
                z = torch.randn_like(p)
                p.add_(z, alpha=self.epsilon)

        loss_pos = float(loss_fn().item())

        # 2. Backward perturbation: theta <- theta - 2 * epsilon * z
        torch.manual_seed(rand_seed)
        for p in self.model.parameters():
            if p.requires_grad:
                z = torch.randn_like(p)
                p.sub_(z, alpha=2.0 * self.epsilon)

        loss_neg = float(loss_fn().item())

        # 3. Restore parameters: theta <- theta + epsilon * z
        torch.manual_seed(rand_seed)
        for p in self.model.parameters():
            if p.requires_grad:
                z = torch.randn_like(p)
                p.add_(z, alpha=self.epsilon)

        # 4. Projected directional gradient
        projected_grad = (loss_pos - loss_neg) / (2.0 * self.epsilon)

        # 5. In-place parameter update
        torch.manual_seed(rand_seed)
        for p in self.model.parameters():
            if p.requires_grad:
                z = torch.randn_like(p)
                if self.weight_decay > 0.0:
                    p.mul_(1.0 - self.lr * self.weight_decay)
                p.sub_(z, alpha=self.lr * projected_grad)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        peak_mem = torch.cuda.max_memory_allocated() if torch.cuda.is_available() else 0

        return MeZOStepResult(
            step=self.step_count,
            loss_positive=round(loss_pos, 5),
            loss_negative=round(loss_neg, 5),
            projected_gradient=round(projected_grad, 5),
            loss_delta=round(loss_pos - loss_neg, 5),
            peak_memory_bytes=peak_mem,
            duration_ms=round(elapsed_ms, 3),
        )


class EdgeContinuousPlasticityEngine:
    """
    Manages online continuous learning on edge hardware using MeZO.
    Enables instant continuous plasticity without requiring multi-GPU VRAM.
    """

    def __init__(
        self,
        model: nn.Module,
        lr: float = 1e-4,
        epsilon: float = 1e-3,
    ) -> None:
        self.model = model
        self.optimizer = MeZOOptimizer(model, lr=lr, epsilon=epsilon)
        self.history: list[MeZOStepResult] = []

    def adapt_on_prediction_surprise(
        self,
        current_state: torch.Tensor,
        action: torch.Tensor,
        actual_future: torch.Tensor,
    ) -> MeZOStepResult:
        """
        Executes active inference plasticity step via MeZO forward passes.
        """

        def compute_surprise_loss() -> torch.Tensor:
            pred = self.model(current_state, action)
            return nn.functional.mse_loss(pred, actual_future)

        step_res = self.optimizer.step(compute_surprise_loss)
        self.history.append(step_res)
        return step_res
