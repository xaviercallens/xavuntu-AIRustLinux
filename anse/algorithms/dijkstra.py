"""
Production-grade Dijkstra's Shortest Path Algorithm for weighted graphs.

Implements single-source shortest path search with binary min-heap priority queue,
visited set pruning, early target termination, and negative edge detection.
Conforms to SPEC-ALG-01 and Anti-Stub Guard rules.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T", bound=Hashable)


@dataclass(frozen=True)
class ShortestPathResult(Generic[T]):
    """
    Immutable container for Dijkstra shortest path results.

    Attributes:
        source: The origin vertex.
        distances: Mapping of reachable vertices to their shortest distance.
        predecessors: Mapping of vertices to their immediate predecessor along the shortest path.
        settled_count: Number of vertices settled during search execution.
    """

    source: T
    distances: dict[T, float]
    predecessors: dict[T, T | None]
    settled_count: int

    def get_distance(self, target: T) -> float:
        """
        Return the shortest distance to the target vertex.

        Returns math.inf if the target is unreachable from the source.
        """
        return self.distances.get(target, math.inf)

    def is_reachable(self, target: T) -> bool:
        """Return True if target has a finite distance path from source."""
        return target in self.distances and not math.isinf(self.distances[target])

    def get_path(self, target: T) -> list[T] | None:
        """
        Reconstruct the ordered shortest path from source to target [source, ..., target].

        Returns None if target is unreachable from source.
        """
        if not self.is_reachable(target):
            return None

        path: list[T] = []
        curr: T | None = target
        visited_nodes: set[T] = set()

        while curr is not None:
            if curr in visited_nodes:
                # Loop safety check in predecessor chain
                break
            visited_nodes.add(curr)
            path.append(curr)
            if curr == self.source:
                break
            curr = self.predecessors.get(curr)

        if not path or path[-1] != self.source:
            return None

        path.reverse()
        return path


def dijkstra_shortest_paths(
    graph: Mapping[T, Iterable[tuple[T, float]]],
    source: T,
    target: T | None = None,
) -> ShortestPathResult[T]:
    """
    Compute single-source shortest paths on a directed or undirected weighted graph.

    Args:
        graph: Adjacency mapping where graph[u] yields (v, weight) tuples.
        source: The starting vertex.
        target: Optional destination vertex. If specified, search terminates
                early once target is settled.

    Returns:
        ShortestPathResult[T] containing shortest distances and path reconstructions.

    Raises:
        ValueError: If any negative edge weight is encountered.
    """
    distances: dict[T, float] = {source: 0.0}
    predecessors: dict[T, T | None] = {source: None}
    visited: set[T] = set()
    settled_count: int = 0

    # Priority queue stores tuples of (current_distance, node)
    pq: list[tuple[float, T]] = [(0.0, source)]

    while pq:
        curr_dist, u = heapq.heappop(pq)

        if u in visited:
            continue

        visited.add(u)
        settled_count += 1

        # Target early-termination check
        if target is not None and u == target:
            break

        # If current distance in heap is strictly greater than recorded distance, skip
        if curr_dist > distances.get(u, math.inf):
            continue

        neighbors = graph.get(u, ())
        for v, weight in neighbors:
            if weight < 0:
                raise ValueError(
                    f"Negative edge weight encountered ({u} -> {v}: {weight}). "
                    "Dijkstra's algorithm requires non-negative edge weights."
                )

            if v in visited:
                continue

            new_dist = curr_dist + weight
            if new_dist < distances.get(v, math.inf):
                distances[v] = new_dist
                predecessors[v] = u
                heapq.heappush(pq, (new_dist, v))

    return ShortestPathResult(
        source=source,
        distances=distances,
        predecessors=predecessors,
        settled_count=settled_count,
    )
