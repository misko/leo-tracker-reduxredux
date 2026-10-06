"""Scalar-score best-first spatial hierarchy, independent of likelihood units.

Uses the baseline's aligned cell-halving policy and explicit point budget. A
score is an evaluated value, never a lower bound on the unexplored cell.
"""

import heapq
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SpatialEvaluation:
    east_km: float
    north_km: float
    spacing_km: float
    score: float


@dataclass(frozen=True)
class SpatialSearch:
    evaluations: tuple[SpatialEvaluation, ...]
    deferred_cells: int
    stop_reason: str

    @property
    def selected(self):
        return min(self.evaluations, key=lambda p: (p.score, p.east_km, p.north_km))


def hierarchical_search(
    evaluate: Callable[[float, float], float],
    *,
    radius_km=250.0,
    levels_km=(100.0, 50.0, 25.0, 12.5),
    budget_points=400,
):
    levels = np.asarray(levels_km, float)
    if (
        not np.isfinite(radius_km)
        or not 0 < radius_km <= 500
        or isinstance(budget_points, bool)
        or not isinstance(budget_points, int)
        or budget_points < 1
        or levels.ndim != 1
        or not len(levels)
        or not np.isfinite(levels).all()
        or np.any(levels <= 0)
        or not np.allclose(levels[:-1] / levels[1:], 2)
        or not np.isclose(1000 / levels[0], round(1000 / levels[0]))
    ):
        raise ValueError("invalid bounded spatial hierarchy")
    axis = (np.arange(round(1000 / levels[0])) + 0.5) * levels[0] - 500
    rows: dict[tuple[float, float], SpatialEvaluation] = {}
    heap: list[tuple[float, float, float, int]] = []

    def intersects(e, n, spacing):
        return np.hypot(max(abs(e) - spacing / 2, 0), max(abs(n) - spacing / 2, 0)) <= radius_km

    def record(e, n, depth):
        score = float(evaluate(e, n))
        if not np.isfinite(score):
            raise ValueError("spatial evaluator returned a nonfinite score")
        rows[(e, n)] = SpatialEvaluation(e, n, float(levels[depth]), score)
        return score

    cells = [(float(e), float(n)) for n in axis for e in axis if intersects(e, n, levels[0])]
    inside = [(e, n) for e, n in cells if np.hypot(e, n) <= radius_km]
    if len(inside) > budget_points:
        raise ValueError("budget cannot evaluate initial centers")
    for e, n in inside:
        record(e, n, 0)
    for e, n in cells:
        score = rows[(e, n)].score if (e, n) in rows else 0.0
        heapq.heappush(heap, (score, e, n, 0))
    while heap and len(rows) < budget_points:
        parent_score, e, n, depth = heapq.heappop(heap)
        if depth == len(levels) - 1:
            continue
        delta = levels[depth] / 4
        spacing = levels[depth + 1]
        for de, dn in ((-delta, -delta), (-delta, delta), (delta, -delta), (delta, delta)):
            ce, cn = float(e + de), float(n + dn)
            if not intersects(ce, cn, spacing):
                continue
            score = parent_score
            if np.hypot(ce, cn) <= radius_km and len(rows) < budget_points:
                score = record(ce, cn, depth + 1)
            heapq.heappush(heap, (score, ce, cn, depth + 1))
    return SpatialSearch(
        tuple(rows.values()), len(heap), "point-budget" if heap else "frontier-exhausted"
    )


def distinct_basins(search: SpatialSearch, *, count=3, minimum_separation_km=12.5):
    if count < 1 or minimum_separation_km <= 0:
        raise ValueError("positive basin count and separation required")
    selected: list[SpatialEvaluation] = []
    for row in sorted(search.evaluations, key=lambda p: (p.score, p.east_km, p.north_km)):
        if all(
            np.hypot(row.east_km - p.east_km, row.north_km - p.north_km) >= minimum_separation_km
            for p in selected
        ):
            selected.append(row)
            if len(selected) == count:
                break
    return tuple(selected)
