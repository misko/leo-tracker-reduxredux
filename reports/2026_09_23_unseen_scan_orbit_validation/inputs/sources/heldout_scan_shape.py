"""Offset-invariant scoring of entirely unseen scans at frozen model parameters.

No position, orbital correction or identity is optimized here. Orthogonal
contrasts remove the unobserved constant frequency offset in each segment.
This is a composite prediction of Doppler shape, not absolute carrier frequency.
"""

import numpy as np

from leo.analysis.research.regional_doppler import ScoreConfig, logsumexp


def score_unseen_shape(observed_hz, predicted_hz, segment, visible, catalogue_size, config=None):
    """Marginalize identities and a null over frozen candidate predictions.

    Sum-squared demeaned residuals equal sum-squared orthonormal contrasts.
    Their rank is n-1. Effective-count tempering prevents treating all closely
    spaced samples as independent; the result is not calibrated probability.
    """
    config = config or ScoreConfig()
    observed = np.asarray(observed_hz, float)
    predicted = np.asarray(predicted_hz, float)
    groups = np.asarray(segment)
    support = np.asarray(visible)
    if (
        observed.ndim != 1
        or predicted.ndim != 2
        or predicted.shape[1:] != observed.shape
        or groups.shape != observed.shape
        or support.shape != predicted.shape[:1]
        or support.dtype != bool
        or not np.all(np.isfinite(observed))
        or not np.all(np.isfinite(predicted))
        or catalogue_size < len(predicted)
        or catalogue_size < 1
        or observed.size < 2
    ):
        raise ValueError("aligned finite observations, predictions and candidate support required")
    unique = np.unique(groups)
    signal_ll = np.zeros(len(predicted))
    null_ll = 0.0
    rank_total = 0
    for group in unique:
        rows = groups == group
        rank = int(np.sum(rows)) - 1
        if rank < 1:
            raise ValueError("each segment requires at least two observations")
        rank_total += rank
        residual = observed[None, rows] - predicted[:, rows]
        residual -= np.mean(residual, axis=1, keepdims=True)
        null = observed[rows] - np.mean(observed[rows])
        count = min(config.effective_count, rank) / len(unique)
        signal_ll += (
            -0.5
            * count
            * (
                np.sum(residual**2, axis=1) / (rank * config.signal_sigma_hz**2)
                + np.log(2 * np.pi * config.signal_sigma_hz**2)
            )
        )
        null_ll += (
            -0.5
            * count
            * (
                np.sum(null**2) / (rank * config.null_sigma_hz**2)
                + np.log(2 * np.pi * config.null_sigma_hz**2)
            )
        )
    signal_ll = np.where(support, signal_ll, -np.inf)
    components = np.r_[
        signal_ll + np.log(config.signal_prior / catalogue_size),
        null_ll + np.log1p(-config.signal_prior),
    ]
    score = float(logsumexp(components))
    if not np.isfinite(score):
        raise ValueError("non-finite unseen-scan score")
    return {
        "log_predictive": score,
        "contrast_rank": rank_total,
        "candidate_weights": np.exp(components[:-1] - score),
        "null_weight": float(np.exp(components[-1] - score)),
        "interpretation": "offset-invariant composite Doppler-shape score",
    }
