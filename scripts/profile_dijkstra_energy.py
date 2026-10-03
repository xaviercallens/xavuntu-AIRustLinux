#!/usr/bin/env python3
"""
Computational Physics Profiling for Dijkstra's Algorithm.

Compares:
- Candidate 0 (Naive O(V^2) unindexed Dijkstra)
- Candidate 1 (Optimized O((V+E) log V) Min-Heap Dijkstra from anse.algorithms.dijkstra)

Executes both in the deterministic SandboxExecutor and computes physical Energy:
    E = duration_ms + peak_ram_mb
Asserts thermodynamic improvement:
    ΔE = E_optimized - E_naive < 0
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add repo root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anse.symbolic.sandbox import SandboxExecutor
from anse.symbolic.performance_evaluator import PerformanceEnergyEvaluator

REPO_ROOT = str(Path(__file__).resolve().parent.parent)

NAIVE_BENCHMARK_CODE = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import random
import math
import time

# Generate deterministic graph
random.seed(42)
N = 500
graph = {{i: [] for i in range(N)}}
for i in range(N):
    for _ in range(6):
        target = random.randint(0, N - 1)
        if target != i:
            graph[i].append((target, random.uniform(1.0, 50.0)))

# Naive O(V^2) Dijkstra without priority queue
def naive_dijkstra(graph, source):
    unvisited = set(graph.keys())
    distances = {{node: math.inf for node in graph}}
    distances[source] = 0.0

    while unvisited:
        # Linear O(V) minimum search every step
        current = None
        min_d = math.inf
        for node in unvisited:
            if distances[node] < min_d:
                min_d = distances[node]
                current = node

        if current is None or min_d == math.inf:
            break

        unvisited.remove(current)

        for neighbor, weight in graph[current]:
            if neighbor in unvisited:
                new_dist = distances[current] + weight
                if new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist

    return distances

t0 = time.perf_counter()
dist = naive_dijkstra(graph, 0)
t1 = time.perf_counter()
reachable = sum(1 for d in dist.values() if d < math.inf)
print(f"DONE_NAIVE: reachable={{reachable}}, time_ms={{(t1-t0)*1000:.2f}}")
"""

OPTIMIZED_BENCHMARK_CODE = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import random
import math
import time
from anse.algorithms.dijkstra import dijkstra_shortest_paths

# Generate identical deterministic graph
random.seed(42)
N = 500
graph = {{i: [] for i in range(N)}}
for i in range(N):
    for _ in range(6):
        target = random.randint(0, N - 1)
        if target != i:
            graph[i].append((target, random.uniform(1.0, 50.0)))

t0 = time.perf_counter()
res = dijkstra_shortest_paths(graph, 0)
t1 = time.perf_counter()
reachable = sum(1 for d in res.distances.values() if d < math.inf)
print(f"DONE_OPTIMIZED: reachable={{reachable}}, time_ms={{(t1-t0)*1000:.2f}}")
"""


def run_physics_comparison() -> dict[str, object]:
    print("=" * 70)
    print("ANSE Computational Physics Profiling: Dijkstra Optimization")
    print("=" * 70)

    sandbox = SandboxExecutor()
    evaluator = PerformanceEnergyEvaluator()

    print("\n[1/3] Executing Naive Candidate 0 (O(V^2) linear scan)...")
    naive_res = sandbox.execute(NAIVE_BENCHMARK_CODE, force_tier=1)
    naive_energy = evaluator.evaluate(naive_res)
    print(f"  -> Exit code: {naive_res.returncode}")
    print(f"  -> Stdout: {naive_res.stdout.strip()}")
    print(f"  -> Duration: {naive_res.duration_ms:.2f} ms")
    print(f"  -> Peak RAM: {naive_res.peak_ram_mb:.2f} MB")
    print(f"  -> Naive Energy E_0: {naive_energy.score:.2f}")

    print("\n[2/3] Executing Optimized Candidate 1 (O((V+E) log V) Min-Heap)...")
    opt_res = sandbox.execute(OPTIMIZED_BENCHMARK_CODE, force_tier=1)
    opt_energy = evaluator.evaluate(opt_res, baseline_result=naive_res)
    print(f"  -> Exit code: {opt_res.returncode}")
    print(f"  -> Stdout: {opt_res.stdout.strip()}")
    print(f"  -> Duration: {opt_res.duration_ms:.2f} ms")
    print(f"  -> Peak RAM: {opt_res.peak_ram_mb:.2f} MB")
    print(f"  -> Optimized Energy E_1: {opt_energy.score:.2f}")

    speedup = naive_res.duration_ms / max(opt_res.duration_ms, 0.001)
    delta_e = opt_energy.score - naive_energy.score
    print("\n[3/3] Computational Physics Evaluation:")
    print(f"  -> Speedup: {speedup:.2f}x")
    print(f"  -> Energy Delta (ΔE = E_opt - E_naive): {delta_e:.2f}")

    assert opt_res.returncode == 0, f"Optimized execution failed: {opt_res.stderr}"
    assert naive_res.returncode == 0, f"Naive execution failed: {naive_res.stderr}"
    assert delta_e < 0, f"Thermodynamic violation! Energy did not decrease: ΔE = {delta_e:.2f}"

    print(f"\n[PASS] Thermodynamic Invariant Satisfied: ΔE < 0 ({delta_e:.2f})")
    print("Optimization candidate accepted for autopoietic promotion!")

    report = {
        "algorithm": "Dijkstra",
        "graph_nodes": 500,
        "graph_edges": 3000,
        "naive": {
            "duration_ms": naive_res.duration_ms,
            "peak_ram_mb": naive_res.peak_ram_mb,
            "energy": naive_energy.score,
            "category": naive_energy.category.value,
        },
        "optimized": {
            "duration_ms": opt_res.duration_ms,
            "peak_ram_mb": opt_res.peak_ram_mb,
            "energy": opt_energy.score,
            "category": opt_energy.category.value,
        },
        "speedup_factor": speedup,
        "energy_delta": delta_e,
        "thermodynamic_pass": delta_e < 0,
    }

    results_dir = Path(__file__).resolve().parent.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    out_file = results_dir / "dijkstra_energy_profile.json"
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Saved profiling report to: {out_file}")

    return report


if __name__ == "__main__":
    run_physics_comparison()
