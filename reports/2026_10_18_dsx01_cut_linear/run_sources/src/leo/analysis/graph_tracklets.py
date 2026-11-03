"""Alias-aware, second-order DAG paths followed by polynomial validation.

Discovery uses observations and velocity-continuity edge states, not polynomial
RANSAC proposals. Dynamic programming finds an exact best path for the current
additive graph costs. Repeated exclusive extraction is greedy path packing;
neither packing nor subsequent polynomial segmentation is globally optimal.
"""

import numpy as np

from leo.analysis.polynomial_tracklets import (
    TrackConfig,
    _diagnose,
    _predict,
    _refine,
    _wrap,
)
from leo.analysis.tracklet_fitting import finish_lane, prepare_lane


def _graph(t, y, cfg):
    """Edges carry alias-resolved slopes over a bounded local time horizon."""
    sources, targets, durations, velocities = [], [], [], []
    for target in range(len(t)):
        first = np.searchsorted(t, t[target] - cfg.max_gap_s)
        previous = np.arange(first, target)
        dt = t[target] - t[previous]
        keep = dt >= 0.15
        previous, dt = previous[keep], dt[keep]
        # Bound graph density without discarding all long-baseline edges.
        if len(previous) > 48:
            pick = np.unique(np.linspace(0, len(previous) - 1, 48).astype(int))
            previous, dt = previous[pick], dt[pick]
        delta = _wrap(y[target] - y[previous], cfg.alias_spacing_hz)
        branches = int(np.ceil(cfg.max_slope_hz_s * cfg.max_gap_s / cfg.alias_spacing_hz))
        for branch in range(-branches, branches + 1):
            slope = (delta + branch * cfg.alias_spacing_hz) / dt
            keep = np.abs(slope) <= cfg.max_slope_hz_s
            sources.extend(previous[keep].tolist())
            targets.extend([target] * int(keep.sum()))
            durations.extend(dt[keep].tolist())
            velocities.extend(slope[keep].tolist())
    source = np.asarray(sources, int)
    target = np.asarray(targets, int)
    dt, velocity = np.asarray(durations), np.asarray(velocities)
    incoming = [np.flatnonzero(target == j) for j in range(len(t))]
    outgoing = [np.flatnonzero(source == j) for j in range(len(t))]
    return source, target, dt, velocity, incoming, outgoing


def _best_path(t, y, graph, available, edge_enabled, cfg):
    """Second-order Viterbi recurrence over consecutive-observation edges."""
    source, target, dt, velocity, incoming, outgoing = graph
    allowed = available[source] & available[target] & edge_enabled
    reward = cfg.association_sigma**2
    score = np.full(len(source), -np.inf)
    predecessor = np.full(len(source), -1, int)
    count = np.zeros(len(source), int)
    start = np.zeros(len(source), int)
    for node in range(len(t)):
        after = outgoing[node][allowed[outgoing[node]]]
        if not len(after):
            continue
        gap_cost = 0.05 * dt[after]
        score[after] = 2 * reward - cfg.track_penalty - gap_cost
        count[after], start[after] = 2, node
        before = incoming[node][allowed[incoming[node]]]
        if not len(before):
            continue
        a, b = dt[before, None], dt[None, after]
        variance = 2 * cfg.noise_sigma_hz**2 * (1 / a**2 + 1 / b**2 + 1 / (a * b))
        # An explicit discovery prior, not an extra fitted likelihood scale:
        # modest Doppler acceleration can connect local polynomial fragments.
        variance += (20 * (a + b) / 2) ** 2
        change = velocity[before, None] - velocity[None, after]
        transition = 2 * change**2 / variance
        candidates = score[before, None] + reward - gap_cost - transition
        winner = np.argmax(candidates, axis=0)
        value = candidates[winner, np.arange(len(after))]
        improved = value > score[after]
        selected = after[improved]
        parent = before[winner[improved]]
        score[selected] = value[improved]
        predecessor[selected] = parent
        count[selected] = count[parent] + 1
        start[selected] = start[parent]
    usable = np.flatnonzero(
        (count >= cfg.min_points)
        & (t[target] - t[start] >= cfg.min_span_s)
        & (score > 0)
    )
    if not len(usable):
        return np.array([], int), np.array([]), np.array([], int), 0.0
    last = usable[np.argmax(score[usable])]
    value = float(score[last])
    path = [int(target[last])]
    edges = []
    while last >= 0:
        edges.append(last)
        path.append(int(source[last]))
        last = predecessor[last]
    path, edges = np.asarray(path[::-1], int), np.asarray(edges[::-1], int)
    lifted = y[path[0]] + np.r_[0.0, np.cumsum(velocity[edges] * dt[edges])]
    return path, lifted, edges, value


def _path_models(t, y, path, lifted, available, cfg, depth=0):
    if len(path) < cfg.min_points or np.ptp(t[path]) < cfg.min_span_s:
        return []
    model = _refine(t, y, path, lifted, cfg, grow=False)
    if model is not None:
        # Grow only from a polynomial discovered through a graph path, keeping
        # all previously accepted observations unavailable to this candidate.
        grown = _refine(t, y, model["indices"], _predict(model, t[model["indices"]]), cfg)
        if grown is not None:
            ix = grown["indices"][available[grown["indices"]]]
            grown = _refine(t, y, ix, _predict(grown, t[ix]), cfg, grow=False)
            if grown is not None:
                model = grown
        if not _diagnose(model, t, y, cfg)["quality_flags"]:
            return [model]
    if depth < 5 and len(path) >= 2 * cfg.min_points and np.ptp(t[path]) >= 2 * cfg.min_span_s:
        middle = len(path) // 2
        children = (
            _path_models(t, y, path[:middle], lifted[:middle], available, cfg, depth + 1)
            + _path_models(t, y, path[middle:], lifted[middle:], available, cfg, depth + 1)
        )
        if children:
            return children
    return [model] if model is not None else []


def fit_lane(time_s, cfo_hz, config: TrackConfig | None = None):
    """Return the shared tracklet contract, retaining unresolved original rows."""
    cfg = config or TrackConfig()
    t, y, order, n_original = prepare_lane(time_s, cfo_hz)
    models = []
    paths, rejected = 0, 0
    if len(t) >= cfg.min_points and np.ptp(t) >= cfg.min_span_s:
        graph = _graph(t, y, cfg)
        available = np.ones(len(t), bool)
        edge_enabled = np.ones(len(graph[0]), bool)
        for _ in range(2 * cfg.max_tracks):
            if len(models) >= cfg.max_tracks:
                break
            path, lifted, edges, _ = _best_path(t, y, graph, available, edge_enabled, cfg)
            if not len(path):
                break
            paths += 1
            candidates = _path_models(t, y, path, lifted, available, cfg)
            # Forbid this exact edge chain, retaining rejected observations for
            # alternative paths. Only polynomial members acquire ownership.
            edge_enabled[edges] = False
            if not candidates:
                rejected += 1
            for candidate in candidates:
                if len(models) >= cfg.max_tracks:
                    break
                models.append(candidate)
                available[candidate["indices"]] = False
    return finish_lane(
        t, y, order, n_original, models, cfg,
        method="graph_second_order_greedy_path_packing",
        diagnostics={
            "graph_paths_extracted": paths,
            "graph_paths_rejected": rejected,
            "discovery_acceleration_scale_hz_s2": 20.0,
            "limitations": [
                "greedy exclusive path packing, not a globally optimal flow",
                "additive graph cost precedes nonadditive polynomial validation",
                "bounded alternative search may leave recoverable points unresolved",
            ],
        },
    )
