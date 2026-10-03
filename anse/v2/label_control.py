"""Shuffled-label control for trainer reports (card V0-8).

A model trained on labels permuted across rows can learn nothing about the labels.
Whatever metric it still reaches is the floor of that metric on this data; a real
run is only evidence of learning by the margin it clears above that floor. The
cosmo3 retrofit showed ``energy_accuracy`` = 1.00 on both arms, so every trainer
report now carries the control next to the real number and flags metrics that do
not move as SATURATED.

Randomness is injected (``seed``) so the control is reproducible and hermetic.
"""

from __future__ import annotations

import random
from typing import Any

SATURATED = "SATURATED"
INFORMATIVE = "INFORMATIVE"
UNDEFINED = "UNDEFINED"


def shuffled_copy(rows: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    """Return copies of *rows* with their ``energy`` values permuted across rows.

    The permutation is drawn with ``random.Random(seed)``; the input list and its
    dicts are left untouched and the output has the same length and row order.
    Raises ``ValueError`` on an empty list (a permutation of nothing is not a control).
    """
    if not rows:
        raise ValueError("shuffled_copy needs at least one row")
    energies = [row["energy"] for row in rows]
    random.Random(seed).shuffle(energies)
    return [dict(row, energy=energy) for row, energy in zip(rows, energies, strict=True)]


def control_report(
    real: dict[str, Any],
    shuffled: dict[str, Any],
    metric_keys: list[str],
) -> dict[str, Any]:
    """Compare the real and the shuffled-label metrics, key by key.

    Each key maps to ``{'real', 'shuffled', 'delta', 'informative', 'status'}``.
    ``informative`` is ``abs(delta) > 0``; a metric equal on both arms is flagged
    ``SATURATED`` because it cannot distinguish learning from noise on this data. A
    metric that is ``None`` on either arm (undefined, e.g. AUROC with one class) has
    ``delta`` ``None`` and status ``UNDEFINED``. The top-level ``saturated`` list names
    the flagged keys so a report can be rejected at a glance.
    """
    report: dict[str, Any] = {}
    saturated: list[str] = []
    for key in metric_keys:
        real_value = real.get(key)
        shuffled_value = shuffled.get(key)
        if real_value is None or shuffled_value is None:
            entry = {
                "real": real_value,
                "shuffled": shuffled_value,
                "delta": None,
                "informative": False,
                "status": UNDEFINED,
            }
        else:
            delta = float(real_value) - float(shuffled_value)
            informative = abs(delta) > 0
            entry = {
                "real": real_value,
                "shuffled": shuffled_value,
                "delta": delta,
                "informative": informative,
                "status": INFORMATIVE if informative else SATURATED,
            }
            if not informative:
                saturated.append(key)
        report[key] = entry
    report["saturated"] = saturated
    return report
