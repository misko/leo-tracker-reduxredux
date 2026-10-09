"""Synthetic research primitive for fixed-observer piecewise-linear horizon paths."""

import numpy as np


def horizon_events(nodes, margins, query_start, query_step, *, maximum_alpha=1.0):
    """Zeros of an interpolated unnormalized horizon margin along a timing step.

    nodes are orbit times; margins are dot(position-site, up) at those nodes.
    The observer must remain fixed. This is not a moving-position root finder.
    Returns events including tangencies; caller decides one-sided mask changes.
    """
    nodes, margins = np.asarray(nodes, float), np.asarray(margins, float)
    if (
        nodes.ndim != 1
        or len(nodes) < 2
        or margins.shape != nodes.shape
        or not np.isfinite(nodes).all()
        or not np.isfinite(margins).all()
        or np.any(np.diff(nodes) <= 0)
    ):
        raise ValueError("finite ordered piecewise-linear path required")
    if not np.isfinite([query_start, query_step, maximum_alpha]).all() or maximum_alpha <= 0:
        raise ValueError("invalid line interval")
    end = query_start + maximum_alpha * query_step
    if min(query_start, end) < nodes[0] or max(query_start, end) > nodes[-1]:
        raise ValueError("line exceeds ephemeris support")
    initial = float(np.interp(query_start, nodes, margins))
    if query_step == 0:
        return dict(events=[], initial_boundary=initial == 0, flat_boundary=initial == 0)
    breaks = [0.0, maximum_alpha]
    breaks.extend(
        float((t - query_start) / query_step)
        for t in nodes
        if 0 < (t - query_start) / query_step < maximum_alpha
    )
    breaks = np.array(sorted(set(breaks)))
    values = np.interp(query_start + breaks * query_step, nodes, margins)
    events = []
    flat = False
    for a, b, left, right in zip(breaks[:-1], breaks[1:], values[:-1], values[1:], strict=True):
        if left == 0 and right == 0:
            flat = True
        if left == 0 and a > 0:
            events.append(float(a))
        if left * right < 0:
            events.append(float(a + (b - a) * (-left) / (right - left)))
        if right == 0:
            events.append(float(b))
    return dict(events=sorted(set(events)), initial_boundary=initial == 0, flat_boundary=flat)


def open_cells(events, *, maximum_alpha=1.0):
    """Represent open cells, not artificial feasibility constraints or KKT claims."""
    values = np.asarray(events, float)
    if (
        values.ndim != 1
        or not np.isfinite(values).all()
        or np.any(values <= 0)
        or np.any(values > maximum_alpha)
    ):
        raise ValueError("invalid event fractions")
    boundaries = sorted(set([0.0, maximum_alpha, *values.tolist()]))
    return [(a, b) for a, b in zip(boundaries[:-1], boundaries[1:], strict=True) if b > a]
