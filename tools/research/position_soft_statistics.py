"""Pure, train-only hard/soft candidate statistics for position experiments."""

from __future__ import annotations

import numpy as np
from scipy.special import logsumexp

SIGMA_HZ = 250.0
NULL_SIGMA_HZ = 30000.0
SIGNAL_PRIOR = 0.5


def track_statistics(prediction, include_evaluation=False):
    """Profile CFO on training rows and freeze posterior before held-out scoring.

    The candidate/tau prior is uniform over the complete cached support.  An
    invisible component receives zero likelihood, rather than being removed
    from that denominator.  Dense-row IID likelihood values are heuristic.
    """
    train = np.asarray(prediction.training_mask, bool)
    y = np.asarray(prediction.measured_hz, float)
    model = np.asarray(prediction.predictions_hz, float)
    residual = y[None, None, :] - model
    cfo = residual[:, :, train].mean(axis=2)
    centered = residual - cfo[:, :, None]
    sse = np.sum(centered[:, :, train] ** 2, axis=2)
    n = int(train.sum())
    if n == 0 or (include_evaluation and train.all()):
        raise ValueError("training and requested evaluation support must be nonempty")
    visible = np.asarray(prediction.visible, bool)
    visible = np.broadcast_to(visible[:, None] if visible.ndim == 1 else visible, sse.shape)
    full_count = sse.size
    log_signal = np.full(sse.shape, -np.inf)
    log_signal[visible] = (
        np.log(SIGNAL_PRIOR / full_count) - 0.5 * sse[visible] / SIGMA_HZ**2 - n * np.log(SIGMA_HZ)
    )
    null = y - y[train].mean()
    log_null = (
        np.log1p(-SIGNAL_PRIOR)
        - 0.5 * np.sum(null[train] ** 2) / NULL_SIGMA_HZ**2
        - n * np.log(NULL_SIGMA_HZ)
    )
    log_total = logsumexp(np.r_[log_signal.ravel(), log_null])
    posterior = np.exp(log_signal - log_total)
    null_posterior = float(np.exp(log_null - log_total))
    hard_index = np.unravel_index(np.argmin(np.where(visible, sse, np.inf)), sse.shape)
    positive = posterior[posterior > 0]
    result = {
        "hard_mse_hz2": float(np.min(np.where(visible, sse, np.inf)) / n),
        "soft_nll": float(-log_total / n),
        "posterior": posterior,
        "null_probability": null_posterior,
        "entropy_nats": float(
            -np.sum(positive * np.log(positive))
            - (null_posterior * np.log(null_posterior) if null_posterior > 0 else 0)
        ),
        "visible_support": int(visible.sum()),
        "full_support": int(full_count),
    }
    if include_evaluation:
        held = ~train
        signal_squared = centered[:, :, held] ** 2
        null_squared = null[held] ** 2
        soft_mse = float(
            (posterior[..., None] * signal_squared).sum() + null_posterior * null_squared.sum()
        ) / int(held.sum())
        hard_mse = (
            float(signal_squared[hard_index].mean())
            if np.any(visible)
            else float(null_squared.mean())
        )
        result["soft_reserved_mse_hz2"] = soft_mse
        result["hard_reserved_mse_hz2"] = hard_mse
    return result
