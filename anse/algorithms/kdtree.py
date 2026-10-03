"""
Production-grade k-D Tree for Vector Memory Retrieval.

Provides logarithmic expected-time nearest neighbor (1-NN) and k-NN search
in k-dimensional Euclidean spaces with hyper-rectangle sphere pruning.
Conforms to SPEC-ALG-KDTREE and Anti-Stub Guard invariants.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class KDNeighbor(Generic[T]):
    """
    Immutable container representing a discovered nearest neighbor.

    Attributes:
        point: Coordinates in k-dimensional Euclidean space.
        distance: Exact Euclidean distance from the query point.
        payload: User-attached metadata / item identifier.
    """

    point: tuple[float, ...]
    distance: float
    payload: T


class _KDNode(Generic[T]):
    """Internal node of the k-d tree."""

    __slots__ = ("point", "payload", "axis", "left", "right")

    def __init__(
        self,
        point: tuple[float, ...],
        payload: T,
        axis: int,
        left: _KDNode[T] | None = None,
        right: _KDNode[T] | None = None,
    ) -> None:
        self.point = point
        self.payload = payload
        self.axis = axis
        self.left = left
        self.right = right


def _sq_dist(p1: tuple[float, ...], p2: tuple[float, ...]) -> float:
    """Calculate squared Euclidean distance between two points."""
    return sum((a - b) * (a - b) for a, b in zip(p1, p2, strict=False))


class KDTree(Generic[T]):
    """
    A balanced k-dimensional spatial partitioning tree.

    Constructs a spatial search structure over N vectors in R^k with
    O(N log N) construction time and O(log N) expected search time.
    """

    def __init__(self, items: Sequence[tuple[Sequence[float], T]]) -> None:
        """
        Build the k-D tree from an iterable of (coordinates, payload) pairs.

        Raises:
            ValueError: If items have inconsistent dimensionalities.
        """
        if not items:
            self._root: _KDNode[T] | None = None
            self._dim: int = 0
            self._size: int = 0
            return

        first_pt = tuple(float(x) for x in items[0][0])
        self._dim = len(first_pt)
        if self._dim == 0:
            raise ValueError("Point dimensionality must be at least 1.")

        cleaned: list[tuple[tuple[float, ...], T]] = []
        for coords, payload in items:
            pt = tuple(float(x) for x in coords)
            if len(pt) != self._dim:
                raise ValueError(
                    f"Inconsistent dimensionality: expected {self._dim}, got {len(pt)} ({pt})."
                )
            cleaned.append((pt, payload))

        self._size = len(cleaned)
        self._root = self._build_tree(cleaned, depth=0)

    def _build_tree(
        self, items: list[tuple[tuple[float, ...], T]], depth: int
    ) -> _KDNode[T] | None:
        if not items:
            return None

        axis = depth % self._dim
        items.sort(key=lambda item: item[0][axis])
        median_idx = len(items) // 2

        median_pt, median_payload = items[median_idx]
        return _KDNode(
            point=median_pt,
            payload=median_payload,
            axis=axis,
            left=self._build_tree(items[:median_idx], depth + 1),
            right=self._build_tree(items[median_idx + 1 :], depth + 1),
        )

    def __len__(self) -> int:
        return self._size

    def query_nearest(self, query: Sequence[float]) -> KDNeighbor[T] | None:
        """
        Find the single nearest neighbor to the query coordinates.

        Returns:
            KDNeighbor[T] or None if the tree is empty.
        """
        if self._root is None:
            return None

        q_pt = tuple(float(x) for x in query)
        if len(q_pt) != self._dim:
            raise ValueError(f"Query dimensionality mismatch: expected {self._dim}, got {len(q_pt)}.")

        best_node: _KDNode[T] = self._root
        best_sq_dist: float = _sq_dist(q_pt, self._root.point)

        def _search(node: _KDNode[T] | None) -> None:
            nonlocal best_node, best_sq_dist
            if node is None:
                return

            dist_sq = _sq_dist(q_pt, node.point)
            if dist_sq < best_sq_dist:
                best_sq_dist = dist_sq
                best_node = node

            axis = node.axis
            diff = q_pt[axis] - node.point[axis]
            primary, secondary = (node.left, node.right) if diff <= 0 else (node.right, node.left)

            _search(primary)

            # Hyper-rectangle bounding sphere intersection test
            if diff * diff < best_sq_dist:
                _search(secondary)

        _search(self._root)
        return KDNeighbor(
            point=best_node.point,
            distance=math.sqrt(best_sq_dist),
            payload=best_node.payload,
        )

    def query_knn(self, query: Sequence[float], k: int) -> list[KDNeighbor[T]]:
        """
        Retrieve the top-k nearest neighbors ordered by distance ascending.

        Args:
            query: Coordinates in R^k.
            k: Number of neighbors to return (k > 0).

        Returns:
            List of up to k KDNeighbor[T] items.
        """
        if self._root is None or k <= 0:
            return []

        q_pt = tuple(float(x) for x in query)
        if len(q_pt) != self._dim:
            raise ValueError(f"Query dimensionality mismatch: expected {self._dim}, got {len(q_pt)}.")

        # Max-heap storing (-sq_dist, count, node)
        heap: list[tuple[float, int, _KDNode[T]]] = []
        counter: int = 0

        def _search(node: _KDNode[T] | None) -> None:
            nonlocal counter
            if node is None:
                return

            dist_sq = _sq_dist(q_pt, node.point)

            if len(heap) < k:
                counter += 1
                heapq.heappush(heap, (-dist_sq, counter, node))
            elif dist_sq < -heap[0][0]:
                counter += 1
                heapq.heapreplace(heap, (-dist_sq, counter, node))

            worst_sq_dist = -heap[0][0] if len(heap) == k else math.inf

            axis = node.axis
            diff = q_pt[axis] - node.point[axis]
            primary, secondary = (node.left, node.right) if diff <= 0 else (node.right, node.left)

            _search(primary)

            if diff * diff < worst_sq_dist or len(heap) < k:
                _search(secondary)

        _search(self._root)

        results: list[KDNeighbor[T]] = []
        while heap:
            neg_d_sq, _, node = heapq.heappop(heap)
            results.append(
                KDNeighbor(
                    point=node.point,
                    distance=math.sqrt(-neg_d_sq),
                    payload=node.payload,
                )
            )

        results.reverse()
        return results
