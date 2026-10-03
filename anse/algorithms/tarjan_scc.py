"""
Production-grade Tarjan's Strongly Connected Components (SCC) and DAG Condenser.

Computes maximal mutually reachable subgraphs in O(V + E) time, detects
deadlock cycles in agent DAG workflows, and condenses graph into topological order.
Conforms to SPEC-ALG-TARJAN and Anti-Stub Guard invariants.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T", bound=Hashable)


@dataclass(frozen=True)
class SCCResult(Generic[T]):
    """
    Decomposition of a directed graph into strongly connected components.

    Attributes:
        components: List of components, where each component is a list of nodes.
        node_to_component: Mapping from node identifier to component index.
        is_dag: True if graph has no directed cycles.
        cyclic_components: List of components representing cyclic deadlock loops.
        condensed_dag: Adjacency mapping of component IDs representing the quotient DAG.
        topological_order: Valid execution order of component IDs.
    """

    components: list[list[T]]
    node_to_component: dict[T, int]
    is_dag: bool
    cyclic_components: list[list[T]]
    condensed_dag: dict[int, list[int]]
    topological_order: list[int]


def find_strongly_connected_components(
    graph: Mapping[T, Iterable[T]],
) -> SCCResult[T]:
    """
    Execute Tarjan's linear-time algorithm to decompose a directed graph into SCCs.

    Args:
        graph: Adjacency mapping where graph[u] yields an iterable of successor nodes v.

    Returns:
        SCCResult[T] with SCC decomposition, cycle detection, and condensed DAG.
    """
    all_nodes: set[T] = set(graph.keys())
    for neighbors in graph.values():
        all_nodes.update(neighbors)

    discovery: dict[T, int] = {}
    low_link: dict[T, int] = {}
    on_stack: set[T] = set()
    stack: list[T] = []

    components: list[list[T]] = []
    timer: int = 0

    # Iterative DFS or recursive DFS with system stack
    def _strongconnect(v: T) -> None:
        nonlocal timer
        discovery[v] = timer
        low_link[v] = timer
        timer += 1
        stack.append(v)
        on_stack.add(v)

        for w in graph.get(v, ()):
            if w not in discovery:
                _strongconnect(w)
                low_link[v] = min(low_link[v], low_link[w])
            elif w in on_stack:
                low_link[v] = min(low_link[v], discovery[w])

        if low_link[v] == discovery[v]:
            component: list[T] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                component.append(w)
                if w == v:
                    break
            components.append(component)

    for node in all_nodes:
        if node not in discovery:
            _strongconnect(node)

    # Reverse components so that topological order flows naturally
    components.reverse()

    node_to_comp: dict[T, int] = {}
    for comp_idx, comp in enumerate(components):
        for node in comp:
            node_to_comp[node] = comp_idx

    # Check for cycles: size > 1 OR size == 1 with self-loop
    cyclic_comps: list[list[T]] = []
    for comp in components:
        if len(comp) > 1:
            cyclic_comps.append(comp)
        elif len(comp) == 1:
            u = comp[0]
            if u in graph.get(u, ()):
                cyclic_comps.append(comp)

    is_dag = len(cyclic_comps) == 0

    # Build condensed quotient DAG
    condensed_dag_set: dict[int, set[int]] = defaultdict(set)
    in_degree: dict[int, int] = {i: 0 for i in range(len(components))}

    for u in all_nodes:
        u_comp = node_to_comp[u]
        for v in graph.get(u, ()):
            v_comp = node_to_comp[v]
            if u_comp != v_comp and v_comp not in condensed_dag_set[u_comp]:
                condensed_dag_set[u_comp].add(v_comp)
                in_degree[v_comp] += 1

    condensed_dag: dict[int, list[int]] = {
        i: sorted(condensed_dag_set[i]) for i in range(len(components))
    }

    # Kahn's algorithm for topological sort of condensed DAG
    queue: deque[int] = deque([i for i, deg in in_degree.items() if deg == 0])
    topological_order: list[int] = []

    while queue:
        curr = queue.popleft()
        topological_order.append(curr)
        for nxt in condensed_dag[curr]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    return SCCResult(
        components=components,
        node_to_component=node_to_comp,
        is_dag=is_dag,
        cyclic_components=cyclic_comps,
        condensed_dag=condensed_dag,
        topological_order=topological_order,
    )
