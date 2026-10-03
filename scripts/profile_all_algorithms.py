#!/usr/bin/env python3
"""
Full ANSE Computational Physics Profiling Suite for 5 Complex Neuro-Symbolic Algorithms:
1. A* Search Engine vs Dijkstra (5 Goal-directed queries on 40x40 spatial grid)
2. k-D Tree Vector Memory vs Brute-force Linear Scan (2,000 points, 200 queries in R^4)
3. Micro-JEPA VICReg Loss vs Unvectorized Python Loops (B=256, D=48)
4. Banach Fixed-Point Engine vs Slow Damped Iteration (D=20 linear contraction)
5. Tarjan's Strongly Connected Components vs Warshall Matrix (N=150 nodes)

Executes all pairs inside SandboxExecutor (Tier 1) and computes physical Energy:
    E = duration_ms + peak_ram_mb
Asserts thermodynamic monotonic descent (ΔE < 0) for each case.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO_ROOT)

from anse.symbolic.sandbox import SandboxExecutor
from anse.symbolic.performance_evaluator import PerformanceEnergyEvaluator


# ─── UC1: A* Search vs Dijkstra ──────────────────────────────────────────────
ASTAR_BASELINE = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import time
from anse.algorithms.dijkstra import dijkstra_shortest_paths

size = 50
graph = {{}}
for x in range(size):
    for y in range(size):
        neighbors = []
        for nx, ny in [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]:
            if 0 <= nx < size and 0 <= ny < size:
                neighbors.append(((nx, ny), 1.0))
        graph[(x, y)] = neighbors

targets = [(49, 49), (49, 0), (0, 49), (25, 25), (40, 10), (10, 40), (30, 30), (45, 45)] * 3

t0 = time.perf_counter()
total_settled = 0
for t in targets:
    res = dijkstra_shortest_paths(graph, (0, 0), target=t)
    total_settled += res.settled_count
t1 = time.perf_counter()
print(f"DIJKSTRA_DONE: settled={{total_settled}}, time_ms={{(t1-t0)*1000:.2f}}")
"""

ASTAR_OPTIMIZED = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import time
from anse.algorithms.astar import astar_search

size = 50
graph = {{}}
for x in range(size):
    for y in range(size):
        neighbors = []
        for nx, ny in [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]:
            if 0 <= nx < size and 0 <= ny < size:
                neighbors.append(((nx, ny), 1.0))
        graph[(x, y)] = neighbors

def heuristic(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

targets = [(49, 49), (49, 0), (0, 49), (25, 25), (40, 10), (10, 40), (30, 30), (45, 45)] * 3

t0 = time.perf_counter()
total_settled = 0
for t in targets:
    res = astar_search(lambda p: graph.get(p, ()), heuristic, (0, 0), t)
    if res:
        total_settled += res.nodes_settled
t1 = time.perf_counter()
print(f"ASTAR_DONE: settled={{total_settled}}, time_ms={{(t1-t0)*1000:.2f}}")
"""

# ─── UC2: k-D Tree Vector Memory vs Brute-force Linear Scan ──────────────────
KDTREE_BASELINE = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import math, time, random
random.seed(42)

points = [[random.uniform(-50, 50) for _ in range(4)] for _ in range(2000)]
queries = [[random.uniform(-50, 50) for _ in range(4)] for _ in range(200)]

def linear_nn(pts, q):
    best_d = math.inf
    best_p = None
    for p in pts:
        d = math.sqrt(sum((a - b)**2 for a, b in zip(p, q)))
        if d < best_d:
            best_d = d
            best_p = p
    return best_d

t0 = time.perf_counter()
for q in queries:
    _ = linear_nn(points, q)
t1 = time.perf_counter()
print(f"LINEAR_KNN_DONE: time_ms={{(t1-t0)*1000:.2f}}")
"""

KDTREE_OPTIMIZED = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import time, random
from anse.algorithms.kdtree import KDTree
random.seed(42)

points = [([random.uniform(-50, 50) for _ in range(4)], i) for i in range(2000)]
queries = [[random.uniform(-50, 50) for _ in range(4)] for _ in range(200)]

t0 = time.perf_counter()
tree = KDTree(points)
for q in queries:
    _ = tree.query_nearest(q)
t1 = time.perf_counter()
print(f"KDTREE_DONE: time_ms={{(t1-t0)*1000:.2f}}")
"""

# ─── UC3: Micro-JEPA VICReg Loss (Vectorized vs Python Loops) ────────────────
VICREG_BASELINE = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import numpy as np, time
np.random.seed(42)
B, D = 256, 48
z = np.random.randn(B, D)
z_prime = np.random.randn(B, D)

# Naive unvectorized covariance calculation using nested Python loops
t0 = time.perf_counter()
cov = np.zeros((D, D))
z_cent = z - np.mean(z, axis=0)
for i in range(D):
    for j in range(D):
        if i != j:
            cov[i, j] = sum(z_cent[b, i] * z_cent[b, j] for b in range(B)) / (B - 1)
cov_loss = np.sum(cov**2) / D
t1 = time.perf_counter()
print(f"NAIVE_VICREG_DONE: time_ms={{(t1-t0)*1000:.2f}}")
"""

VICREG_OPTIMIZED = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import numpy as np, time
from anse.algorithms.vicreg import compute_vicreg_loss
np.random.seed(42)
B, D = 256, 48
z = np.random.randn(B, D)
z_prime = np.random.randn(B, D)

t0 = time.perf_counter()
res = compute_vicreg_loss(z, z_prime)
t1 = time.perf_counter()
print(f"OPT_VICREG_DONE: time_ms={{(t1-t0)*1000:.2f}}")
"""

# ─── UC4: Banach Fixed-Point Engine vs Slow Damped Iteration ─────────────────
BANACH_BASELINE = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import numpy as np, time
np.random.seed(42)
D = 80

systems = []
for _ in range(12):
    A = np.random.uniform(-0.05, 0.05, (D, D))
    b = np.ones(D)
    systems.append((A, b))

# Naive over-damped iteration with tiny relaxation steps (omega=0.005)
t0 = time.perf_counter()
for A, b in systems:
    x = np.zeros(D)
    for _ in range(3000):
        x_new = 0.005 * (A @ x + b) + 0.995 * x
        if np.linalg.norm(x_new - x) < 1e-6:
            break
        x = x_new
t1 = time.perf_counter()
print(f"SLOW_DAMPED_DONE: time_ms={{(t1-t0)*1000:.2f}}")
"""

BANACH_OPTIMIZED = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import numpy as np, time
from anse.algorithms.fixed_point import solve_banach_fixed_point
np.random.seed(42)
D = 80

systems = []
for _ in range(12):
    A = np.random.uniform(-0.05, 0.05, (D, D))
    b = np.ones(D)
    systems.append((A, b))

t0 = time.perf_counter()
for A, b in systems:
    res = solve_banach_fixed_point(lambda x, a_mat=A, b_vec=b: a_mat @ x + b_vec, np.zeros(D), tol=1e-6)
t1 = time.perf_counter()
print(f"OPT_BANACH_DONE: iters={{res.iterations}}, time_ms={{(t1-t0)*1000:.2f}}")
"""

# ─── UC5: Tarjan SCC vs Warshall Reachability Matrix ──────────────────────────
TARJAN_BASELINE = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import time, random
random.seed(42)
N = 140
edges = [(i, (i + 1) % N) for i in range(N)] + [(random.randint(0, N-1), random.randint(0, N-1)) for _ in range(100)]

# Naive O(N^3) Floyd-Warshall transitive closure for mutual reachability
t0 = time.perf_counter()
reach = [[False]*N for _ in range(N)]
for i in range(N):
    reach[i][i] = True
for u, v in edges:
    reach[u][v] = True
for k in range(N):
    for i in range(N):
        if reach[i][k]:
            for j in range(N):
                reach[i][j] = reach[i][j] or reach[k][j]

scc_count = 0
visited = set()
for i in range(N):
    if i not in visited:
        scc_count += 1
        for j in range(N):
            if reach[i][j] and reach[j][i]:
                visited.add(j)
t1 = time.perf_counter()
print(f"WARSHALL_SCC_DONE: sccs={{scc_count}}, time_ms={{(t1-t0)*1000:.2f}}")
"""

TARJAN_OPTIMIZED = f"""
import sys
sys.path.insert(0, "{REPO_ROOT}")
import time, random
from anse.algorithms.tarjan_scc import find_strongly_connected_components
random.seed(42)
N = 140
edges = [(i, (i + 1) % N) for i in range(N)] + [(random.randint(0, N-1), random.randint(0, N-1)) for _ in range(100)]

graph = {{i: [] for i in range(N)}}
for u, v in edges:
    graph[u].append(v)

t0 = time.perf_counter()
res = find_strongly_connected_components(graph)
t1 = time.perf_counter()
print(f"TARJAN_SCC_DONE: sccs={{len(res.components)}}, time_ms={{(t1-t0)*1000:.2f}}")
"""


CASES = [
    ("UC1: A* Search vs Dijkstra", ASTAR_BASELINE, ASTAR_OPTIMIZED),
    ("UC2: k-D Tree Memory vs Linear Scan", KDTREE_BASELINE, KDTREE_OPTIMIZED),
    ("UC3: Micro-JEPA VICReg Vectorization", VICREG_BASELINE, VICREG_OPTIMIZED),
    ("UC4: Banach Contraction vs Slow Damping", BANACH_BASELINE, BANACH_OPTIMIZED),
    ("UC5: Tarjan SCC vs Warshall Matrix", TARJAN_BASELINE, TARJAN_OPTIMIZED),
]


def run_all_profiles() -> list[dict[str, object]]:
    print("=" * 75)
    print("ANSE Full Computational Physics Profiling: 5 Complex Neuro-Symbolic Algorithms")
    print("=" * 75)

    sandbox = SandboxExecutor()
    evaluator = PerformanceEnergyEvaluator()
    reports = []

    for name, base_code, opt_code in CASES:
        print(f"\n---> Profiling {name}...")
        r_base = sandbox.execute(base_code, force_tier=1)
        e_base = evaluator.evaluate(r_base)
        assert r_base.returncode == 0, f"Baseline failed: {r_base.stderr}"

        r_opt = sandbox.execute(opt_code, force_tier=1)
        e_opt = evaluator.evaluate(r_opt, baseline_result=r_base)
        assert r_opt.returncode == 0, f"Optimized failed: {r_opt.stderr}"

        speedup = r_base.duration_ms / max(r_opt.duration_ms, 0.001)
        delta_e = e_opt.score - e_base.score

        print(f"  [Baseline]  Stdout: {r_base.stdout.strip()} | Duration: {r_base.duration_ms:.2f} ms | Energy: {e_base.score:.2f}")
        print(f"  [Optimized] Stdout: {r_opt.stdout.strip()} | Duration: {r_opt.duration_ms:.2f} ms | Energy: {e_opt.score:.2f}")
        print(f"  [Verdict]   Speedup: {speedup:.2f}x | ΔE: {delta_e:.2f}")

        # Assert thermodynamic invariant
        assert delta_e < 0, f"Thermodynamic violation on {name}: delta_e={delta_e:.2f}"
        print(f"  [PASS] Thermodynamic Invariant Satisfied: ΔE < 0")

        reports.append({
            "use_case": name,
            "baseline": {
                "duration_ms": r_base.duration_ms,
                "peak_ram_mb": r_base.peak_ram_mb,
                "energy": e_base.score,
                "output": r_base.stdout.strip(),
            },
            "optimized": {
                "duration_ms": r_opt.duration_ms,
                "peak_ram_mb": r_opt.peak_ram_mb,
                "energy": e_opt.score,
                "output": r_opt.stdout.strip(),
            },
            "speedup": speedup,
            "energy_delta": delta_e,
            "thermodynamic_pass": delta_e < 0,
        })

    out_file = Path(REPO_ROOT) / "results" / "five_algorithms_physics_report.json"
    with open(out_file, "w") as f:
        json.dump(reports, f, indent=2)

    print(f"\nAll 5 cases satisfied thermodynamic constraints! Saved to: {out_file}")
    return reports


if __name__ == "__main__":
    run_all_profiles()
