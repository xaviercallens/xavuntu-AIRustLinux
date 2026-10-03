#!/usr/bin/env python3
"""
RunuX AI Runtime Optimization CLI for Xavuntu.

Leverages algorithms from https://github.com/xaviercallens/runux-ai-runtime:
- PolarQuant 3-bit / 4-bit KV Cache Compression
- MLGO Systolic Tiling Advisor for TPU v5e/v6e and Intel Xeon AVX-512 VNNI / T4
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from anse.runtime.runux_optimizer import RunuXOptimizer


def main() -> None:
    parser = argparse.ArgumentParser(description="RunuX AI Runtime Optimizer CLI")
    parser.add_argument("--model", default="gwaya-qwen:14b-t4", help="Model name to profile")
    parser.add_argument("--ctx", type=int, default=8192, help="Context length")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    opt = RunuXOptimizer(platform="xavuntu_tpu_vma")
    res = opt.optimize_model_inference(args.model, context_length=args.ctx)

    if args.json:
        print(json.dumps(res, indent=2))
        return

    print("=== RUNUX AI RUNTIME OPTIMISATION TELEMETRY ===")
    print(f"Modèle Cible           : {res['model_name']}")
    print(f"Plateforme Matérielle  : {res['hardware_platform']}")
    print(f"Fenêtre de Contexte    : {res['context_length']} tokens")
    print(f"Poids du Modèle        : {res['weight_memory_gb']} Go")
    print(f"KV-Cache Décompressé   : {res['uncompressed_kv_mb']} Mo")
    print(f"KV-Cache PolarQuant 3b : {res['polarquant_kv_mb']} Mo (Gain: {res['kv_compression_ratio']})")
    print(f"Efficacité Systolique  : {res['systolic_efficiency']}")
    print(f"Accélération Calcul    : {res['systolic_speedup']}")
    print(f"Gestionnaire KV Paged  : {res['paged_cache_status']}")
    print(f"Attestation Formelle   : {res['optimization_attestation']}")


if __name__ == "__main__":
    main()
