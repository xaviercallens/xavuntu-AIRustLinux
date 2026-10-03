"""
JEPA Dataset — loads Phase 1 harvested traces into a PyTorch Dataset.

Lean 4 ref: Basic.lean §5
    structure Dataset (X Y : Type*) (n : ℕ) where
      inputs  : Fin n → X    -- hidden state embeddings h ∈ ℝ^d
      targets : Fin n → Y    -- actual energy scores ∈ [0, 100]

Sources:
  · Phase 1 Harvester JSONL (interactions.jsonl)
  · HiddenStateRecord.to_embedding() → list[float] of length d_model

Two kinds of training item are built from the traces:

  state item       (h, h, E(h))             one per valid trace; trains the energy head
  transition item  (h_t, h_{t+1}, E(h_{t+1}))  attempt t → attempt t+1 of the SAME task run;
                                            the only items on which the predictor has
                                            something other than identity to learn

The energy of an item is always the energy of its *target* state, and the world
model reads the energy head on the encoding of that same target state, so labels
and inputs stay aligned for both kinds of item.

Exact duplicate traces (same task, same iteration, byte-identical hidden state —
what a re-run of a seeded Phase 1 benchmark appends to the same file) carry no new
information. They are dropped and counted in ``skipped["duplicate"]`` so that state
counts, class counts and minimum-data guards cannot be inflated by replays.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import Dataset, Subset

logger = logging.getLogger("anse.jepa.dataset")

PAIR_MODES = ("mixed", "self", "transition")


class HiddenDimMismatchError(ValueError):
    """A hidden state does not have the dimension the dataset / model expects."""


@dataclass(frozen=True)
class StateSample:
    """One verified attempt: its embedding and the energy the sandbox gave it."""

    task: str
    run_id: int
    iteration: int
    hidden: torch.Tensor
    energy: float  # raw energy in [0, max_energy]
    code: str
    tests_total: int  # 0 when the trace carries no hidden-test verification


class JEPADataset(Dataset):
    """PyTorch Dataset for JEPA world model training.

    Each item is a tuple ``(h_context, h_target, energy_of_target)`` with the
    energy normalised to [0, 1].

    Lean 4 ref::

        structure Dataset (X Y : Type*) (n : ℕ) where
          inputs  : Fin n → X
          targets : Fin n → Y
    """

    def __init__(
        self,
        jsonl_path: Path | str | Sequence[Path | str],
        hidden_dim: int | None = None,
        normalise: bool = True,
        max_energy: float = 100.0,
        pair_mode: str = "mixed",
        verified_only: bool = False,
        deduplicate: bool = True,
    ) -> None:
        """Load traces from one or more Phase 1 JSONL logs.

        Args:
            jsonl_path: One path, or a sequence of paths, to harvester JSONL logs.
            hidden_dim: Expected hidden state dimension (Lean 4: d). ``None`` infers
                it from the first valid trace. A trace of any other dimension raises
                HiddenDimMismatchError: states are never padded or truncated.
            normalise: If True, L2-normalise hidden states.
            max_energy: Maximum energy value for normalisation (default: 100.0).
            pair_mode: "mixed" (state + transition items, default), "self" (state
                items only: the pre-evolution behaviour, kept for ablation) or
                "transition" (transition items only).
            verified_only: Keep only traces graded by hidden tests
                (``metadata.tests_total`` > 0).
            deduplicate: Drop a trace whose (task, iteration, hidden state) was already
                loaded, from any of the files, and count it in ``skipped["duplicate"]``.
        """
        if pair_mode not in PAIR_MODES:
            raise ValueError(f"pair_mode must be one of {PAIR_MODES}, got {pair_mode!r}")
        self.hidden_dim: int = hidden_dim or 0
        self.normalise = normalise
        self.max_energy = max_energy
        self.pair_mode = pair_mode
        self.verified_only = verified_only
        self.deduplicate = deduplicate
        self.states: list[StateSample] = []
        self.transitions: list[tuple[int, int]] = []
        self.skipped: dict[str, int] = {
            "malformed_json": 0,
            "empty_hidden_state": 0,
            "non_finite": 0,
            "unverified": 0,
            "duplicate": 0,
        }
        self._items: list[tuple[int, int]] = []
        self._seen: dict[
            tuple[str, int, str], int
        ] = {}  # (task, iteration, state hash) → state index
        self._next_run_id = 0

        paths = [jsonl_path] if isinstance(jsonl_path, (str, Path)) else list(jsonl_path)
        n_traces = 0
        for raw_path in paths:
            path = Path(raw_path)
            if not path.exists():
                logger.warning("JSONL file not found: %s — contributes no samples", path)
                continue
            traces = self._load_traces(path)
            n_traces += len(traces)
            self._build_pairs(traces)

        self.set_pair_mode(pair_mode)
        logger.info(
            "JEPADataset: %d states, %d transitions, %d items (%s) from %d traces; skipped=%s",
            len(self.states),
            len(self.transitions),
            len(self._items),
            pair_mode,
            n_traces,
            self.skipped,
        )

    # ── Loading ──────────────────────────────────────────────────────────────

    def _load_traces(self, path: Path) -> list[dict[str, Any]]:
        """Parse JSONL file into a list of trace dicts (file order is preserved)."""
        traces = []
        with open(path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    self.skipped["malformed_json"] += 1
                    logger.warning("Skipping malformed JSON at %s:%d", path, line_num)
                    continue
                if isinstance(obj, dict):
                    traces.append(obj)
                else:
                    self.skipped["malformed_json"] += 1
        return traces

    def _build_pairs(self, traces: list[dict[str, Any]]) -> None:
        """Turn traces into state samples and (attempt t → attempt t+1) transitions.

        Traces are read in file order. A trace extends the open run of its task when
        its iteration is exactly one more than that run's last valid attempt;
        anything else (iteration restarts, a gap left by a skipped trace) opens a
        new run. Different seeds of the same task are therefore never chained.

        An exact duplicate of an already loaded state (same task, iteration and
        hidden state) is not stored again. The chain is pointed at the existing
        state instead, so a replayed run adds nothing, while a replay that diverges
        later still links its first new attempt to the attempt it really followed.
        """
        open_runs: dict[str, int] = {}  # task → index in self.states of its last attempt
        for trace in traces:
            task = str(trace.get("task", "unknown"))
            sample = self._to_sample(trace, task)
            if sample is None:
                open_runs.pop(task, None)  # a hole breaks the chain
                continue

            key = (
                task,
                sample.iteration,
                hashlib.sha1(sample.hidden.numpy().tobytes()).hexdigest(),
            )
            if self.deduplicate and key in self._seen:
                self.skipped["duplicate"] += 1
                open_runs[task] = self._seen[key]
                continue

            prev_idx = open_runs.get(task)
            prev = self.states[prev_idx] if prev_idx is not None else None
            if prev is not None and sample.iteration == prev.iteration + 1:
                sample = replace(sample, run_id=prev.run_id)
            else:
                prev_idx = None
                self._next_run_id += 1
                sample = replace(sample, run_id=self._next_run_id)

            self.states.append(sample)
            idx = len(self.states) - 1
            self._seen.setdefault(key, idx)
            if prev_idx is not None:
                self.transitions.append((prev_idx, idx))
            open_runs[task] = idx

    def _to_sample(self, trace: dict[str, Any], task: str) -> StateSample | None:
        """Validate one trace; return None (and count why) if it is unusable."""
        metadata = trace.get("metadata") or {}
        tests_total = int(metadata.get("tests_total") or 0) if isinstance(metadata, dict) else 0
        if self.verified_only and tests_total <= 0:
            self.skipped["unverified"] += 1
            return None

        hs = trace.get("hidden_state")
        if hs is None or len(hs) == 0:
            self.skipped["empty_hidden_state"] += 1
            return None

        energy = trace.get("energy", self.max_energy)
        if not isinstance(energy, (int, float)) or not math.isfinite(energy):
            self.skipped["non_finite"] += 1
            return None

        hs_tensor = self._to_tensor(hs)
        if hs_tensor is None:
            return None

        return StateSample(
            task=task,
            run_id=0,  # assigned by _build_pairs
            iteration=int(trace.get("iteration", 0)),
            hidden=hs_tensor,
            energy=min(max(float(energy), 0.0), self.max_energy),
            code=str(trace.get("code", "")),
            tests_total=tests_total,
        )

    def _to_tensor(self, hs: list[float]) -> torch.Tensor | None:
        """Convert hidden state list to tensor with optional L2 normalisation.

        Lean 4 ref: HiddenState (d : ℕ) := EuclideanSpace ℝ (Fin d)

        Raises:
            HiddenDimMismatchError: the state is not ``hidden_dim`` long. Padding with
                zeros or truncating would silently train on a different input space.
        """
        try:
            t = torch.tensor(hs, dtype=torch.float32).flatten()
        except (TypeError, ValueError):
            self.skipped["non_finite"] += 1
            return None

        if not bool(torch.isfinite(t).all()):
            self.skipped["non_finite"] += 1
            return None

        if self.hidden_dim == 0:
            self.hidden_dim = int(t.shape[0])
            logger.info("JEPADataset: inferred hidden_dim=%d from data", self.hidden_dim)
        elif t.shape[0] != self.hidden_dim:
            raise HiddenDimMismatchError(
                f"hidden state has dimension {t.shape[0]} but the dataset expects "
                f"{self.hidden_dim}; refusing to pad or truncate. Pass the real embedding "
                f"dimension as hidden_dim (or hidden_dim=None to infer it from the data)."
            )

        if self.normalise:
            norm = t.norm(p=2)
            if norm > 0:
                t = t / norm

        return t

    # ── Items ────────────────────────────────────────────────────────────────

    def set_pair_mode(self, pair_mode: str) -> None:
        """Rebuild the item list for *pair_mode* without re-reading the traces."""
        if pair_mode not in PAIR_MODES:
            raise ValueError(f"pair_mode must be one of {PAIR_MODES}, got {pair_mode!r}")
        self.pair_mode = pair_mode
        self_items = [(i, i) for i in range(len(self.states))]
        if pair_mode == "self":
            self._items = self_items
        elif pair_mode == "transition":
            self._items = list(self.transitions)
        else:
            self._items = self_items + list(self.transitions)

    @property
    def item_tasks(self) -> list[str]:
        """Task of every item, aligned with dataset indices."""
        return [self.states[tgt].task for _, tgt in self._items]

    def is_transition(self, idx: int) -> bool:
        """True when item *idx* pairs two different attempts."""
        ctx, tgt = self._items[idx]
        return ctx != tgt

    def first_attempt_indices(self) -> list[int]:
        """State indices of first attempts: the states that open a run.

        A retry is conditioned on a failure (the loop only retries after one, and the
        retry response usually says so), so its embedding leaks its own label. First
        attempts are the only states on which pass/fail prediction is a fair test,
        and there is one per task run, so they are also the independent sample.
        """
        targets = {tgt for _, tgt in self.transitions}
        return [i for i, s in enumerate(self.states) if i not in targets and s.iteration <= 1]

    def distinct_embedding_count(self) -> int:
        """Number of distinct (task, hidden state) pairs among the loaded states."""
        return len({(task, digest) for task, _, digest in self._seen})

    def indices_for_tasks(self, tasks: set[str]) -> list[int]:
        """Dataset indices of every item whose task is in *tasks*."""
        return [i for i, task in enumerate(self.item_tasks) if task in tasks]

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        ctx, tgt = self._items[idx]
        target = self.states[tgt]
        energy_norm = min(target.energy / self.max_energy, 1.0)
        return (
            self.states[ctx].hidden,
            target.hidden.clone() if ctx == tgt else target.hidden,
            torch.tensor(energy_norm, dtype=torch.float32),
        )


def task_kfold(tasks: Sequence[str], k: int, seed: int) -> list[set[str]]:
    """Partition the distinct *tasks* into k disjoint validation folds.

    The shuffle depends only on the sorted task names and the seed, so folds are
    reproducible regardless of trace order.
    """
    unique = sorted(set(tasks))
    if k < 2:
        raise ValueError(f"k must be >= 2, got {k}")
    if len(unique) < k:
        raise ValueError(f"cannot build {k} task folds from {len(unique)} distinct tasks")
    perm = torch.randperm(len(unique), generator=torch.Generator().manual_seed(seed)).tolist()
    folds: list[set[str]] = [set() for _ in range(k)]
    for position, task_idx in enumerate(perm):
        folds[position % k].add(unique[task_idx])
    return folds


def train_val_split(
    dataset: JEPADataset,
    val_fraction: float = 0.2,
    seed: int = 42,
) -> tuple[Subset, Subset]:
    """Split dataset into training and validation sets BY TASK.

    Every item of a task lands on the same side, so validation measures
    generalisation to unseen tasks rather than recall of a task seen in training.

    Args:
        dataset: Full JEPADataset.
        val_fraction: Fraction of *tasks* held out for validation (default: 0.2).
        seed: Random seed for reproducibility.

    Returns:
        (train_dataset, val_dataset) tuple.
    """
    item_tasks = dataset.item_tasks
    unique = sorted(set(item_tasks))
    generator = torch.Generator().manual_seed(seed)

    if len(unique) < 2:
        # One task cannot be split by task; an item-level split is the only option.
        logger.warning(
            "train_val_split: only %d distinct task(s) — falling back to an item-level "
            "split, validation is NOT task-independent",
            len(unique),
        )
        n_total = len(dataset)
        n_val = max(1, int(n_total * val_fraction))
        perm = torch.randperm(n_total, generator=generator).tolist()
        return Subset(dataset, sorted(perm[n_val:])), Subset(dataset, sorted(perm[:n_val]))

    n_val_tasks = min(len(unique) - 1, max(1, round(len(unique) * val_fraction)))
    perm = torch.randperm(len(unique), generator=generator).tolist()
    val_tasks = {unique[i] for i in perm[:n_val_tasks]}
    val_idx = [i for i, task in enumerate(item_tasks) if task in val_tasks]
    train_idx = [i for i, task in enumerate(item_tasks) if task not in val_tasks]
    return Subset(dataset, train_idx), Subset(dataset, val_idx)
