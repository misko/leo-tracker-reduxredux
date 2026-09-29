"""Track likelihood potentials with training-only visibility and fixed masks."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "2026_09_29_unassociated_trend"))
from trend_mixture import contrast_density, trend_density  # noqa: E402


def track_potentials(track, prediction, visible, ids, snapshot):
    y = np.asarray(track["y"], float)
    times = np.asarray(track["times_s"], float)
    mask = np.asarray(track["mask"], bool)
    ids = np.asarray(ids)
    visible = np.asarray(visible, bool)
    prediction = np.asarray(prediction, float)
    if prediction.shape != (len(ids), len(y)) or visible.shape != ids.shape or not visible.any():
        raise ValueError("Invalid candidate prediction or empty training-visible domain")
    if mask.shape != y.shape or mask.sum() < 2 or mask.all():
        raise ValueError("Require training and held observations")
    residual = y[None, :] - prediction
    train, _ = contrast_density(residual[:, mask])
    joint, _ = contrast_density(residual)
    base = {"ids": ids[visible], "snapshot": snapshot}
    return (
        {**base, "signal": train[visible], "background": trend_density(y[mask], times[mask])},
        {**base, "signal": joint[visible], "background": trend_density(y, times)},
    )
