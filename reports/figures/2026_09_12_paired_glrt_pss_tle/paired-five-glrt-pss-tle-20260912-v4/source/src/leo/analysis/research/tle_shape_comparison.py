"""Pure, conditional TLE shape comparisons with explicit clock nuisance terms."""

from __future__ import annotations

import numpy as np


def unwrap_cfo(values: np.ndarray, spacing_hz: float = 2_500_000 / 11) -> np.ndarray:
    """Choose adjacent pilot aliases without consulting orbital predictions.

    Assumes adjacent true CFO changes are less than half the alias spacing.
    Does not establish the absolute alias or reject non-alias outliers.
    """
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all() or spacing_hz <= 0:
        raise ValueError("finite one-dimensional CFO and positive spacing required")
    return np.unwrap(values * (2 * np.pi / spacing_hz)) * (spacing_hz / (2 * np.pi))


def profile_shapes(times, measured, predictions, *, nuisance_degree: int, split_s: float):
    """Fit nuisance on early samples only and rank by early residual RMS.

    Late residuals and pairwise distances are descriptive checks, not calibrated
    probabilities. Detector/track selection may have used the complete interval.
    """
    t, y, p = (np.asarray(v, dtype=float) for v in (times, measured, predictions))
    if (
        t.ndim != 1
        or y.shape != t.shape
        or p.ndim != 2
        or p.shape[1] != len(t)
        or p.shape[0] == 0
        or nuisance_degree not in (0, 1, 2)
        or not all(np.isfinite(v).all() for v in (t, y, p))
        or np.any(np.diff(t) <= 0)
    ):
        raise ValueError("ordered finite observations and a nonempty prediction bank required")
    train = t < split_s
    if min(train.sum(), (~train).sum()) < nuisance_degree + 2:
        raise ValueError("insufficient early or late samples")
    design = np.vander(t - split_s / 2, nuisance_degree + 1, increasing=True)
    coef = np.linalg.lstsq(design[train], (y[None, :] - p)[:, train].T, rcond=None)[0]
    fitted = p + (design @ coef).T
    residual = y[None, :] - fitted
    early = np.sqrt(np.mean(residual[:, train] ** 2, axis=1))
    late = np.sqrt(np.mean(residual[:, ~train] ** 2, axis=1))
    order = np.argsort(early, kind="stable")
    separation = np.sqrt(np.mean((fitted[:, ~train] - fitted[order[0], ~train]) ** 2, axis=1))
    return dict(
        order=order,
        early_rms=early,
        late_rms=late,
        coefficients=coef.T,
        fitted=fitted,
        residual=residual,
        late_separation_from_early_winner=separation,
    )
