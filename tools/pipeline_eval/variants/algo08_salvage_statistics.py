"""Profile coarse salvage phases from per-track weighted quadratic statistics."""

from collections import Counter
from contextlib import contextmanager
from functools import partial
from unittest.mock import patch

import numpy as np

from leo.analysis.research.retained_track_likelihood import BIAS, PERIOD
from tools.pipeline_eval.variants import v5_tiled_salvage


def phase_costs(measured, noise, frequency, slope, rf_ratio, phases):
    """Compute diagonal-whitened, native-alias, Gaussian-bias profile costs."""
    base = measured - rf_ratio * frequency
    gradient = -rf_ratio * slope
    weighted_base = base / noise
    weighted_gradient = gradient / noise
    inverse = 1 / noise
    information = inverse @ inverse
    base_mean = weighted_base @ inverse / information
    gradient_mean = weighted_gradient @ inverse / information
    weighted_base -= base_mean[:, None] * inverse
    weighted_gradient -= gradient_mean[:, None] * inverse

    base_ss = np.einsum("ij,ij->i", weighted_base, weighted_base)
    cross = np.einsum("ij,ij->i", weighted_base, weighted_gradient)
    gradient_ss = np.einsum("ij,ij->i", weighted_gradient, weighted_gradient)
    mean = base_mean[:, None] + gradient_mean[:, None] * phases
    rolls = -(base.mean(axis=1)[:, None] + gradient.mean(axis=1)[:, None] * phases) / PERIOD
    aliases = np.rint(rolls)
    mean += aliases * PERIOD
    cost = base_ss[:, None] + phases * (2 * cross[:, None] + gradient_ss[:, None] * phases)
    cost += information / (1 + information * BIAS**2) * mean**2
    cost += np.log1p(BIAS**2 * information)
    return cost, rolls, aliases


def coarse_scores(stock, profile, measured, noise, frequency, elevation, slope, rf_ratio,
                  phases, mask, counters):
    original = measured, noise, frequency, elevation, slope, rf_ratio, phases, mask
    if mask is not None:
        measured, noise = measured[mask], noise[mask]
        frequency, elevation, slope = frequency[:, mask], elevation[:, mask], slope[:, mask]
    quota = 30 if mask is None else 10
    counters["statistics_windows"] += 1

    def replay(reason):
        counters[reason] += 1
        return stock(profile, *original, counters)

    if not all(np.isfinite(a).all() for a in (measured, noise, frequency, elevation, slope)):
        return replay("nonfinite_replays")
    cost, rolls, aliases = phase_costs(measured, noise, frequency, slope, rf_ratio, phases)
    if not np.isfinite(cost).all():
        return replay("nonfinite_replays")
    # Back off near possible floating-point rank changes. These margins are
    # numerical guards, independent of position, RF evidence and case identity.
    scale = np.abs(measured) + abs(rf_ratio) * (
        np.abs(frequency) + np.abs(slope) * np.max(np.abs(phases))
    )
    rounding = 64 * np.finfo(float).eps * (len(measured) + 8)
    distance_to_half_alias = (0.5 - np.abs(rolls - aliases)) * PERIOD
    if np.any(distance_to_half_alias <= rounding * scale.max(axis=1)[:, None]):
        return replay("alias_replays")
    scores = (cost + phases**2 / 9).min(axis=1)
    scores[elevation.max(axis=1) < 0] = np.inf
    finite = np.sort(scores[np.isfinite(scores)])
    if len(finite) < min(quota, len(scores)):
        return replay("visibility_replays")
    if len(finite) > quota:
        score_rounding = rounding * np.max(np.sum(((scale + PERIOD) / noise)**2, axis=1))
        if finite[quota] - finite[quota - 1] <= 2 * score_rounding:
            return replay("rank_replays")
    return scores


@contextmanager
def salvage_statistics():
    """Replace only the coarse profile in the research salvage port."""
    from leo.analysis.localization_v3 import conservative_recovery

    counters, shortlists = Counter(), []
    stock = v5_tiled_salvage.coarse_scores
    salvage = partial(v5_tiled_salvage.salvage, conservative_recovery, counters, shortlists)
    with (
        patch.object(v5_tiled_salvage, "coarse_scores", partial(coarse_scores, stock)),
        patch.object(conservative_recovery, "salvage", salvage),
    ):
        yield counters, shortlists
