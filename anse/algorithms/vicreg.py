"""
Production-grade Micro-JEPA Non-Contrastive VICReg Loss Engine.

Computes Invariance (MSE), Variance (Hinge on std), and Covariance (off-diagonal decorrelation)
losses over representation batches, preventing latent dimensional collapse.
Conforms to SPEC-ALG-VICREG and formal Theorem B6 in formal/ANSE/JEPA.lean.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class VICRegLossResult:
    """
    Detailed decomposition of the VICReg loss.

    Attributes:
        total_loss: Weighted sum of invariance, variance, and covariance losses.
        invariance_loss: Mean squared error between representations.
        variance_loss_z: Variance penalty on first branch.
        variance_loss_z_prime: Variance penalty on second branch.
        covariance_loss_z: Covariance decorrelation penalty on first branch.
        covariance_loss_z_prime: Covariance decorrelation penalty on second branch.
        collapse_detected: True if any feature dimension collapsed (std < 1e-3).
    """

    total_loss: float
    invariance_loss: float
    variance_loss_z: float
    variance_loss_z_prime: float
    covariance_loss_z: float
    covariance_loss_z_prime: float
    collapse_detected: bool


def _compute_variance_loss(z_centered: np.ndarray, gamma: float, epsilon: float) -> tuple[float, bool]:
    """Calculate hinge variance loss and check for dimensional collapse."""
    batch_size, num_features = z_centered.shape
    # Sample standard deviation along batch dimension
    variances = np.sum(z_centered * z_centered, axis=0) / (batch_size - 1)
    std_devs = np.sqrt(variances + epsilon)

    hinge = np.maximum(0.0, gamma - std_devs)
    variance_loss = float(np.mean(hinge))
    # Check true empirical std dev without epsilon offset
    collapse = bool(np.any(np.sqrt(variances) < 1e-3))
    return variance_loss, collapse


def _compute_covariance_loss(z_centered: np.ndarray) -> float:
    """Calculate off-diagonal squared covariance penalty."""
    batch_size, num_features = z_centered.shape
    # Covariance matrix C = (Z^T Z) / (B - 1)
    cov_matrix = np.matmul(z_centered.T, z_centered) / (batch_size - 1)
    # Zero out diagonal elements
    np.fill_diagonal(cov_matrix, 0.0)
    # Off-diagonal sum of squares normalized by feature count
    cov_loss = float(np.sum(cov_matrix * cov_matrix) / num_features)
    return cov_loss


def compute_vicreg_loss(
    z: np.ndarray,
    z_prime: np.ndarray,
    sim_coeff: float = 25.0,
    std_coeff: float = 25.0,
    cov_coeff: float = 1.0,
    gamma: float = 1.0,
    epsilon: float = 1e-4,
) -> VICRegLossResult:
    """
    Compute non-contrastive VICReg loss between two latent representation batches.

    Args:
        z: Batch of embeddings, shape (B, D).
        z_prime: Twin batch of embeddings, shape (B, D).
        sim_coeff: Weight multiplier for invariance term (lambda).
        std_coeff: Weight multiplier for variance term (mu).
        cov_coeff: Weight multiplier for covariance term (nu).
        gamma: Target standard deviation threshold (default: 1.0).
        epsilon: Numerical stability constant for square root.

    Returns:
        VICRegLossResult containing the scalar loss and diagnostic components.

    Raises:
        ValueError: If batch size < 2 or tensor shapes do not match.
    """
    z_arr = np.asarray(z, dtype=np.float64)
    z_prime_arr = np.asarray(z_prime, dtype=np.float64)

    if z_arr.shape != z_prime_arr.shape:
        raise ValueError(
            f"Shape mismatch: z has shape {z_arr.shape}, z_prime has shape {z_prime_arr.shape}."
        )

    if z_arr.ndim != 2:
        raise ValueError(f"Input tensors must be 2D (batch_size, num_features), got ndim={z_arr.ndim}.")

    batch_size, num_features = z_arr.shape
    if batch_size < 2:
        raise ValueError(f"Batch size must be at least 2 to compute sample variance, got {batch_size}.")

    if num_features < 1:
        raise ValueError(f"Feature dimension must be at least 1, got {num_features}.")

    # 1. Invariance term: Mean Squared Error
    diff = z_arr - z_prime_arr
    invariance_loss = float(np.mean(np.sum(diff * diff, axis=1)))

    # Centering along batch dimension
    z_centered = z_arr - np.mean(z_arr, axis=0, keepdims=True)
    z_prime_centered = z_prime_arr - np.mean(z_prime_arr, axis=0, keepdims=True)

    # 2. Variance terms (Hinge on standard deviation)
    var_loss_z, collapse_z = _compute_variance_loss(z_centered, gamma, epsilon)
    var_loss_z_prime, collapse_z_prime = _compute_variance_loss(z_prime_centered, gamma, epsilon)

    # 3. Covariance terms (Decorrelation of off-diagonal features)
    cov_loss_z = _compute_covariance_loss(z_centered)
    cov_loss_z_prime = _compute_covariance_loss(z_prime_centered)

    # Total loss combination
    total = (
        sim_coeff * invariance_loss
        + std_coeff * (var_loss_z + var_loss_z_prime)
        + cov_coeff * (cov_loss_z + cov_loss_z_prime)
    )

    return VICRegLossResult(
        total_loss=total,
        invariance_loss=invariance_loss,
        variance_loss_z=var_loss_z,
        variance_loss_z_prime=var_loss_z_prime,
        covariance_loss_z=cov_loss_z,
        covariance_loss_z_prime=cov_loss_z_prime,
        collapse_detected=collapse_z or collapse_z_prime,
    )
