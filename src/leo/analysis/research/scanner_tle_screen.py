"""Training-only offset/tau selection for an exploratory scanner TLE screen.

This is a simple unweighted RMS diagnostic, not the production covariance-aware
matcher and not an identity probability. Predictions must be frozen beforehand.
"""

import numpy as np


def rank_curves(measured, predictions, *, training_count=None, training_mask=None):
    y = np.asarray(measured, dtype=float)
    p = np.asarray(predictions, dtype=float)
    if (
        y.ndim != 1
        or p.ndim != 3
        or p.shape[2] != len(y)
        or min(p.shape[:2]) < 1
        or not np.all(np.isfinite(y))
        or not np.all(np.isfinite(p))
    ):
        raise ValueError("invalid curve bank")
    if training_mask is None:
        if not isinstance(training_count, int) or not 2 <= training_count < len(y):
            raise ValueError("invalid chronological split")
        training_mask = np.arange(len(y)) < training_count
    else:
        training_mask = np.asarray(training_mask, dtype=bool)
        if training_mask.shape != y.shape or not 2 <= int(training_mask.sum()) < len(y):
            raise ValueError("invalid training mask")
    evaluation_mask = ~training_mask
    offsets = np.mean(y[training_mask] - p[:, :, training_mask], axis=2)
    residual = y - p - offsets[:, :, None]
    training = np.sqrt(np.mean(residual[:, :, training_mask] ** 2, axis=2))
    tau_indices = np.argmin(training, axis=1)
    rows = np.arange(len(p))
    train = training[rows, tau_indices]
    held = np.sqrt(np.mean(residual[rows, tau_indices][:, evaluation_mask] ** 2, axis=1))
    order = np.argsort(train, kind="stable")
    held_order = np.argsort(held, kind="stable")
    return {
        "order": order,
        "held_order": held_order,
        "tau_indices": tau_indices,
        "offsets": offsets[rows, tau_indices],
        "training_rms": train,
        "heldout_rms": held,
        "winner_heldout_rank": int(np.flatnonzero(held_order == order[0])[0]) + 1,
    }


def sample_grid(values, grid_start_s, spacing_s, sample_times_s):
    """Vectorized linear interpolation without extrapolation."""
    v = np.asarray(values, dtype=float)
    x = (np.asarray(sample_times_s, dtype=float) - grid_start_s) / spacing_s
    if spacing_s <= 0 or np.any(x < 0) or np.any(x > v.shape[-1] - 1):
        raise ValueError("prediction requested outside frozen grid")
    lo = np.minimum(np.floor(x).astype(int), v.shape[-1] - 2)
    fraction = x - lo
    return v[..., lo] * (1 - fraction) + v[..., lo + 1] * fraction
