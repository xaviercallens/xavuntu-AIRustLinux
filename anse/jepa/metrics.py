"""
Evaluation metrics for the JEPA world model's energy "intuition".

Pure-Python / torch implementations (scipy and scikit-learn are not dependencies):

    mean_absolute_error   MAE between predicted and verified energies
    average_ranks         tie-aware ranks (ties share their mean rank)
    spearman              rank correlation, tie-aware; None when undefined
    roc_auc               P(score_fail > score_pass) with ties counted 1/2; None when undefined
    ridge_fit_predict     closed-form ridge regression baseline on raw embeddings
    latent_std            per-dimension standard deviation of a batch of latents

"Undefined" is reported as None rather than a made-up number: a constant input has
no rank correlation and a single-class sample has no ROC curve.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import torch


def mean_absolute_error(predicted: Sequence[float], actual: Sequence[float]) -> float:
    """Mean |predicted − actual|."""
    if len(predicted) != len(actual):
        raise ValueError(f"length mismatch: {len(predicted)} predictions vs {len(actual)} labels")
    if not predicted:
        raise ValueError("mean_absolute_error needs at least one sample")
    return sum(abs(p - a) for p, a in zip(predicted, actual)) / len(predicted)


def average_ranks(values: Sequence[float]) -> list[float]:
    """1-based ranks of *values*; tied values share the mean of their positions."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        shared = (start + end) / 2.0 + 1.0
        for position in range(start, end + 1):
            ranks[order[position]] = shared
        start = end + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Spearman rank correlation (Pearson on average ranks). None if either side is constant."""
    if len(x) != len(y):
        raise ValueError(f"length mismatch: {len(x)} vs {len(y)}")
    if len(x) < 2:
        return None
    rx, ry = average_ranks(x), average_ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    var_x = sum((a - mx) ** 2 for a in rx)
    var_y = sum((b - my) ** 2 for b in ry)
    if var_x == 0.0 or var_y == 0.0:
        return None
    return cov / math.sqrt(var_x * var_y)


def roc_auc(scores: Sequence[float], is_positive: Sequence[bool]) -> float | None:
    """Area under the ROC curve: P(score of a positive > score of a negative), ties = 1/2.

    None when one of the two classes is absent.
    """
    if len(scores) != len(is_positive):
        raise ValueError(f"length mismatch: {len(scores)} scores vs {len(is_positive)} labels")
    positives = [s for s, flag in zip(scores, is_positive) if flag]
    negatives = [s for s, flag in zip(scores, is_positive) if not flag]
    if not positives or not negatives:
        return None
    wins = 0.0
    for p in positives:
        for n in negatives:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def ridge_fit_predict(
    x_train: torch.Tensor,
    y_train: torch.Tensor,
    x_eval: torch.Tensor,
    alpha: float = 1.0,
) -> torch.Tensor:
    """Closed-form ridge regression with an unpenalised intercept (dual form, n ≪ d).

    Solves (K + αI) a = y − ȳ with K = X_c X_cᵀ, predicts ȳ + (x − x̄) X_cᵀ a.
    """
    if alpha <= 0.0:
        raise ValueError(f"alpha must be > 0, got {alpha}")
    if x_train.shape[0] != y_train.shape[0]:
        raise ValueError("x_train and y_train must have the same number of rows")
    x_mean = x_train.mean(dim=0, keepdim=True)
    y_mean = y_train.mean()
    xc = (x_train - x_mean).double()
    gram = xc @ xc.T
    dual = torch.linalg.solve(
        gram + alpha * torch.eye(gram.shape[0], dtype=torch.float64), (y_train - y_mean).double()
    )
    return (((x_eval - x_mean).double() @ xc.T) @ dual + y_mean.double()).float()


def latent_std(z: torch.Tensor) -> torch.Tensor:
    """Per-dimension standard deviation over a batch of latents [B, k] → [k]."""
    if z.dim() != 2 or z.shape[0] < 2:
        raise ValueError("latent_std needs a [B, k] batch with B >= 2")
    return z.std(dim=0, unbiased=True)
