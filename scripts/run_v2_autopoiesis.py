#!/usr/bin/env python3
"""
Executes the ANSE 2.0 Master Autopoietic Engine on a physics benchmark.
"""

import sys
import torch
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from anse.v2.engine_v2 import ANSEEngineV2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    logger.info("Initializing ANSE V2 Master Autopoietic Engine...")
    engine = ANSEEngineV2(input_dim=128, latent_dim=128)
    
    logger.info("Simulating Sensory Input (Latent Z Space)...")
    sensory_input = torch.randn(1, 128)
    
    logger.info("Triggering ANSE V2 Autonomous Cycle (Surrogate + MeZO + REM + System 3)...")
    result = engine.run_autonomous_cycle(
        sensory_input=sensory_input,
        prompt_text="Optimize fluid dynamics Navier-Stokes incompressible solver for V100 GPU",
        num_monte_carlo=1000,
        trigger_sleep_after=True
    )
    
    logger.info(f"V2 Cycle Completed: Cycle ID {result.cycle_id}")
    logger.info(f"Monte Carlo Rollouts: {result.surrogate_summary.total_evaluated} evaluated, {result.surrogate_summary.selected_count} selected in {result.surrogate_summary.total_latency_ms:.2f}ms")
    logger.info(f"System 3 Falsification: {'FALSIFIED' if result.falsification_report.is_falsified else 'PASSED'}")
    logger.info(f"Final Sandbox Verified: {result.sandbox_verified}")
    logger.info(f"Final Energy Score: {result.final_energy_score:.4f}")
    if result.rem_summary:
        logger.info(f"REM Sleep Consolidation: {result.rem_summary}")
    
    print("\nANSE V2 Integration: SUCCESS")

if __name__ == "__main__":
    main()
