"""Regular-grid state interpolation for the long-cohort cache."""

from __future__ import annotations

import numpy as np


def interpolate_states(cache, offsets_ns):
    """Linearly interpolate cached ECEF states at rounded query epochs."""
    grid = np.asarray(cache["receive_plus_tau_offset_ns"], dtype=np.int64)
    query = np.asarray(offsets_ns, dtype=np.int64)
    if len(grid) < 2 or np.any(query < grid[0]) or np.any(query > grid[-1]):
        raise ValueError("query lies outside regular cache")
    step = grid[1] - grid[0]
    if step <= 0 or not np.all(np.diff(grid) == step):
        raise ValueError("regular increasing grid required")
    fraction = (query - grid[0]) / step
    low = np.floor(fraction).astype(int)
    high = np.minimum(low + 1, len(grid) - 1)
    weight = fraction - low
    position = cache["position_ecef_km"][:, low] * (1 - weight)[None, :, None]
    position += cache["position_ecef_km"][:, high] * weight[None, :, None]
    velocity = cache["velocity_ecef_km_s"][:, low] * (1 - weight)[None, :, None]
    velocity += cache["velocity_ecef_km_s"][:, high] * weight[None, :, None]
    return position, velocity
