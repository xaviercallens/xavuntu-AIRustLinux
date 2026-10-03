#!/usr/bin/env python3
import time
import subprocess
import sys
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def run_script(script_path: str, phase_name: str):
    logger.info(f"--- Running {phase_name} ---")
    start_time = time.time()
    result = subprocess.run(["python3", script_path], capture_output=True, text=True)
    end_time = time.time()
    
    duration = end_time - start_time
    success = result.returncode == 0
    
    if not success:
        logger.error(f"{phase_name} FAILED in {duration:.2f}s")
        logger.error(f"Error output:\n{result.stderr}")
    else:
        logger.info(f"{phase_name} COMPLETED in {duration:.2f}s")
        
    return {
        "phase": phase_name,
        "success": success,
        "duration_seconds": duration,
        "output_length": len(result.stdout),
        "stderr": result.stderr if not success else None
    }

def main():
    results = []
    results.append(run_script("scripts/run_v2_autopoiesis.py", "Phase V2 (Surrogate Cache)"))
    results.append(run_script("scripts/run_phase3_singularity_loop.py", "Phase V3 (Autopoietic Meta-Learning)"))
    results.append(run_script("scripts/run_v4_certification.py", "Phase V4 (Safe ANSE - DoAIK)"))
    
    logger.info("=== SUMMARY ===")
    for r in results:
        status = "PASS" if r['success'] else "FAIL"
        logger.info(f"{r['phase']}: {status} ({r['duration_seconds']:.2f}s)")
        
    with open("results_all_phases.json", "w") as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    main()
