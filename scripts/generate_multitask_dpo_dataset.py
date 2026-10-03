#!/usr/bin/env python3
"""
Generate the multi-task DPO dataset for the 5 complex neuro-symbolic algorithms.
Outputs: results/dpo_multitask_dataset.jsonl
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Read the chosen implementations directly from the repository
astar_code = (REPO_ROOT / "anse/algorithms/astar.py").read_text()
kdtree_code = (REPO_ROOT / "anse/algorithms/kdtree.py").read_text()
vicreg_code = (REPO_ROOT / "anse/algorithms/vicreg.py").read_text()
fixed_point_code = (REPO_ROOT / "anse/algorithms/fixed_point.py").read_text()
tarjan_code = (REPO_ROOT / "anse/algorithms/tarjan_scc.py").read_text()

# Read profiling metrics
physics_report = json.loads((REPO_ROOT / "results/five_algorithms_physics_report.json").read_text())
metrics_map = {item["use_case"]: item for item in physics_report}

records = [
    # UC1: A* Search
    {
        "prompt": [
            {
                "role": "system",
                "content": "You are an autonomous AI coding engineer operating under ANSE computational physics constraints. You must deliver mathematically sound, zero-stub algorithms with optimal energy complexity."
            },
            {
                "role": "user",
                "content": "Implement the A* heuristic search algorithm in Python for generalized graphs. Requirements:\n1. Complexity: O((|V| + |E|) log |V|) using a binary min-heap priority queue.\n2. Admissibility: Support an arbitrary heuristic function h(u, goal) that never overestimates distance.\n3. Monotonicity: Support consistent/monotone heuristics ensuring optimal paths upon first settlement.\n4. Negative weights: Detect and reject negative edge weights with ValueError.\n5. Structured Result: Return an immutable dataclass containing path, distance, settled count, and explored nodes."
            }
        ],
        "chosen": astar_code,
        "rejected": """import math

def astar(graph, start, goal, heuristic=None):
    # Flawed: unindexed linear search with stub heuristic
    open_set = [start]
    came_from = {}
    g_score = {start: 0}
    
    while open_set:
        # O(N) scan instead of binary heap
        current = None
        for node in open_set:
            if current is None or g_score.get(node, math.inf) < g_score.get(current, math.inf):
                current = node
        if current == goal:
            return came_from  # Incomplete: returns unformatted raw dict
        open_set.remove(current)
        for neighbor, weight in graph.get(current, []):
            # No negative weight validation!
            tentative_g = g_score[current] + weight
            if tentative_g < g_score.get(neighbor, math.inf):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                if neighbor not in open_set:
                    open_set.append(neighbor)
    return None  # Unhandled failure mode
""",
        "metadata": {
            "use_case_id": "UC1",
            "task_name": "A* Search Engine with Admissible Heuristics",
            "baseline": "Dijkstra Exhaustive Search / Naive O(N) Open Set Scan",
            "speedup": metrics_map["UC1: A* Search vs Dijkstra"]["speedup"],
            "energy_delta": metrics_map["UC1: A* Search vs Dijkstra"]["energy_delta"],
            "failure_reasons": ["O(N) unindexed open set lookup", "Missing negative edge validation", "No path reconstruction", "Unstructured return value"],
            "thermodynamic_pass": True
        }
    },

    # UC2: k-D Tree Memory
    {
        "prompt": [
            {
                "role": "system",
                "content": "You are an autonomous AI coding engineer operating under ANSE computational physics constraints. You must deliver mathematically sound, zero-stub algorithms with optimal energy complexity."
            },
            {
                "role": "user",
                "content": "Implement a balanced k-D Tree vector spatial index in Python for fast nearest-neighbor memory retrieval. Requirements:\n1. Construction: Build balanced binary space partitioning tree in O(D * N log N) using median selection.\n2. Query: Exact k-Nearest Neighbors in O(k log N) expected time using branch pruning based on hypersphere bounding box intersections.\n3. Determinism: Handle arbitrary dimension D without recursion depth explosion or memory leaks.\n4. Quality: Immutable dataclass results with point indices, coordinates, and exact Euclidean distances."
            }
        ],
        "chosen": kdtree_code,
        "rejected": """import math

class KDTree:
    def __init__(self, points):
        # Stub: stores flat list without tree partitioning
        self.points = points

    def query(self, target, k=1):
        # Degenerate O(N log N) brute-force linear distance calculation
        # TODO: implement actual k-d tree splitting
        distances = []
        for p in self.points:
            d = math.sqrt(sum((a - b) ** 2 for a, b in zip(p, target)))
            distances.append((d, p))
        distances.sort()
        return distances[:k]
""",
        "metadata": {
            "use_case_id": "UC2",
            "task_name": "k-D Tree Vector Spatial Memory Index",
            "baseline": "Linear Scan O(N * D)",
            "speedup": metrics_map["UC2: k-D Tree Memory vs Linear Scan"]["speedup"],
            "energy_delta": metrics_map["UC2: k-D Tree Memory vs Linear Scan"]["energy_delta"],
            "failure_reasons": ["Flat list storage without spatial hierarchy", "O(N) scan per query", "High memory allocation per call", "TODO stubs"],
            "thermodynamic_pass": True
        }
    },

    # UC3: Micro-JEPA VICReg Loss Engine
    {
        "prompt": [
            {
                "role": "system",
                "content": "You are an autonomous AI coding engineer operating under ANSE computational physics constraints. You must deliver mathematically sound, zero-stub algorithms with optimal energy complexity."
            },
            {
                "role": "user",
                "content": "Implement the non-contrastive VICReg (Variance-Invariance-Covariance) loss engine in PyTorch for self-supervised representation learning. Requirements:\n1. Terms: Compute Invariance (MSE between representations), Variance (hinge penalty maintaining std >= gamma), and Covariance (decorrelation off-diagonal penalties).\n2. Physics: Fully vectorized tensor operations eliminating explicit Python loops over features.\n3. Numerical Stability: Guard variance computation against NaN/division-by-zero using epsilon clamping.\n4. Collapse Detection: Provide automated collapse detection when empirical standard deviation drops below threshold."
            }
        ],
        "chosen": vicreg_code,
        "rejected": """import torch
import torch.nn as nn

class NaiveVICReg(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, z_a, z_b):
        # Inefficient: unvectorized nested loops over batch and feature dimensions
        # Prone to GPU sync stalls and high CPU dispatch overhead
        N, D = z_a.shape
        inv_loss = 0.0
        for i in range(N):
            for j in range(D):
                inv_loss += (z_a[i, j] - z_b[i, j]) ** 2
        inv_loss /= (N * D)

        # Unstable variance without epsilon clamping
        var_loss = 0.0
        for j in range(D):
            mean_j = torch.mean(z_a[:, j])
            std_j = torch.sqrt(torch.mean((z_a[:, j] - mean_j) ** 2))
            var_loss += max(0.0, 1.0 - std_j.item())

        return inv_loss + var_loss
""",
        "metadata": {
            "use_case_id": "UC3",
            "task_name": "Micro-JEPA VICReg Non-Contrastive Loss Engine",
            "baseline": "Naive Unvectorized Python Loops",
            "speedup": metrics_map["UC3: Micro-JEPA VICReg Vectorization"]["speedup"],
            "energy_delta": metrics_map["UC3: Micro-JEPA VICReg Vectorization"]["energy_delta"],
            "failure_reasons": ["Unvectorized nested Python loops", "High dispatch latency", "Missing covariance off-diagonal penalty", "Lack of numerical epsilon guarding"],
            "thermodynamic_pass": True
        }
    },

    # UC4: Banach Contraction Engine
    {
        "prompt": [
            {
                "role": "system",
                "content": "You are an autonomous AI coding engineer operating under ANSE computational physics constraints. You must deliver mathematically sound, zero-stub algorithms with optimal energy complexity."
            },
            {
                "role": "user",
                "content": "Implement a Banach Fixed-Point Contraction Solver in PyTorch for recurrent equilibrium states and autopoietic self-stabilization. Requirements:\n1. Contraction Invariant: Enforce ||T(x) - T(y)|| <= L * ||x - y|| with strict Lipschitz constant L < 1.0.\n2. Iterative Convergence: Iterate x_{k+1} = T(x_k) until ||x_{k+1} - x_k|| < tolerance or max iterations reached.\n3. Error Bound: Compute a priori / a posteriori theoretical Banach error bounds: ||x_k - x*|| <= (L^k / (1 - L)) * ||x_1 - x_0||.\n4. Verification: Automatically certify contraction modulus before iterative execution."
            }
        ],
        "chosen": fixed_point_code,
        "rejected": """import torch

def solve_fixed_point(f, x0, max_iter=1000):
    # Naive damped iteration with no Lipschitz contractivity check
    # Will diverge or cycle indefinitely if L >= 1.0
    x = x0
    for _ in range(max_iter):
        next_x = 0.5 * x + 0.5 * f(x)
        # TODO: check convergence correctly
        x = next_x
    return x
""",
        "metadata": {
            "use_case_id": "UC4",
            "task_name": "Banach Fixed-Point Contraction Solver",
            "baseline": "Slow Damped Iteration without Lipschitz Bound",
            "speedup": metrics_map["UC4: Banach Contraction vs Slow Damping"]["speedup"],
            "energy_delta": metrics_map["UC4: Banach Contraction vs Slow Damping"]["energy_delta"],
            "failure_reasons": ["No Lipschitz constant validation", "No convergence tolerance stopping criteria", "No Banach theoretical error bounds", "TODO stubs"],
            "thermodynamic_pass": True
        }
    },

    # UC5: Tarjan SCC
    {
        "prompt": [
            {
                "role": "system",
                "content": "You are an autonomous AI coding engineer operating under ANSE computational physics constraints. You must deliver mathematically sound, zero-stub algorithms with optimal energy complexity."
            },
            {
                "role": "user",
                "content": "Implement Tarjan's Strongly Connected Components (SCC) and DAG condensation algorithm in Python for neuro-symbolic causal graphs. Requirements:\n1. Complexity: Strict linear time O(|V| + |E|) single-pass depth-first search.\n2. Invariant: Maintain discovery indices and low-link values using an explicit node stack.\n3. Condensation: Build condensed Directed Acyclic Graph (DAG) where each meta-node is an SCC with deduplicated cross-component edges.\n4. Topological Order: Return the condensed components in valid reverse topological order.\n5. Quality: Immutable dataclass results, fully typed generic implementation, zero mock stubs."
            }
        ],
        "chosen": tarjan_code,
        "rejected": """def find_sccs(graph):
    # Degenerate O(V^3) Warshall transitive closure
    nodes = list(graph.keys())
    reach = {u: {v: False for v in nodes} for u in nodes}
    for u in nodes:
        reach[u][u] = True
        for v in graph.get(u, []):
            reach[u][v] = True
    for k in nodes:
        for i in nodes:
            for j in nodes:
                reach[i][j] = reach[i][j] or (reach[i][k] and reach[k][j])
    
    # Incomplete: doesn't build condensed DAG
    sccs = []
    # TODO: group nodes by mutual reachability
    return sccs
""",
        "metadata": {
            "use_case_id": "UC5",
            "task_name": "Tarjan SCC & DAG Condensation Engine",
            "baseline": "Warshall Transitive Closure O(V^3)",
            "speedup": metrics_map["UC5: Tarjan SCC vs Warshall Matrix"]["speedup"],
            "energy_delta": metrics_map["UC5: Tarjan SCC vs Warshall Matrix"]["energy_delta"],
            "failure_reasons": ["O(V^3) matrix multiplication", "No condensation DAG construction", "No topological ordering", "TODO stubs"],
            "thermodynamic_pass": True
        }
    }
]

output_path = REPO_ROOT / "results/dpo_multitask_dataset.jsonl"
with open(output_path, "w", encoding="utf-8") as f:
    for rec in records:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

print(f"[SUCCESS] Wrote {len(records)} high-fidelity DPO triplets to {output_path}")
