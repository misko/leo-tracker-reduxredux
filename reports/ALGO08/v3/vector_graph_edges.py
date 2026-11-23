"""Construct the ordered alias-aware graph in batches, before native path search."""

import numpy as np


def adjacency(nodes, permutation, size):
    if not size:
        return []
    counts = np.bincount(nodes, minlength=size)
    return np.split(permutation, counts.cumsum()[:-1])


def ordered_edges(t, y, config, original):
    """Same previous-time and alias ordering as the stock target-major graph."""
    size = len(t)
    nodes = np.arange(size)
    branches = int(np.ceil(config.max_slope_hz_s * config.max_gap_s / config.alias_spacing_hz))
    first = np.searchsorted(t, t - config.max_gap_s)
    counts = nodes - first
    if (
        t.dtype != np.float64
        or y.dtype != np.float64
        or np.any(counts < 0)
        or counts.sum() > 2_000_000
        or not 0 <= branches <= 4
    ):
        return original(t, y, config)

    target = np.repeat(nodes, counts)
    starts = counts.cumsum() - counts
    source = first[target] + np.arange(len(target)) - starts[target]
    dt = t[target] - t[source]
    keep = dt >= 0.15
    source, target, dt = source[keep], target[keep], dt[keep]

    # Match the original np.linspace rounding and endpoints for each distinct count.
    counts = np.bincount(target, minlength=size)
    if (counts > 48).any():
        selections = {
            n: np.linspace(0, n - 1, 48).astype(int) if n > 48 else np.arange(n)
            for n in np.unique(counts)
        }
        starts = counts.cumsum() - counts
        picks = np.concatenate(
            [start + selections[n] for start, n in zip(starts, counts, strict=True)]
        )
        source, target, dt = source[picks], target[picks], dt[picks]

    period = config.alias_spacing_hz
    delta = (y[target] - y[source] + period / 2) % period - period / 2
    rows, velocities = [], []
    for branch in range(-branches, branches + 1):
        slope = (delta + branch * period) / dt
        valid = np.flatnonzero(np.abs(slope) <= config.max_slope_hz_s)
        rows.append(valid)
        velocities.append(slope[valid])
    included = np.concatenate(rows)
    # The stock builder visits target, then signed alias, then previous observation.
    order = np.argsort(target[included], kind="stable")
    velocity = np.concatenate(velocities)[order]
    included = included[order]
    source, target, dt = source[included], target[included], dt[included]
    incoming = adjacency(target, np.arange(len(target)), size)
    outgoing = adjacency(source, np.argsort(source, kind="stable"), size)
    return source, target, dt, velocity, incoming, outgoing
