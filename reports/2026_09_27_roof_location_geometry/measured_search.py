"""Research-only bounded search: every queued cell has a measured priority.

Boundary-intersecting cells use a representative inside both the disk and cell.
No unevaluated cell receives a synthetic zero-loss priority. This is heuristic
best-first refinement, not a global-optimum guarantee or an interval bound.
"""
from dataclasses import dataclass
import heapq
import math
import numpy as np


@dataclass(frozen=True)
class SearchResult:
    complete: bool
    stop_reason: str
    global_incumbent: object
    finest_incumbent: object
    all_evaluations: tuple
    finest_evaluations: tuple
    trace: tuple


def representative(east, north, spacing, radius):
    center = np.array([east, north], float)
    closest = np.sign(center)*np.maximum(np.abs(center)-spacing/2, 0)
    if np.linalg.norm(closest) > radius:
        return None
    if np.linalg.norm(center) <= radius:
        return tuple(center)
    delta = center-closest
    a = float(delta@delta)
    b = float(2*(closest@delta))
    c = float(closest@closest-radius**2)
    fraction = (-b+math.sqrt(max(0., b*b-4*a*c)))/(2*a)
    point = closest+max(0., fraction-1e-12)*delta
    return tuple(map(float, point))


def search(evaluate_points, *, radius_km=500., region_size_km=1000.,
           levels_km=(100., 50., 25., 12.5, 6.25, 3.125, 1.5625), budget_points=160):
    levels = tuple(map(float, levels_km))
    if not levels or not all(math.isfinite(v) and v > 0 for v in levels):
        raise ValueError('invalid grid levels')
    if not 0 < radius_km <= region_size_km/2 or budget_points <= 0:
        raise ValueError('invalid disk or budget')
    if any(not np.isclose(a, 2*b) for a, b in zip(levels, levels[1:])):
        raise ValueError('levels must halve')
    count = round(region_size_km/levels[0])
    if not np.isclose(count*levels[0], region_size_km):
        raise ValueError('coarse spacing must divide box')
    axis = (np.arange(count)+.5)*levels[0]-region_size_km/2
    initial = [(float(e), float(n), 0) for n in axis for e in axis
               if representative(e, n, levels[0], radius_km) is not None]
    initial_points = {representative(e, n, levels[0], radius_km) for e, n, _ in initial}
    if len(initial_points) > budget_points:
        raise ValueError('budget smaller than initial measured coverage')
    cache = {}
    trace = []
    queue = []
    finest = set()
    serial = 0
    cut_short = False

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
                    raise ValueError('evaluator changed coordinates')
                score = float(rows[0].weighted_mse_hz2)
                if not math.isfinite(score):
                    raise ValueError('nonfinite search score')
                cache[point] = rows[0]
                trace.append(dict(event='evaluate', depth=depth, spacing_km=levels[depth],
                    east_km=point[0], north_km=point[1], objective=score,
                    cell_east_km=east, cell_north_km=north))
            if depth == len(levels)-1:
                finest.add(point)
            else:
                heapq.heappush(queue, (cache[point].weighted_mse_hz2, east, north, serial, depth, point))
                serial += 1

    evaluate_and_queue(initial)
    while queue and len(cache) < budget_points:
        score, east, north, _, depth, point = heapq.heappop(queue)
        trace.append(dict(event='pop', depth=depth, east_km=east, north_km=north,
                          representative=list(point), measured_priority=score))
        offset = levels[depth]/4
        evaluate_and_queue([(east+de, north+dn, depth+1)
            for de, dn in ((-offset, -offset), (-offset, offset), (offset, -offset), (offset, offset))])
    ranked = tuple(sorted(cache.values(), key=lambda x: (x.weighted_mse_hz2, x.east_km, x.north_km)))
    fine = tuple(x for x in ranked if (x.east_km, x.north_km) in finest)
    complete = not queue and not cut_short
    return SearchResult(complete, 'frontier-exhausted' if complete else 'point-budget-reached',
        ranked[0], fine[0] if fine else None, ranked, fine, tuple(trace))
