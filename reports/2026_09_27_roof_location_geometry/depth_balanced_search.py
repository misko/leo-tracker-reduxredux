"""Measured-priority search with deterministic round-robin depth balancing.

Every queued priority is an observed score.  Separate heaps prevent a deeply
refined basin from permanently competing with all still-coarse alternatives.
"""
from __future__ import annotations

import heapq
import math

import numpy as np

from measured_search import SearchResult, representative


def search(evaluate_points, *, radius_km=500., region_size_km=1000.,
           levels_km=(100., 50., 25., 12.5, 6.25, 3.125, 1.5625),
           budget_points=160):
    levels = tuple(map(float, levels_km))
    if not levels or not all(math.isfinite(value) and value > 0 for value in levels):
        raise ValueError("invalid grid levels")
    if not 0 < radius_km <= region_size_km / 2 or budget_points <= 0:
        raise ValueError("invalid disk or budget")
    if any(not np.isclose(parent, 2 * child)
           for parent, child in zip(levels, levels[1:])):
        raise ValueError("levels must halve")
    count = round(region_size_km / levels[0])
    if not np.isclose(count * levels[0], region_size_km):
        raise ValueError("coarse spacing must divide box")
    axis = (np.arange(count) + .5) * levels[0] - region_size_km / 2
    initial = [(float(east), float(north), 0) for north in axis for east in axis
               if representative(east, north, levels[0], radius_km) is not None]
    initial_points = {representative(east, north, levels[0], radius_km)
                      for east, north, _ in initial}
    if len(initial_points) > budget_points:
        raise ValueError("budget smaller than initial measured coverage")

    cache = {}
    trace = []
    heaps = [[] for _ in levels[:-1]]
    finest = set()
    serial = 0
    cut_short = False
    cursor = 0

    def evaluate_and_queue(cells):
        nonlocal serial, cut_short
        for east, north, depth in cells:
            point = representative(east, north, levels[depth], radius_km)
            if point is None:
                continue
            if point not in cache:
                if len(cache) >= budget_points:
                    cut_short = True
                    return
                rows = tuple(evaluate_points(np.asarray([point])))
                if len(rows) != 1 or (rows[0].east_km, rows[0].north_km) != point:
                    raise ValueError("evaluator changed coordinates")
                score = float(rows[0].weighted_mse_hz2)
                if not math.isfinite(score):
                    raise ValueError("nonfinite search score")
                cache[point] = rows[0]
                trace.append({
                    "event": "evaluate", "depth": depth,
                    "spacing_km": levels[depth], "east_km": point[0],
                    "north_km": point[1], "objective": score,
                    "cell_east_km": east, "cell_north_km": north,
                })
            if depth == len(levels) - 1:
                finest.add(point)
            else:
                heapq.heappush(
                    heaps[depth],
                    (float(cache[point].weighted_mse_hz2), east, north,
                     serial, point))
                serial += 1

    evaluate_and_queue(initial)
    while any(heaps) and len(cache) < budget_points:
        # Start at the next scheduled depth, skipping empty levels but retaining
        # the deterministic round-robin phase across iterations.
        selected_depth = next(
            (depth for offset in range(len(heaps))
             if heaps[depth := (cursor + offset) % len(heaps)]), None)
        if selected_depth is None:
            break
        score, east, north, _, point = heapq.heappop(heaps[selected_depth])
        cursor = (selected_depth + 1) % len(heaps)
        trace.append({
            "event": "pop", "depth": selected_depth,
            "east_km": east, "north_km": north,
            "representative": list(point), "measured_priority": score,
        })
        offset = levels[selected_depth] / 4
        evaluate_and_queue([
            (east + de, north + dn, selected_depth + 1)
            for de, dn in ((-offset, -offset), (-offset, offset),
                           (offset, -offset), (offset, offset))])

    ranked = tuple(sorted(
        cache.values(),
        key=lambda row: (row.weighted_mse_hz2, row.east_km, row.north_km)))
    fine = tuple(row for row in ranked
                 if (row.east_km, row.north_km) in finest)
    complete = not any(heaps) and not cut_short
    return SearchResult(
        complete,
        "frontier-exhausted" if complete else "point-budget-reached",
        ranked[0], fine[0] if fine else None, ranked, fine, tuple(trace))
