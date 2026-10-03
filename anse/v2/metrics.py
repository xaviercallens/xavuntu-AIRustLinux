"""Metrics for a zero-inflated, few-valued target (card V0-3).

The cosmo3 retrofit showed that ``energy_accuracy`` (fraction of predictions within a
threshold) reaches 1.00 on real *and* on shuffled labels, so it cannot tell learning
from noise. The functions here are rank-based and therefore insensitive to the scale
of the scores; each returns ``None`` when it is undefined instead of a misleading number.

Pure Python only (no numpy, no scipy) so the module has no import-time cost and its
results are bit-reproducible across environments.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence

MetricFn = Callable[[Sequence[float], Sequence[float]], float | None]


def average_ranks(values: Sequence[float]) -> list[float]:
    """1-based ranks of *values*; tied values share the average of their positions."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        mean_rank = (i + j + 2) / 2.0  # positions are 0-based, ranks 1-based
        for k in range(i, j + 1):
            ranks[order[k]] = mean_rank
        i = j + 1
    return ranks


def auroc(scores: Sequence[float], labels: Sequence[int]) -> float | None:
    """Area under the ROC curve via the Mann-Whitney U statistic.

    Labels must be 0 or 1; a positive is a label of 1. Ties in *scores* count half,
    which is what average ranks give. Returns ``None`` when only one class is present.
    """
    if len(scores) != len(labels):
        raise ValueError(f"scores and labels differ in length: {len(scores)} vs {len(labels)}")
    if any(label not in (0, 1) for label in labels):
        raise ValueError("labels must be 0 or 1")
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = average_ranks(scores)
    rank_sum_pos = sum(r for r, label in zip(ranks, labels, strict=True) if label == 1)
    u_pos = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return u_pos / (n_pos * n_neg)


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Spearman rank correlation with average ranks for ties.

    Returns ``None`` when fewer than 3 pairs are given or either series is constant.
    """
    if len(xs) != len(ys):
        raise ValueError(f"xs and ys differ in length: {len(xs)} vs {len(ys)}")
    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    rx = average_ranks(xs)
    ry = average_ranks(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    var_x = sum((a - mx) ** 2 for a in rx)
    var_y = sum((b - my) ** 2 for b in ry)
    return cov / math.sqrt(var_x * var_y)


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile of an already sorted, non-empty sequence."""
    position = q * (len(sorted_values) - 1)
    lo = math.floor(position)
    hi = math.ceil(position)
    weight = position - lo
    return sorted_values[lo] * (1.0 - weight) + sorted_values[hi] * weight


def bootstrap_ci(
    fn: MetricFn,
    xs: Sequence[float],
    ys: Sequence[float],
    n: int = 1000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile bootstrap interval of ``fn(xs, ys)`` over resampled index pairs.

    Index pairs are drawn with ``random.Random(seed)``; resamples on which *fn* returns
    ``None`` (for example a single-class draw) are skipped. Raises ``ValueError`` when
    fewer than 10 resamples were valid.
    """
    if len(xs) != len(ys):
        raise ValueError(f"xs and ys differ in length: {len(xs)} vs {len(ys)}")
    if len(xs) == 0:
        raise ValueError("cannot bootstrap an empty sample")
    rng = random.Random(seed)
    size = len(xs)
    values: list[float] = []
    for _ in range(n):
        idx = [rng.randrange(size) for _ in range(size)]
        value = fn([xs[i] for i in idx], [ys[i] for i in idx])
        if value is not None:
            values.append(value)
    if len(values) < 10:
        raise ValueError(f"only {len(values)} of {n} bootstrap resamples were valid (need 10)")
    values.sort()
    return _quantile(values, alpha / 2.0), _quantile(values, 1.0 - alpha / 2.0)


def median_baseline_mae(actuals: Sequence[float]) -> float:
    """Mean absolute error of always predicting the median of *actuals*."""
    if len(actuals) == 0:
        raise ValueError("median_baseline_mae needs at least one value")
    ordered = sorted(actuals)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 == 1 else (ordered[mid - 1] + ordered[mid]) / 2.0
    return sum(abs(a - median) for a in actuals) / len(actuals)
