"""
ANSE Algorithmic Engine & Physical Optimization Modules.

Exports production neuro-symbolic algorithms:
- Dijkstra Shortest Paths (O((V+E)log V) min-heap)
- A* Search with Admissible Heuristics
- k-D Tree Vector Memory Retrieval
- Micro-JEPA Non-Contrastive VICReg Loss Engine
- Banach Fixed-Point Contraction Engine
- Tarjan's Strongly Connected Components & DAG Condenser
"""

from anse.algorithms.astar import AStarResult, astar_search
from anse.algorithms.dijkstra import ShortestPathResult, dijkstra_shortest_paths
from anse.algorithms.fixed_point import (
    FixedPointResult,
    estimate_lipschitz_constant,
    solve_banach_fixed_point,
)
from anse.algorithms.kdtree import KDNeighbor, KDTree
from anse.algorithms.symplectic import (
    SymplecticResult,
    compute_poincare_section,
    estimate_lyapunov_exponent,
    explicit_euler_integrate,
    solve_symplectic_orbit,
)
from anse.algorithms.tarjan_scc import SCCResult, find_strongly_connected_components
from anse.algorithms.vicreg import VICRegLossResult, compute_vicreg_loss

__all__ = [
    "AStarResult",
    "FixedPointResult",
    "KDNeighbor",
    "KDTree",
    "SCCResult",
    "ShortestPathResult",
    "SymplecticResult",
    "VICRegLossResult",
    "astar_search",
    "compute_poincare_section",
    "compute_vicreg_loss",
    "dijkstra_shortest_paths",
    "estimate_lipschitz_constant",
    "estimate_lyapunov_exponent",
    "explicit_euler_integrate",
    "find_strongly_connected_components",
    "solve_banach_fixed_point",
    "solve_symplectic_orbit",
]
