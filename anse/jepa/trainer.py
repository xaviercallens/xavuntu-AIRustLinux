"""
JEPA Trainer — training loop for the JEPA World Model.

Lean 4 ref: jepTrainingLoss = energy_loss + vicreg_loss
            jepTrainingLoss_nonneg ✅ proved
            mseJEPA_monotone_descent ✅ proved (loss ≥ 0)

Algorithm per step:
  1. Sample batch (h_ctx, h_tgt, energy_actual) from JEPADataset
  2. Forward through JEPAWorldModel → compute_training_loss
  3. Backprop through ContextEncoder + Predictor + EnergyHead
  4. EMA update TargetEncoder
  5. Log metrics + checkpoint best model
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset, Subset

from anse.config import JEPAConfig
from anse.jepa.dataset import JEPADataset, train_val_split
from anse.jepa.ema import cosine_ema_schedule, ema_update
from anse.jepa.world_model import JEPAWorldModel
from anse.v2.label_control import control_report, shuffled_copy
from anse.v2.metrics import auroc, spearman

logger = logging.getLogger("anse.jepa.trainer")

LABEL_CONTROL_KEYS = ["energy_accuracy", "val_loss", "auroc", "spearman"]


@dataclass
class TrainingSummary:
    """Summary of a JEPA training run."""

    epochs_completed: int = 0
    best_val_loss: float = float("inf")
    final_train_loss: float = float("inf")
    final_val_loss: float = float("inf")
    total_steps: int = 0
    training_time_seconds: float = 0.0
    checkpoint_path: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


def shuffled_label_dataset(dataset: JEPADataset, seed: int) -> JEPADataset:
    """A shallow copy of *dataset* whose state energies are permuted across states.

    Items, transitions and the task split are untouched, so the control trains on
    exactly the same inputs and the same held-out tasks as the real run; only the
    labels no longer belong to their rows.
    """
    permuted = shuffled_copy([{"energy": s.energy} for s in dataset.states], seed)
    clone = copy.copy(dataset)
    clone.states = [
        replace(state, energy=row["energy"])
        for state, row in zip(dataset.states, permuted, strict=True)
    ]
    return clone


@dataclass
class ValidationMetrics:
    """Validation metrics for the JEPA world model."""

    val_loss: float
    prediction_loss: float
    vicreg_loss: float
    energy_head_loss: float
    energy_prediction_accuracy: float  # Fraction within threshold


class JEPATrainer:
    """Training loop for the JEPA World Model.

    Lean 4 ref: jepTrainingLoss = energy_loss + vicreg_loss
                jepTrainingLoss_nonneg ✅ proved

    The trainer:
    1. Runs the forward pass through JEPAWorldModel.compute_training_loss()
    2. Backpropagates through ContextEncoder + Predictor + EnergyHead
    3. Updates TargetEncoder via EMA (no gradients)
    4. Logs metrics and checkpoints the best model

    Note: TargetEncoder is excluded from the optimiser —
    it is updated only via EMA.
    """

    def __init__(
        self,
        model: JEPAWorldModel,
        config: JEPAConfig | None = None,
        lr: float = 3e-4,
        weight_decay: float = 0.01,
        tau_start: float = 0.996,
        tau_end: float = 1.0,
        checkpoint_dir: Path | str | None = None,
        device: str = "cpu",
    ):
        self.model = model
        self.config = config or JEPAConfig()
        self.lr = lr
        self.weight_decay = weight_decay
        self.tau_start = tau_start
        self.tau_end = tau_end
        self.device = device
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else Path("checkpoints")

        # Move model to device
        self.model = self.model.to(self.device)

        # Build optimiser — exclude TargetEncoder (EMA only)
        trainable_params = []
        for name, param in self.model.named_parameters():
            if "tgt_encoder" not in name and param.requires_grad:
                trainable_params.append(param)

        self.optimizer = torch.optim.AdamW(
            trainable_params,
            lr=self.lr,
            weight_decay=self.weight_decay,
        )

    def _train_epoch(
        self,
        train_loader: DataLoader,
        global_step: int,
        total_steps: int,
    ) -> tuple[dict[str, float], int]:
        self.model.train()
        epoch_metrics: dict[str, float] = {
            "prediction_loss": 0.0,
            "vicreg_loss": 0.0,
            "energy_head_loss": 0.0,
            "total_loss": 0.0,
        }
        n_batches = 0

        for h_ctx, h_tgt, energy_actual in train_loader:
            h_ctx = h_ctx.to(self.device)
            h_tgt = h_tgt.to(self.device)
            energy_actual = energy_actual.to(self.device)

            # Forward
            loss, metrics = self.model.compute_training_loss(h_ctx, h_tgt, energy_actual)

            # Backward
            self.optimizer.zero_grad()
            loss.backward()
            # Gradient clipping for stability
            nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()

            # EMA update target encoder
            tau = cosine_ema_schedule(global_step, total_steps, self.tau_start, self.tau_end)
            ema_update(
                self.model.tgt_encoder,  # type: ignore
                self.model.ctx_encoder,  # type: ignore
                tau,
            )

            global_step += 1
            n_batches += 1
            for k, v in metrics.items():
                if k in epoch_metrics:
                    epoch_metrics[k] += v

        # Average epoch metrics
        for k in epoch_metrics:
            epoch_metrics[k] /= max(n_batches, 1)

        return epoch_metrics, global_step

    def train(
        self,
        dataset: JEPADataset,
        epochs: int = 100,
        batch_size: int = 32,
        val_fraction: float = 0.2,
        seed: int = 42,
        energy_accuracy_threshold: float = 0.1,
        label_control_seed: int | None = None,
    ) -> TrainingSummary:
        """Run the full training loop.

        Args:
            dataset: JEPADataset with Phase 1 traces.
            epochs: Number of training epochs.
            batch_size: Mini-batch size.
            val_fraction: Fraction of data for validation.
            seed: Random seed for reproducibility.
            energy_accuracy_threshold: Threshold for energy prediction accuracy.
            label_control_seed: When set, a second fit from the same initial weights
                on ``shuffled_label_dataset(dataset, label_control_seed)`` is run and
                ``history[-1]['label_control']`` carries the real-vs-shuffled
                comparison (card V0-8). The returned trainer state and checkpoint are
                those of the real fit. ``None`` leaves the behaviour unchanged.

        Returns:
            TrainingSummary with metrics and checkpoint path.
        """
        if len(dataset) == 0:
            logger.warning("Dataset is empty — skipping training")
            return TrainingSummary()

        # Split into train / validation (by task: see train_val_split)
        train_ds: Dataset
        val_ds: Dataset
        if len(dataset) < 3:
            # Too few samples for a meaningful split — use all for both
            logger.warning(
                "Dataset too small (%d samples) for train/val split — using full dataset for both",
                len(dataset),
            )
            train_ds = dataset
            val_ds = dataset
        else:
            train_ds, val_ds = train_val_split(dataset, val_fraction, seed)

        if label_control_seed is None:
            return self.fit(
                train_ds,
                val_ds,
                epochs=epochs,
                batch_size=batch_size,
                seed=seed,
                energy_accuracy_threshold=energy_accuracy_threshold,
            )
        return self._fit_with_label_control(
            dataset,
            train_ds,
            val_ds,
            epochs=epochs,
            batch_size=batch_size,
            seed=seed,
            energy_accuracy_threshold=energy_accuracy_threshold,
            label_control_seed=label_control_seed,
        )

    def _fit_with_label_control(
        self,
        dataset: JEPADataset,
        train_ds: Dataset,
        val_ds: Dataset,
        epochs: int,
        batch_size: int,
        seed: int,
        energy_accuracy_threshold: float,
        label_control_seed: int,
    ) -> TrainingSummary:
        """Real fit, then a shuffled-label fit from the same initial weights (V0-8).

        The control never checkpoints and never leaks into the returned model: the
        real weights and optimiser state are restored before returning.
        """
        initial_model = copy.deepcopy(self.model.state_dict())
        initial_optimizer = copy.deepcopy(self.optimizer.state_dict())

        summary = self.fit(
            train_ds,
            val_ds,
            epochs=epochs,
            batch_size=batch_size,
            seed=seed,
            energy_accuracy_threshold=energy_accuracy_threshold,
        )
        real_metrics = self._arm_metrics(summary, val_ds, batch_size)
        real_model = copy.deepcopy(self.model.state_dict())
        real_optimizer = copy.deepcopy(self.optimizer.state_dict())

        shuffled = shuffled_label_dataset(dataset, label_control_seed)
        shuffled_train: Dataset = (
            Subset(shuffled, train_ds.indices) if isinstance(train_ds, Subset) else shuffled
        )
        shuffled_val: Dataset = (
            Subset(shuffled, val_ds.indices) if isinstance(val_ds, Subset) else shuffled
        )
        self.model.load_state_dict(initial_model)
        self.optimizer.load_state_dict(initial_optimizer)
        control_summary = self.fit(
            shuffled_train,
            shuffled_val,
            epochs=epochs,
            batch_size=batch_size,
            seed=seed,
            energy_accuracy_threshold=energy_accuracy_threshold,
            select_best_on_val=False,
        )
        shuffled_metrics = self._arm_metrics(control_summary, shuffled_val, batch_size)

        self.model.load_state_dict(real_model)
        self.optimizer.load_state_dict(real_optimizer)

        report = control_report(real_metrics, shuffled_metrics, LABEL_CONTROL_KEYS)
        report["seed"] = label_control_seed
        report["val_items"] = len(val_ds)  # type: ignore[arg-type]
        report["val_positives"] = sum(1 for e in real_metrics["actuals"] if e > 0.0)
        summary.history[-1]["label_control"] = report
        return summary

    def _arm_metrics(self, summary: TrainingSummary, val_ds: Dataset, batch_size: int) -> dict[str, Any]:
        """Metrics of one arm (real or shuffled) on its validation items.

        ``auroc`` scores the energy head as a detector of non-zero energy (any
        failure); ``spearman`` is its rank agreement with the graded energy. Both are
        ``None`` when undefined (one class, constant predictions, < 3 items).
        """
        predictions, actuals = self._energy_predictions(DataLoader(val_ds, batch_size=batch_size))
        labels = [1 if e > 0.0 else 0 for e in actuals]
        return {
            "energy_accuracy": summary.history[-1]["energy_accuracy"],
            "val_loss": summary.final_val_loss,
            "auroc": auroc(predictions, labels),
            "spearman": spearman(predictions, actuals),
            "actuals": actuals,
        }

    @torch.no_grad()
    def _energy_predictions(self, loader: DataLoader) -> tuple[list[float], list[float]]:
        """Energy-head predictions and actual energies, aligned, for every item of *loader*."""
        self.model.eval()
        predictions: list[float] = []
        actuals: list[float] = []
        for h_ctx, _h_tgt, energy_actual in loader:
            z_ctx = self.model.ctx_encoder(self.model.prepare_input(h_ctx.to(self.device), "h_context"))  # type: ignore
            energy_pred = self.model.energy_head(z_ctx)  # type: ignore
            predictions.extend(float(v) for v in energy_pred.flatten().tolist())
            actuals.extend(float(v) for v in energy_actual.flatten().tolist())
        return predictions, actuals

    def fit(
        self,
        train_ds: Dataset,
        val_ds: Dataset,
        epochs: int = 100,
        batch_size: int = 32,
        seed: int = 42,
        energy_accuracy_threshold: float = 0.1,
        select_best_on_val: bool = True,
        validate_every: int = 1,
    ) -> TrainingSummary:
        """Train on an explicit (train, validation) pair of datasets.

        Args:
            train_ds: Items to optimise on.
            val_ds: Items to monitor.
            epochs: Number of training epochs.
            batch_size: Mini-batch size.
            seed: Seed of the shuffling order.
            energy_accuracy_threshold: Threshold for energy prediction accuracy.
            select_best_on_val: Checkpoint the epoch with the lowest validation loss.
                Pass False when ``val_ds`` is the held-out set of an experiment:
                selecting an epoch on it would leak the test labels into the model.
            validate_every: Validate every N epochs (the last epoch is always
                validated). Skipped epochs repeat the previous validation metrics.

        Returns:
            TrainingSummary with metrics and checkpoint path.
        """
        if len(train_ds) == 0:  # type: ignore[arg-type]
            logger.warning("Training split is empty — skipping training")
            return TrainingSummary()
        if validate_every < 1:
            raise ValueError(f"validate_every must be >= 1, got {validate_every}")

        train_loader = DataLoader(
            train_ds,
            batch_size=batch_size,
            shuffle=True,
            generator=torch.Generator().manual_seed(seed),
            # A trailing batch of one sample has undefined variance: VICReg returns NaN
            # and a single backward pass poisons every weight.
            drop_last=len(train_ds) > batch_size and len(train_ds) % batch_size == 1,
        )
        val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

        total_steps = epochs * len(train_loader)
        summary = TrainingSummary()
        global_step = 0
        best_val_loss = float("inf")
        start_time = time.time()

        # We need epoch_metrics in scope for the final summary assignment,
        # so initialize it to a default.
        epoch_metrics: dict[str, float] = {"total_loss": 0.0}

        logger.info(
            "Starting JEPA training: %d epochs, %d train / %d val samples, %d total steps",
            epochs,
            len(train_ds),  # type: ignore[arg-type]
            len(val_ds),  # type: ignore[arg-type]
            total_steps,
        )

        for epoch in range(1, epochs + 1):
            epoch_metrics, global_step = self._train_epoch(train_loader, global_step, total_steps)

            # ── Validation phase ────────────────────────────────────
            if epoch == 1 or epoch == epochs or epoch % validate_every == 0:
                val_metrics = self.validate(val_loader, energy_accuracy_threshold)

            epoch_record = {
                "epoch": epoch,
                "train_loss": epoch_metrics["total_loss"],
                "val_loss": val_metrics.val_loss,
                "energy_accuracy": val_metrics.energy_prediction_accuracy,
                **epoch_metrics,
            }
            summary.history.append(epoch_record)

            # Checkpoint best model
            improved = val_metrics.val_loss < best_val_loss
            if improved:
                best_val_loss = val_metrics.val_loss
            if improved and select_best_on_val:
                ckpt_path = self.checkpoint_dir / "jepa_best.pt"
                self.model.save(ckpt_path)
                summary.checkpoint_path = str(ckpt_path)

            if epoch % 10 == 0 or epoch == 1:
                logger.info(
                    "Epoch %d/%d | Train Loss: %.4f | Val Loss: %.4f | Energy Acc: %.1f%%",
                    epoch,
                    epochs,
                    epoch_metrics["total_loss"],
                    val_metrics.val_loss,
                    val_metrics.energy_prediction_accuracy * 100,
                )

        summary.epochs_completed = epochs
        summary.best_val_loss = best_val_loss
        summary.final_train_loss = epoch_metrics["total_loss"]
        summary.final_val_loss = val_metrics.val_loss
        summary.total_steps = global_step
        summary.training_time_seconds = time.time() - start_time

        logger.info(
            "Training complete: %d epochs, %.1fs, best val loss: %.4f",
            epochs,
            summary.training_time_seconds,
            summary.best_val_loss,
        )

        return summary

    @torch.no_grad()
    def validate(
        self,
        val_loader: DataLoader,
        energy_accuracy_threshold: float = 0.1,
    ) -> ValidationMetrics:
        """Validate the model on held-out data.

        Args:
            val_loader: DataLoader for validation set.
            energy_accuracy_threshold: Max |predicted − actual| for "correct".

        Returns:
            ValidationMetrics with loss components and prediction accuracy.
        """
        self.model.eval()

        total_loss = 0.0
        total_pred_loss = 0.0
        total_vicreg_loss = 0.0
        total_energy_loss = 0.0
        n_correct = 0
        n_total = 0
        n_batches = 0

        for h_ctx, h_tgt, energy_actual in val_loader:
            h_ctx = h_ctx.to(self.device)
            h_tgt = h_tgt.to(self.device)
            energy_actual = energy_actual.to(self.device)

            loss, metrics = self.model.compute_training_loss(h_ctx, h_tgt, energy_actual)

            total_loss += loss.item()
            total_pred_loss += metrics["prediction_loss"]
            total_vicreg_loss += metrics["vicreg_loss"]
            total_energy_loss += metrics["energy_head_loss"]
            n_batches += 1

            # Energy prediction accuracy
            z_ctx = self.model.ctx_encoder(self.model.prepare_input(h_ctx, "h_context"))  # type: ignore
            energy_pred = self.model.energy_head(z_ctx)  # type: ignore
            diff = (energy_pred - energy_actual).abs()
            n_correct += (diff < energy_accuracy_threshold).sum().item()
            n_total += h_ctx.shape[0]

        n_batches = max(n_batches, 1)
        n_total = max(n_total, 1)

        return ValidationMetrics(
            val_loss=total_loss / n_batches,
            prediction_loss=total_pred_loss / n_batches,
            vicreg_loss=total_vicreg_loss / n_batches,
            energy_head_loss=total_energy_loss / n_batches,
            energy_prediction_accuracy=n_correct / n_total,
        )
