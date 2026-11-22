"""Bound a fixed-state white curve nominee using four original observations."""

from math import sqrt

import numpy as np

from leo.analysis.research.retained_track_likelihood import BIAS, NOISE, PERIOD
from tools.pipeline_eval.variants.algo08_streamed_nomination import white_nomination

MAX_OBSERVATIONS = 4096
MAX_SAMPLE_HZ = 2**24
WEIGHT = 1 / NOISE
INNOVATION_SLACK = 2**-18
ALIAS_SLACK_HZ = 2**-11
SUM_SLACK = 2**-28


def witness_indexes(count):
    return np.linspace(0, count - 1, 4, dtype=int) if count > 4 else np.arange(count)


def lower_scores(observed, predicted, full_normalizer):
    """Enclose full stock costs after projecting four unchanged model rows."""
    raw = observed - predicted
    size = raw.shape[1]
    centered = np.zeros(len(raw))
    for i in range(size):
        for j in range(i):
            difference = np.abs((raw[:, i] - raw[:, j]) * WEIGHT)
            centered += np.maximum(0., difference - 2 * INNOVATION_SLACK) ** 2
    mean = raw.mean(axis=1)
    nearest = np.rint(-mean / PERIOD)
    location = np.abs(mean + nearest * PERIOD) * WEIGHT
    bias_lower = np.maximum(0., location - INNOVATION_SLACK) ** 2 / (1 / size + (BIAS * WEIGHT)**2)
    optimistic = (centered / size + bias_lower) * (1. - SUM_SLACK) - SUM_SLACK
    return np.nextafter(np.maximum(0., optimistic) + full_normalizer, -np.inf)


def can_enclose(observed, predicted, whitening):
    inverse, volume = whitening
    size = len(observed)
    return (
        4 < size <= MAX_OBSERVATIONS
        and observed.dtype == predicted.dtype == inverse.dtype == np.float64
        and volume == 0.
        and inverse.shape == (size, size)
        and np.count_nonzero(inverse) == size
        and np.all(np.diag(inverse) == WEIGHT)
        and np.all(np.abs(observed) <= MAX_SAMPLE_HZ)
        and np.all(np.abs(predicted) <= MAX_SAMPLE_HZ)
    )


def _score_radius(cost, count):
    # Enclose altered summation in the compact full-data profile when its
    # alias is fixed. Apply the norm perturbation before its square.
    radius = 4 * INNOVATION_SLACK * sqrt(count + 1)
    return radius * (2 * np.sqrt(np.maximum(0., cost)) + radius) + SUM_SLACK * (1 + abs(cost))


def full_profiles(observed, predicted, visible, whitening, indexes, *, check_alias=True):
    columns = predicted.flags.f_contiguous and not predicted.flags.c_contiguous
    # A singleton would otherwise change the axis reduction to contiguous.
    padded = columns and len(indexes) == 1
    selected = np.repeat(indexes, 2) if padded else indexes
    data = predicted[selected]
    if columns:
        data = np.asfortranarray(data)
    boundary = False
    if check_alias:
        mean = (observed - data).mean(axis=1)
        folded = np.abs(mean - np.rint(mean / PERIOD) * PERIOD)
        boundary = bool(np.any(np.abs(folded - PERIOD / 2) <= ALIAS_SLACK_HZ))
    result = white_nomination(observed, data, visible[selected], whitening)
    return result, boundary


def subset_nomination(observed, predicted, visible, whitening, metrics):
    """Measure the bound and original full profiles of all potential winners."""
    count, tracks = len(observed), len(predicted)
    metrics["dense_candidates"] += tracks
    metrics["dense_profile_cells"] += predicted.size

    def fallback(reason):
        metrics["fallback_" + reason] += 1
        metrics["full_candidates"] += tracks
        metrics["full_profile_cells"] += predicted.size
        j, cost, alias, bias, rms, innovations = white_nomination(
            observed, predicted, visible, whitening,
        )
        return j, cost[j], alias[j], bias, rms, innovations

    if not visible.any() or not can_enclose(observed, predicted, whitening):
        return fallback("domain_or_visibility")

    witness = witness_indexes(count)
    one = np.diag(whitening[0])
    normalizer = np.log1p(BIAS**2 * (one @ one))
    bound = lower_scores(observed[witness], predicted[:, witness], normalizer)
    metrics["witness_cells"] += tracks * len(witness)
    coarse = np.argmin(np.where(visible, bound, np.inf))
    (j, cost, _, _, _, _), boundary = full_profiles(
        observed, predicted, visible, whitening, np.array([coarse]),
    )
    metrics["full_candidates"] += 1
    metrics["full_profile_cells"] += count
    if boundary:
        return fallback("incumbent_alias")
    upper = cost[j] + _score_radius(cost[j], count)
    finalists = np.flatnonzero(visible & (bound <= upper))
    if not len(finalists) or coarse not in finalists:
        return fallback("enclosure")

    (j, cost, alias, bias, rms, innovations), boundary = full_profiles(
        observed, predicted, visible, whitening, finalists,
    )
    metrics["full_candidates"] += len(finalists)
    metrics["full_profile_cells"] += len(finalists) * count
    if boundary:
        return fallback("finalist_alias")
    if len(finalists) >= 2:
        competitive = cost - _score_radius(cost, count)
        competitive[j] = np.inf
        if np.min(competitive) <= cost[j] + _score_radius(cost[j], count):
            return fallback("rounding_or_tie")
    return finalists[j], cost[j], alias[j], bias, rms, innovations
