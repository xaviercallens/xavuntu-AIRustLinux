"""Route a (domain, hardness tier) to the models that have EARNED it.

Why this exists (LL.md §4c, docs/v2/IMPLEMENTATION_PLAN_2026-09-28.md §1): on this T4 the
7-9B models are competent executors and poor discoverers. The hardness ladder measured
DeepSeek-Prover-V2-7B at 6/10 and Goedel-Prover-V2-8B at 8/10 on tier T0 and both at 0/12
on T1-T3, with zero false items accepted; the cosmology run needed the top model tier for
Lean and for the adversarial referee while the default tier handled fits and papers. A
router that hard-codes "small model first" repeats the 0/12 forty-eight more times; one
that hard-codes "big model always" wastes the tiers the small models already own.

So routing is data-driven and sound-first:

* A **capability matrix** holds, per (domain, tier, model), the measured attempts, passes
  and false-item acceptances, each with the file it came from. Unmeasured cells are
  ``None``, never a guess.
* ``route`` orders candidates by the **Wilson lower bound** of their pass rate (so a 1/1
  never outranks an 8/10), **excludes any model that accepted a false item at that tier**
  (soundness before fluency: an unsound prover is worse than no prover), allows at most
  one unmeasured model as an exploration slot, and appends an escalation to the next
  tier (``top-tier`` or ``human``) when the best measured lower bound is below the
  budget's threshold.
* ``record_outcome`` feeds verdicts back, so every ladder run, retrieval arm or nightly
  eval tightens the matrix. The verdicts must come from a verifier (kernel, sandbox,
  reference oracle) - the matrix has no cell for "the model said it passed".

Everything here is pure: no I/O, no clock, no randomness. ``scripts/hardness/
capability_matrix.py`` is the glue that builds the matrix from the real result files.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

ESCALATE_TOP_TIER = "escalate:top-tier"
ESCALATE_HUMAN = "escalate:human"


@dataclass(frozen=True)
class Cell:
    """Measured evidence for one (domain, tier, model)."""

    attempts: int
    passes: int
    false_items: int = 0  # false/negative-control items the model was shown
    false_accepted: int = 0  # ... and how many it "proved" (must be 0 to be sound)
    source: str = ""  # file the numbers came from

    def __post_init__(self) -> None:
        if self.attempts < 0 or self.passes < 0 or self.false_items < 0 or self.false_accepted < 0:
            raise ValueError("counts must be non-negative")
        if self.passes > self.attempts:
            raise ValueError(f"passes ({self.passes}) exceed attempts ({self.attempts})")
        if self.false_accepted > self.false_items:
            raise ValueError("false_accepted exceeds false_items")

    @property
    def pass_rate(self) -> float | None:
        return None if self.attempts == 0 else self.passes / self.attempts

    @property
    def sound(self) -> bool:
        """No false item was ever accepted. Unmeasured soundness counts as sound-so-far."""
        return self.false_accepted == 0

    def wilson_low(self, z: float = 1.96) -> float | None:
        """Lower bound of the Wilson score interval for the pass rate (None if unmeasured)."""
        n = self.attempts
        if n == 0:
            return None
        p = self.passes / n
        denom = 1.0 + z * z / n
        centre = p + z * z / (2 * n)
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
        return max(0.0, (centre - half) / denom)

    def merged(self, other: Cell) -> Cell:
        return Cell(
            attempts=self.attempts + other.attempts,
            passes=self.passes + other.passes,
            false_items=self.false_items + other.false_items,
            false_accepted=self.false_accepted + other.false_accepted,
            source=self.source if self.source == other.source else f"{self.source}+{other.source}",
        )


@dataclass
class CapabilityMatrix:
    cells: dict[tuple[str, str, str], Cell] = field(default_factory=dict)

    def get(self, domain: str, tier: str, model: str) -> Cell | None:
        return self.cells.get((domain, tier, model))

    def set(self, domain: str, tier: str, model: str, cell: Cell) -> None:
        self.cells[(domain, tier, model)] = cell

    def models(self, domain: str, tier: str) -> list[str]:
        return sorted(m for (d, t, m) in self.cells if d == domain and t == tier)

    def to_dict(self) -> dict:
        return {
            f"{d}|{t}|{m}": {
                "attempts": c.attempts,
                "passes": c.passes,
                "false_items": c.false_items,
                "false_accepted": c.false_accepted,
                "pass_rate": c.pass_rate,
                "wilson_low": c.wilson_low(),
                "sound": c.sound,
                "source": c.source,
            }
            for (d, t, m), c in sorted(self.cells.items())
        }

    @classmethod
    def from_dict(cls, data: dict) -> CapabilityMatrix:
        mx = cls()
        for key, v in data.items():
            d, t, m = key.split("|")
            mx.set(d, t, m, Cell(v["attempts"], v["passes"], v.get("false_items", 0),
                                 v.get("false_accepted", 0), v.get("source", "")))
        return mx


@dataclass(frozen=True)
class Budget:
    """How much a caller may spend before escalating."""

    max_candidates: int = 3
    min_wilson_low: float = 0.5  # below this the local tier is not trusted alone
    allow_exploration: bool = True  # one unmeasured model may be tried
    next_tier: str = ESCALATE_TOP_TIER

    def __post_init__(self) -> None:
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be >= 1")
        if not 0.0 <= self.min_wilson_low <= 1.0:
            raise ValueError("min_wilson_low must be in [0, 1]")


@dataclass(frozen=True)
class Candidate:
    model: str
    reason: str  # "measured wilson_low=0.44 (6/10)" | "exploration: unmeasured" | "escalation"
    wilson_low: float | None


@dataclass(frozen=True)
class Plan:
    domain: str
    tier: str
    candidates: tuple[Candidate, ...]
    excluded_unsound: tuple[str, ...]

    @property
    def escalates(self) -> bool:
        return any(c.model.startswith("escalate:") for c in self.candidates)


def route(
    domain: str,
    tier: str,
    matrix: CapabilityMatrix,
    available: list[str],
    budget: Budget = Budget(),
) -> Plan:
    """Order the available models for (domain, tier); deterministic for equal inputs."""
    if not available:
        raise ValueError("no models available")
    measured: list[tuple[float, int, str]] = []  # (-wilson_low, -attempts, name) for sorting
    unmeasured: list[str] = []
    unsound: list[str] = []
    for model in sorted(set(available)):
        cell = matrix.get(domain, tier, model)
        if cell is None or cell.attempts == 0:
            if cell is not None and not cell.sound:
                unsound.append(model)
            else:
                unmeasured.append(model)
            continue
        if not cell.sound:
            unsound.append(model)
            continue
        wl = cell.wilson_low()
        assert wl is not None
        measured.append((-wl, -cell.attempts, model))
    measured.sort()

    cands: list[Candidate] = []
    for neg_wl, neg_n, model in measured:
        cell = matrix.get(domain, tier, model)
        assert cell is not None
        cands.append(Candidate(model, f"measured wilson_low={-neg_wl:.2f} ({cell.passes}/{cell.attempts})", -neg_wl))
    if budget.allow_exploration and unmeasured:
        cands.append(Candidate(unmeasured[0], "exploration: unmeasured", None))
    cands = cands[: budget.max_candidates]

    best = max((c.wilson_low for c in cands if c.wilson_low is not None), default=None)
    if best is None or best < budget.min_wilson_low:
        why = "no measured model" if best is None else f"best wilson_low={best:.2f} < {budget.min_wilson_low:.2f}"
        cands.append(Candidate(budget.next_tier, f"escalation: {why}", None))
    return Plan(domain, tier, tuple(cands), tuple(unsound))


def record_outcome(
    matrix: CapabilityMatrix,
    domain: str,
    tier: str,
    model: str,
    *,
    passed: bool,
    truth: bool | None,
    source: str,
) -> CapabilityMatrix:
    """Return a new matrix with one verifier-issued verdict folded in.

    ``truth`` is the item's ground truth: True items count toward the pass rate; False
    items (negative controls) count toward soundness, where ``passed`` means the model was
    credited with proving a falsehood. ``truth=None`` (unknown, e.g. the BSD sentinel)
    is recorded as an attempt only if it failed - an accepted proof of an unknown
    statement is not evidence either way and is left out.
    """
    if truth is True:
        delta = Cell(1, int(passed), source=source)
    elif truth is False:
        delta = Cell(0, 0, false_items=1, false_accepted=int(passed), source=source)
    else:
        if passed:
            return matrix
        delta = Cell(1, 0, source=source)
    old = matrix.get(domain, tier, model)
    new = delta if old is None else old.merged(delta)
    out = CapabilityMatrix(dict(matrix.cells))
    out.set(domain, tier, model, new)
    return out


def summarize(matrix: CapabilityMatrix, domain: str, tiers: list[str], models: list[str]) -> list[dict]:
    """Rows for a report table: one per tier, the best sound measured model and its bound."""
    rows: list[dict] = []
    for tier in tiers:
        plan = route(domain, tier, matrix, models, Budget(max_candidates=len(models) + 1))
        best = next((c for c in plan.candidates if c.wilson_low is not None), None)
        rows.append({
            "tier": tier,
            "best_model": best.model if best else None,
            "best_wilson_low": best.wilson_low if best else None,
            "escalates": plan.escalates,
            "excluded_unsound": list(plan.excluded_unsound),
        })
    return rows


def with_budget(budget: Budget, **changes) -> Budget:
    """Small helper so callers do not import dataclasses.replace."""
    return replace(budget, **changes)
