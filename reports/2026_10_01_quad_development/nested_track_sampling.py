"""Deterministic time coverage that retains every baseline observation."""
import numpy as np


def nested_indices(times, baseline_indices, limit):
    times = np.asarray(times, dtype=float)
    base = np.asarray(baseline_indices)
    if times.ndim != 1 or not len(times) or not np.all(np.isfinite(times)):
        raise ValueError('Finite nonempty one-dimensional times required')
    if base.ndim != 1 or not len(base) or not np.issubdtype(base.dtype, np.integer):
        raise ValueError('Nonempty integer baseline indices required')
    if len(set(base.tolist())) != len(base) or np.any(base < 0) or np.any(base >= len(times)):
        raise ValueError('Invalid or repeated baseline index')
    if not isinstance(limit, (int, np.integer)) or isinstance(limit, bool) or limit < len(base):
        raise ValueError('Limit must retain the complete baseline')
    order = np.argsort(times, kind='stable')
    chosen = np.zeros(len(times), dtype=bool)
    chosen[base] = True
    distance = np.min(np.abs(times[:, None]-times[base][None, :]), axis=1)
    while chosen.sum() < min(limit, len(times)):
        scores = np.where(chosen, -np.inf, distance)
        index = order[np.argmax(scores[order])]
        chosen[index] = True
        distance = np.minimum(distance, np.abs(times-times[index]))
    return order[chosen[order]]
