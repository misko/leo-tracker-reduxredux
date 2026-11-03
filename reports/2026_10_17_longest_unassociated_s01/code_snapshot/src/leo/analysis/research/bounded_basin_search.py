"""Deterministic regional coverage with equal local budgets for separated basins."""

import numpy as np


def bounded_basin_search(objective, *, radius_km=250.0, spacing_km=125.0, basins=3):
    """Rank a disk grid, then give each separated basin the same ten scales.

    A single four-neighbour sweep per scale keeps work bounded and guarantees
    that later basins are not starved by the first one. This is a proposal search,
    not a proof of a global or stationary optimum. No geographic truth is read.
    """
    if radius_km <= 0 or spacing_km <= 0 or basins < 1:
        raise ValueError("positive radius, spacing and basin count required")
    cache = {}

    def evaluate(point):
        key = tuple(np.round(point, 9))
        if np.linalg.norm(point) > radius_km + 1e-8:
            return np.inf
        if key not in cache:
            cache[key] = float(objective(np.asarray(point, float)))
        return cache[key]

    axis = np.arange(-radius_km, radius_km + spacing_km * 0.5, spacing_km)
    grid = [np.array([x, y]) for x in axis for y in axis if x * x + y * y <= radius_km**2 + 1e-8]
    grid.sort(key=lambda p: (float(p @ p), float(p[0]), float(p[1])))
    for point in grid:
        evaluate(point)
    starts = []
    for point in sorted(grid, key=evaluate):
        if all(np.linalg.norm(point - old) >= spacing_km for old in starts):
            starts.append(point)
        if len(starts) == basins:
            break
    endpoints = []
    scales = spacing_km / 2 ** np.arange(1, 11)
    for start in starts:
        point = start.copy()
        for step in scales:
            trials = [point + step * np.array(d) for d in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            trial = min(trials, key=evaluate)
            if evaluate(trial) < evaluate(point):
                point = trial
        endpoints.append(
            dict(start_east_north_km=start, east_north_km=point, score=evaluate(point))
        )
    return dict(
        endpoints=endpoints,
        trace=[dict(east_north_km=list(k), score=v) for k, v in cache.items()],
        evaluations=len(cache),
        maximum_evaluations=len(grid) + 40 * len(starts),
        coarse_evaluations=len(grid),
        scales_km=scales,
        basins=len(starts),
    )
