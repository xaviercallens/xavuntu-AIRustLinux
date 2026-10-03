"""
Production-grade A* Search Algorithm with Admissible Heuristics.

Provides optimal pathfinding over discrete state-spaces, graphs, and spatial grids.
Supports consistent heuristics, visited pruning, tie-breaking, and negative cost checks.
Conforms to SPEC-ALG-ASTAR and Anti-Stub Guard invariants.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T", bound=Hashable)


@dataclass(frozen=True)
class AStarResult(Generic[T]):
    """
    Result container for A* search.

    Attributes:
        source: Initial origin state.
        target: Goal state reached.
        path: Ordered list of states from source to target.
        cost: Cumulative cost of the optimal path.
        nodes_settled: Number of states closed (settled) during search.
        nodes_generated: Total number of states discovered and added to the frontier.
    """

    source: T
    target: T
    path: list[T]
    cost: float
    nodes_settled: int
    nodes_generated: int


def astar_search(
    neighbors_fn: Callable[[T], Iterable[tuple[T, float]]],
    heuristic_fn: Callable[[T, T], float],
    source: T,
    target: T,
) -> AStarResult[T] | None:
    """
    Execute A* search from source to target.

    Args:
        neighbors_fn: Function returning an iterable of (neighbor_state, transition_cost).
        heuristic_fn: Admissible heuristic function h(current, target) -> float.
        source: Starting state.
        target: Desired target state.

    Returns:
        AStarResult[T] if a path exists, or None if the target is unreachable.

    Raises:
        ValueError: If any transition cost is negative.
    """
    if source == target:
        return AStarResult(
            source=source,
            target=target,
            path=[source],
            cost=0.0,
            nodes_settled=1,
            nodes_generated=1,
        )

    g_score: dict[T, float] = {source: 0.0}
    predecessors: dict[T, T] = {}
    closed_set: set[T] = set()

    nodes_settled: int = 0
    nodes_generated: int = 1
    counter: int = 0

    initial_h = heuristic_fn(source, target)
    # Heap entry: (f_score, h_score, tie_break_counter, node)
    # Preferring lower h_score breaks ties towards the goal
    pq: list[tuple[float, float, int, T]] = [(initial_h, initial_h, counter, source)]

    while pq:
        f_val, h_val, _, current = heapq.heappop(pq)

        if current in closed_set:
            continue

        closed_set.add(current)
        nodes_settled += 1

        if current == target:
            # Reconstruct path
            path: list[T] = [current]
            curr_node = current
            while curr_node in predecessors:
                curr_node = predecessors[curr_node]
                path.append(curr_node)
            path.reverse()
            return AStarResult(
                source=source,
                target=target,
                path=path,
                cost=g_score[current],
                nodes_settled=nodes_settled,
                nodes_generated=nodes_generated,
            )

        curr_g = g_score[current]

        for neighbor, edge_cost in neighbors_fn(current):
            if edge_cost < 0:
                raise ValueError(
                    f"Negative transition cost detected ({current} -> {neighbor}: {edge_cost}). "
                    "A* requires non-negative edge costs."
                )

            if neighbor in closed_set:
                continue

            tentative_g = curr_g + edge_cost
            if tentative_g < g_score.get(neighbor, math.inf):
                g_score[neighbor] = tentative_g
                predecessors[neighbor] = current
                h_cost = heuristic_fn(neighbor, target)
                f_cost = tentative_g + h_cost
                counter += 1
                nodes_generated += 1
                heapq.heappush(pq, (f_cost, h_cost, counter, neighbor))

    return None
