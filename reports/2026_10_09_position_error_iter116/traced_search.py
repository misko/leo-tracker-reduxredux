"""Research copy of the production heap policy, with a deterministic event port."""

import heapq

import numpy as np

from leo.analysis.regional_position_search import SpatialEvaluation, SpatialSearch


def hierarchical_search(evaluate, *, radius_km, levels_km, budget_points, edge_priority, observer):
    if tuple(levels_km) != (40.0, 20.0, 10.0, 5.0) or edge_priority != "nearest":
        raise ValueError("only the frozen hard60 hierarchy is supported")
    if not 0 < radius_km <= 500 or budget_points < 1:
        raise ValueError("invalid search bounds")
    levels = np.asarray(levels_km)
    axis = (np.arange(round(1000 / levels[0])) + 0.5) * levels[0] - 500
    rows, heap = {}, []

    def intersects(e, n, spacing):
        return np.hypot(max(abs(e) - spacing / 2, 0), max(abs(n) - spacing / 2, 0)) <= radius_km

    def record(e, n, depth):
        score = float(evaluate(e, n))
        if not np.isfinite(score):
            raise ValueError("nonfinite score")
        rows[(e, n)] = SpatialEvaluation(e, n, float(levels[depth]), score)
        observer(dict(event="evaluated", east=e, north=n, depth=depth, score=score))
        return score

    cells = [(float(e), float(n)) for n in axis for e in axis if intersects(e, n, levels[0])]
    inside = [(e, n) for e, n in cells if np.hypot(e, n) <= radius_km]
    if len(inside) > budget_points:
        raise ValueError("budget cannot evaluate initial centers")
    for e, n in inside:
        record(e, n, 0)
    for e, n in cells:
        if (e, n) in rows:
            score = rows[(e, n)].score
        else:
            nearest = min(
                rows.values(),
                key=lambda p: (
                    (p.east_km - e) ** 2 + (p.north_km - n) ** 2,
                    p.score,
                    p.east_km,
                    p.north_km,
                ),
            )
            score = nearest.score
        heapq.heappush(heap, (score, e, n, 0))
    while heap and len(rows) < budget_points:
        parent_score, e, n, depth = heapq.heappop(heap)
        observer(dict(event="pop", east=e, north=n, depth=depth, score=parent_score))
        if depth == len(levels) - 1:
            continue
        delta, spacing = levels[depth] / 4, levels[depth + 1]
        for de, dn in ((-delta, -delta), (-delta, delta), (delta, -delta), (delta, delta)):
            ce, cn = float(e + de), float(n + dn)
            if not intersects(ce, cn, spacing):
                continue
            score = parent_score
            if np.hypot(ce, cn) <= radius_km and len(rows) < budget_points:
                score = record(ce, cn, depth + 1)
            observer(
                dict(
                    event="child",
                    parent=[e, n, depth],
                    east=ce,
                    north=cn,
                    depth=depth + 1,
                    score=score,
                    evaluated=(ce, cn) in rows,
                )
            )
            heapq.heappush(heap, (score, ce, cn, depth + 1))
    observer(
        dict(
            event="deferred",
            cells=[dict(score=s, east=e, north=n, depth=d) for s, e, n, d in sorted(heap)],
        )
    )
    observer(
        dict(
            event="ranks",
            rows=[
                dict(rank=i + 1, east=p.east_km, north=p.north_km, score=p.score)
                for i, p in enumerate(
                    sorted(rows.values(), key=lambda p: (p.score, p.east_km, p.north_km))
                )
            ],
        )
    )
    return SpatialSearch(
        tuple(rows.values()), len(heap), "point-budget" if heap else "frontier-exhausted"
    )
