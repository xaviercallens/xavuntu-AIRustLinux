#!/usr/bin/env python3
"""
Executes the Phase V3 Autopoietic Meta-Learning Engine (The Singularity Loop).
"""

import sys
import torch
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from anse.v3.engine_v3 import ANSEEngineV3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    logger.info("Initializing Phase V3 Autopoietic Meta-Learning Engine...")
    engine = ANSEEngineV3(latent_dim=128)
    
    logger.info("Simulating Initial Sensory Input (Latent Z Space)...")
    initial_latent = torch.randn(128)
    
    baseline_energy = 1500.0  # ms
    
    result = engine.run_singularity_loop(initial_latent, baseline_energy)
    
    logger.info(f"V3 Cycle {result.cycle_id} Summary:")
    logger.info(f"  MCTS Predicted Energy: {result.mcts_energy_pred:.4f}")
    logger.info(f"  Online DPO Loss:       {result.dpo_loss:.4f}")
    logger.info(f"  Autopoietic Commit:    {'APPROVED' if result.autopoietic_commit_success else 'REJECTED'}")
    logger.info(f"  Final Physical Energy: {result.final_physical_energy:.4f} ms (Baseline: {baseline_energy:.4f} ms)")

if __name__ == "__main__":
    main()
