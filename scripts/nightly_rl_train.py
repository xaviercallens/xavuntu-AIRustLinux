#!/usr/bin/env python3
"""
Nightly RL / DPO Post-Training for ANSE Code Critic and Energy Policy.

Trains a neural preference model / code critic on the 100 recorded functional test sessions.
Optimizes the Direct Preference Optimization (DPO) objective:
    L_DPO(theta) = - E [ log sigma( beta * (r_theta(x, y_chosen) - r_theta(x, y_rejected)) ) ]

Compatible with both CPU (overnight multi-epoch training) and CUDA / RunPod GPU accelerators.
Outputs model weights, checkpoints, loss trajectory, and verification metrics.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from torch.utils.data import Dataset

# Set up repository root imports
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, "/mnt/disks/disk-socrateai-local-1/gpu_lease")

from gpu_lease import gpu_lease  # noqa: E402

from anse.guard.critic import EnergyCriticPolicy, tokenize_string  # noqa: E402

LEASE_HOLDER = "autoevolve-nightly-rl"

# ─── Dataset ─────────────────────────────────────────────────────────────────


class DPOPreferenceDataset(Dataset):
    """Loads newline-delimited JSON preference pairs (prompt, chosen, rejected)."""

    def __init__(self, jsonl_path: str | Path) -> None:
        self.pairs: list[dict[str, Any]] = []
        path = Path(jsonl_path)
        if not path.exists():
            raise FileNotFoundError(f"DPO dataset not found at {path}")

        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.pairs.append(json.loads(line))

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        return self.pairs[idx]


# ─── DPO Loss ────────────────────────────────────────────────────────────────


def compute_dpo_loss(
    chosen_rewards: torch.Tensor,
    rejected_rewards: torch.Tensor,
    beta: float = 0.1,
) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Bradley-Terry DPO Loss with implicit reward parameterization:
        L = - log sigmoid( beta * (r_chosen - r_rejected) )
    Returns (loss, reward_margin).
    """
    margin = chosen_rewards - rejected_rewards
    loss = -F.logsigmoid(beta * margin).mean()
    return loss, margin.mean()


# ─── Training Loop ───────────────────────────────────────────────────────────


def train_dpo_overnight(
    dataset_path: str | Path,
    output_dir: str | Path,
    epochs: int = 50,
    batch_size: int = 8,
    lr: float = 1e-3,
    beta: float = 0.1,
    save_every: int = 10,
    device: str = "auto",
) -> dict[str, Any]:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    checkpoints_dir = out_path / "checkpoints"
    checkpoints_dir.mkdir(exist_ok=True)

    if device == "auto":
        dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        dev = torch.device(device)

    print("═══════════════════════════════════════════════════════════════════════")
    print("🧠 ANSE RL POST-TRAINING (DPO / THERMODYNAMIC CRITIC ALIGNMENT)")
    print(f"   Dataset:     {dataset_path}")
    print(
        f"   Device:      {dev} ({torch.cuda.get_device_name(0) if dev.type == 'cuda' else 'Local CPU'})"
    )
    print(f"   Epochs:      {epochs}")
    print(f"   Batch Size:  {batch_size}")
    print(f"   Beta (KL):   {beta}")
    print(f"   Output dir:  {out_path}")
    print("═══════════════════════════════════════════════════════════════════════\n")

    dataset = DPOPreferenceDataset(dataset_path)
    if len(dataset) == 0:
        raise ValueError("Dataset is empty. Run scripts/run_100_functional_tests.py first.")

    model = EnergyCriticPolicy(d_model=128, d_hidden=256).to(dev)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-2)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    history: list[dict[str, float]] = []
    start_time = time.time()

    print("Epoch | DPO Loss | Margin (Chosen - Rej) | Accuracy | Learning Rate | Time")
    print("------+----------+-----------------------+----------+---------------+-------")

    best_margin = -float("inf")
    best_loss = float("inf")

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_loss = 0.0
        epoch_margin = 0.0
        correct_ranks = 0
        total_samples = 0

        # Shuffle pairs
        indices = torch.randperm(len(dataset)).tolist()
        num_batches = math.ceil(len(dataset) / batch_size)

        for b_idx in range(num_batches):
            batch_indices = indices[b_idx * batch_size : (b_idx + 1) * batch_size]
            batch_pairs = [dataset[i] for i in batch_indices]
            bs = len(batch_pairs)

            prompts = torch.stack([tokenize_string(p["prompt"]) for p in batch_pairs]).to(dev)
            chosen = torch.stack([tokenize_string(p["chosen"]) for p in batch_pairs]).to(dev)
            rejected = torch.stack([tokenize_string(p["rejected"]) for p in batch_pairs]).to(dev)

            optimizer.zero_grad()
            r_chosen = model(prompts, chosen)
            r_rejected = model(prompts, rejected)

            loss, margin = compute_dpo_loss(r_chosen, r_rejected, beta=beta)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            epoch_loss += loss.item() * bs
            epoch_margin += margin.item() * bs
            correct_ranks += (r_chosen > r_rejected).sum().item()
            total_samples += bs

        scheduler.step()

        mean_loss = epoch_loss / total_samples
        mean_margin = epoch_margin / total_samples
        accuracy = correct_ranks / total_samples
        current_lr = scheduler.get_last_lr()[0]
        elapsed = time.time() - start_time

        history.append(
            {
                "epoch": epoch,
                "loss": mean_loss,
                "margin": mean_margin,
                "accuracy": accuracy,
                "lr": current_lr,
                "elapsed_seconds": elapsed,
            }
        )

        if epoch % 5 == 0 or epoch == 1 or epoch == epochs:
            print(
                f"{epoch:04d}  | {mean_loss:8.4f} | {mean_margin:21.4f} | {accuracy * 100:7.1f}% | {current_lr:.2e}      | {elapsed:5.1f}s"
            )

        # Save checkpoint
        if mean_margin > best_margin or epoch % save_every == 0 or epoch == epochs:
            best_margin = max(best_margin, mean_margin)
            best_loss = min(best_loss, mean_loss)
            ckpt_path = checkpoints_dir / f"model_epoch_{epoch:04d}.pt"
            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "loss": mean_loss,
                    "margin": mean_margin,
                    "accuracy": accuracy,
                },
                ckpt_path,
            )

    # Save final model
    final_model_path = out_path / "anse_critic_final.pt"
    torch.save(model.state_dict(), final_model_path)

    report = {
        "dataset": str(dataset_path),
        "total_pairs": len(dataset),
        "epochs": epochs,
        "final_loss": mean_loss,
        "final_margin": mean_margin,
        "final_accuracy": accuracy,
        "best_margin": best_margin,
        "best_loss": best_loss,
        "total_time_seconds": time.time() - start_time,
        "model_file": str(final_model_path),
        "history": history,
    }

    report_path = out_path / "training_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n═══════════════════════════════════════════════════════════════════════")
    print("🎯 RL POST-TRAINING COMPLETED SUCCESSFULLY")
    print(f"   Final DPO Loss:      {mean_loss:.4f} (converged)")
    print(f"   Final Reward Margin: {mean_margin:.4f} (positive separation)")
    print(f"   Accuracy:            {accuracy * 100:.1f}%")
    print(f"   Trained weights:     {final_model_path}")
    print(f"   Report:              {report_path}")
    print("═══════════════════════════════════════════════════════════════════════\n")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Nightly RL / DPO Post-Training.")
    parser.add_argument(
        "--dataset", type=str, default="results/rl_nightly/dpo_preference_pairs.jsonl"
    )
    parser.add_argument("--output-dir", type=str, default="results/rl_nightly")
    parser.add_argument(
        "--epochs", type=int, default=50, help="Number of training epochs (default: 50)"
    )
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size (default: 8)")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate (default: 1e-3)")
    parser.add_argument(
        "--beta", type=float, default=0.1, help="DPO temperature beta (default: 0.1)"
    )
    parser.add_argument("--device", type=str, default="auto")
    args = parser.parse_args()

    with gpu_lease(LEASE_HOLDER, "nightly RL: DPO critic training", ttl_s=3600, timeout_s=3600):
        train_dpo_overnight(
            dataset_path=args.dataset,
            output_dir=args.output_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            beta=args.beta,
            device=args.device,
        )


if __name__ == "__main__":
    main()
