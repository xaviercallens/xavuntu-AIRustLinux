"""Held-out pass@k evaluation the promotion gate can consume (card C-7, TODO item 2 / P4-5).

Why this exists
---------------
``scripts/night_training_workflow.py`` EVAL compares the first and last *training* loss; with a
handful of rows and 200 steps that falls by construction (LL.md §8). GATE therefore refused every
promotion with BLOCKED. This module is the missing half: an unbiased pass@k over a frozen
held-out set, a confidence interval that admits how few items there are, and a ``compare`` that
says *promote* only when the gain clears a margin and no tier regresses.

Pieces
------
* ``pass_at_k(n, c, k)`` -- the unbiased estimator of Chen et al. 2021 (Codex paper, eq. 1):
  ``1 - C(n-c, k) / C(n, k)`` with ``n`` samples of which ``c`` passed.
* ``wilson_interval(successes, n)`` -- Wilson score interval; ``successes`` may be fractional
  because the per-item pass@k is a probability (it is an exact 0/1 indicator when ``n == k``).
* ``score(verdicts, k)`` -- mean pass@k over items plus the Wilson interval on that mean; raises
  if any item has fewer than ``k`` samples (a silent partial estimate is how metrics lie).
* ``score_by_tier`` -- the same plus a per-tier breakdown; this is what ``compare`` consumes.
* ``compare(baseline, candidate, ...)`` -- ``{promote, reasons}``; every reason is a sentence.
* ``load_ladder_verdicts`` / ``build_heldout_baseline`` -- turn ``results/hardness/baseline.json``
  (greedy, so one sample per item) and, when present, ``results/hardness/retrieval_ab.json`` into
  verdict dicts keyed by item id with tier metadata. Only TRUE items count toward pass@k; a FALSE
  item that was accepted is a soundness failure and is reported separately.

Everything here is pure: no GPU, no network, no clock. File I/O is confined to the two loaders.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from math import comb
from pathlib import Path
from typing import Any

__all__ = [
    "LadderVerdicts",
    "build_heldout_baseline",
    "compare",
    "load_ladder_verdicts",
    "pass_at_k",
    "score",
    "score_by_tier",
    "wilson_interval",
]

Z_95 = 1.96


# ── estimators ────────────────────────────────────────────────────────────────
def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased pass@k for one item: ``n`` samples, ``c`` correct, ``k`` drawn without replacement."""
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    if n < k:
        raise ValueError(f"item has {n} sample(s) but k={k}")
    if not 0 <= c <= n:
        raise ValueError(f"c={c} must lie in [0, n={n}]")
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def wilson_interval(successes: float, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a proportion; ``successes`` may be fractional (mean of pass@k)."""
    if n < 1:
        raise ValueError("Wilson interval needs at least one trial")
    if not 0.0 <= successes <= n:
        raise ValueError(f"successes={successes} must lie in [0, n={n}]")
    p = successes / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return max(0.0, (centre - half) / denom), min(1.0, (centre + half) / denom)


def score(verdicts: dict[str, list[bool]], k: int) -> dict[str, Any]:
    """Mean pass@k over items with a Wilson interval. Raises if any item has < k samples."""
    if not verdicts:
        raise ValueError("no items to score")
    per_item: dict[str, float] = {}
    for item_id, samples in verdicts.items():
        try:
            per_item[item_id] = pass_at_k(len(samples), sum(bool(s) for s in samples), k)
        except ValueError as exc:
            raise ValueError(f"item {item_id!r}: {exc}") from exc
    n_items = len(per_item)
    total = sum(per_item.values())
    low, high = wilson_interval(total, n_items)
    return {
        "k": k,
        "pass_at_k": total / n_items,
        "n_items": n_items,
        "ci_low": low,
        "ci_high": high,
    }


def score_by_tier(
    verdicts: dict[str, list[bool]], tiers: dict[str, str], k: int
) -> dict[str, Any]:
    """``score`` overall plus ``tiers: {tier: score}``; every item must have a tier."""
    missing = sorted(set(verdicts) - set(tiers))
    if missing:
        raise ValueError(f"items without a tier: {missing}")
    overall = score(verdicts, k)
    by_tier: dict[str, dict[str, list[bool]]] = {}
    for item_id, samples in verdicts.items():
        by_tier.setdefault(tiers[item_id], {})[item_id] = samples
    overall["tiers"] = {t: score(v, k) for t, v in sorted(by_tier.items())}
    return overall


# ── promotion decision ────────────────────────────────────────────────────────
def compare(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    min_gain: float = 0.05,
    max_tier_regression: float = 0.02,
    min_items: int = 30,
) -> dict[str, Any]:
    """Decide promotion. Both inputs are ``score_by_tier`` outputs (or the same keys).

    Promote only if ALL hold: same k; the candidate covers at least ``min_items`` items; the
    candidate accepted no FALSE item (when either side reports ``false_accepted``); the overall
    gain is >= ``min_gain``; no tier present in the baseline is missing from the candidate or
    regresses by more than ``max_tier_regression``.
    """
    reasons: list[str] = []
    if baseline.get("k") != candidate.get("k"):
        reasons.append(f"k mismatch: baseline k={baseline.get('k')}, candidate k={candidate.get('k')}")
    n_items = int(candidate.get("n_items", 0))
    if n_items < min_items:
        reasons.append(f"candidate has {n_items} item(s), need >= {min_items} for a decision")
    false_accepted = int(candidate.get("false_accepted", 0))
    if false_accepted > 0:
        reasons.append(f"candidate accepted {false_accepted} FALSE item(s): unsound, never promotable")
    gain = float(candidate["pass_at_k"]) - float(baseline["pass_at_k"])
    if gain < min_gain:
        reasons.append(
            f"gain {gain:+.4f} below min_gain {min_gain:.4f} "
            f"(baseline {baseline['pass_at_k']:.4f}, candidate {candidate['pass_at_k']:.4f})"
        )
    base_tiers: dict[str, Any] = baseline.get("tiers", {})
    cand_tiers: dict[str, Any] = candidate.get("tiers", {})
    for tier in sorted(base_tiers):
        if tier not in cand_tiers:
            reasons.append(f"tier {tier} missing from candidate")
            continue
        delta = float(cand_tiers[tier]["pass_at_k"]) - float(base_tiers[tier]["pass_at_k"])
        if delta < -max_tier_regression:
            reasons.append(
                f"tier {tier} regressed {delta:+.4f} (limit -{max_tier_regression:.4f})"
            )
    return {
        "promote": not reasons,
        "gain": gain,
        "reasons": reasons or ["gain clears min_gain and no tier regresses"],
    }


# ── loaders: the frozen ladder as the math half of the held-out set ───────────
@dataclass
class LadderVerdicts:
    """Per-item verdicts for one (model, arm) with tier metadata; only TRUE items are scored."""

    model: str
    verdicts: dict[str, list[bool]] = field(default_factory=dict)
    tiers: dict[str, str] = field(default_factory=dict)
    false_n: int = 0
    false_accepted: int = 0
    unknown_truth: list[str] = field(default_factory=list)
    dropped_off_split: list[str] = field(default_factory=list)

    def add_run(self, run: dict[str, Any], frozen_ids: set[str] | None) -> None:
        item_id = str(run["id"])
        if frozen_ids is not None and item_id not in frozen_ids:
            self.dropped_off_split.append(item_id)
            return
        clean = bool(run.get("clean", False))
        truth = run.get("truth")
        if truth is None:  # e.g. the T4 BSD sentinel: an open problem is neither pass nor fail
            self.unknown_truth.append(item_id)
            return
        if not truth:
            self.false_n += 1
            self.false_accepted += int(clean)
            return
        self.verdicts.setdefault(item_id, []).append(clean)
        self.tiers[item_id] = str(run["tier"])

    def scored(self, k: int) -> dict[str, Any]:
        out = score_by_tier(self.verdicts, self.tiers, k)
        out.update(
            model=self.model,
            false_n=self.false_n,
            false_accepted=self.false_accepted,
            unknown_truth=sorted(set(self.unknown_truth)),
            dropped_off_split=sorted(self.dropped_off_split),
        )
        return out


def _runs_of(path: Path) -> list[dict[str, Any]]:
    doc = json.loads(path.read_text())
    runs = doc.get("runs") if isinstance(doc, dict) else None
    if not isinstance(runs, list):
        raise ValueError(f"{path}: expected a dict with a 'runs' list")
    return runs


def load_ladder_verdicts(
    baseline_path: Path,
    retrieval_ab_path: Path | None = None,
    frozen_split_path: Path | None = None,
) -> dict[str, LadderVerdicts]:
    """Group ladder runs into ``{arm_key: LadderVerdicts}``.

    ``baseline.json`` runs are keyed by model; ``retrieval_ab.json`` runs by ``model+premises``
    (the key card M-2 uses). One run record = one sample, so a greedy baseline yields n=1 per
    item. Items outside the frozen split are dropped and listed, never scored.
    """
    frozen_ids: set[str] | None = None
    if frozen_split_path is not None:
        frozen_ids = {str(f["id"]) for f in json.loads(frozen_split_path.read_text())}
    arms: dict[str, LadderVerdicts] = {}
    for run in _runs_of(baseline_path):
        key = str(run["model"])
        arms.setdefault(key, LadderVerdicts(model=key)).add_run(run, frozen_ids)
    if retrieval_ab_path is not None and retrieval_ab_path.exists():
        for run in _runs_of(retrieval_ab_path):
            key = f"{run['model']}+premises"
            arms.setdefault(key, LadderVerdicts(model=key)).add_run(run, frozen_ids)
    return arms


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_heldout_baseline(
    baseline_path: Path,
    retrieval_ab_path: Path | None,
    frozen_split_path: Path,
    k: int = 1,
) -> dict[str, Any]:
    """The JSON the GATE consumes: per-arm ``score_by_tier`` output plus provenance hashes."""
    arms = load_ladder_verdicts(baseline_path, retrieval_ab_path, frozen_split_path)
    sources = {"baseline": str(baseline_path), "frozen_split": str(frozen_split_path)}
    hashes = {"baseline": _sha256(baseline_path), "frozen_split": _sha256(frozen_split_path)}
    if retrieval_ab_path is not None and retrieval_ab_path.exists():
        sources["retrieval_ab"] = str(retrieval_ab_path)
        hashes["retrieval_ab"] = _sha256(retrieval_ab_path)
    scored: dict[str, Any] = {}
    skipped: dict[str, str] = {}
    for key, arm in arms.items():
        try:
            scored[key] = arm.scored(k)
        except ValueError as exc:  # e.g. an arm still in progress with < k samples
            skipped[key] = str(exc)
    return {
        "k": k,
        "n_frozen_items": len(json.loads(frozen_split_path.read_text())),
        "sources": sources,
        "sha256": hashes,
        "models": scored,
        "skipped": skipped,
    }
