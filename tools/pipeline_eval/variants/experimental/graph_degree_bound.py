"""Exact cost and support bounds for the Graph tracklet degree search."""

import numpy as np

from leo.analysis import polynomial_tracklets as poly


def best_piece(t, y, indices, prediction, cfg):
    """Keep the original fixed-support fits, wrapped residuals and slope test."""
    n = len(indices)
    if n < cfg.min_points:
        return None
    support = t[indices]
    times = np.unique(support)
    if len(times) < 3 or np.ptp(times) < cfg.min_span_s:
        return None
    highest = min(cfg.max_degree, n // cfg.points_per_coefficient - 1, len(times) // 2 - 1)
    if highest >= 2 and np.max(np.diff(times)) > 0.6 * np.ptp(times):
        highest = 1
    observed = y[indices]
    lifted = prediction + poly._wrap(observed - prediction, cfg.alias_spacing_hz)
    penalty = np.log(max(n, 2))
    best, best_cost = None, float("inf")
    for degree in range(highest + 1):
        floor = (degree + 1) * penalty
        if floor >= best_cost:
            break
        piece = poly._piece(t, lifted, indices, degree)
        residual = poly._wrap(observed - poly._predict(piece, support), cfg.alias_spacing_hz)
        cost = float(np.sum((residual / cfg.noise_sigma_hz) ** 2) + floor)
        if cost < best_cost and poly._bounded_slope(piece, t, cfg):
            best, best_cost = piece, cost
    return best
