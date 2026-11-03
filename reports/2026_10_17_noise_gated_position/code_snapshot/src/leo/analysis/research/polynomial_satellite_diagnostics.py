"""Residual gates and diagnostic lower bounds for polynomial/orbit matching.

Free affine fits are diagnostics only. They cannot calibrate receiver hardware
or establish an emitter identity. Batch gates reproduce the existing screens.
"""

import numpy as np


def batch_noise_screen(residual, times):
    r, t = np.asarray(residual, float), np.asarray(times, float)
    if r.ndim != 2 or t.ndim != 1 or r.shape[1] != len(t) or len(t) < 4:
        raise ValueError("at least four matching finite residual/time samples required")
    if not np.isfinite(r).all() or not np.isfinite(t).all() or np.ptp(t) <= 0:
        raise ValueError("finite samples and positive time span required")
    n = len(t)
    x = t - t.mean()
    sigma = np.maximum(np.std(r, axis=1, ddof=1), 75.0)
    mean_z = np.abs(r.mean(axis=1)) * np.sqrt(n) / sigma
    slope_z = np.abs(r @ x) / np.maximum(sigma * np.sqrt(x @ x), 1e-12)
    tx = x / max(float(np.ptp(t)) / 2, 1.0)
    design = np.stack([np.ones(n), tx, tx * tx], axis=1)
    fitted = (design @ np.linalg.lstsq(design, r.T, rcond=None)[0]).T
    rss0 = np.maximum(np.sum(r * r, axis=1), n * 75.0**2)
    rss1 = np.maximum(np.sum((r - fitted) ** 2, axis=1), n * 75.0**2)
    bic = n * np.log(rss0 / rss1) - 3 * np.log(n)
    splits = np.arange(4, n - 3)
    if len(splits):
        sums = np.cumsum(r, axis=1)[:, splits - 1]
        jump = sums / splits - (r.sum(axis=1)[:, None] - sums) / (n - splits)
        step_z = np.max(
            np.abs(jump) / (sigma[:, None] * np.sqrt(1 / splits + 1 / (n - splits))), axis=1
        )
    else:
        step_z = np.zeros(len(r))
    centered = r - r.mean(axis=1)[:, None]
    acf = np.sum(centered[:, :-1] * centered[:, 1:], axis=1) / np.maximum(
        np.sum(centered * centered, axis=1), 1e-12
    )
    passed = (mean_z <= 3) & (slope_z <= 3) & (bic <= 10) & (step_z <= 4)
    passed &= np.abs(acf) <= 4 / np.sqrt(n)
    return dict(
        noise_screen_pass=passed,
        mean_z=mean_z,
        slope_z=slope_z,
        quadratic_bic_gain=bic,
        maximum_step_z=step_z,
        lag1_acf=acf,
    )


def orbit_shape_lower_bounds(observed, times, predicted):
    """Unpenalized per-track offset/affine minima, never accepted associations."""
    y, t, f = np.asarray(observed), np.asarray(times), np.asarray(predicted)
    x = t - t.mean()
    residual = y[None, :] - f
    mean = residual.mean(axis=1)
    centered = residual - mean[:, None]
    slope = centered @ x / (x @ x)
    rss = np.sum(centered**2, axis=1)
    affine_rss = np.maximum(0.0, rss - slope**2 * (x @ x))
    return dict(
        mean_hz=mean,
        rms_offset_hz=np.sqrt(rss / len(t)),
        slope_hz_s=slope,
        rms_affine_hz=np.sqrt(affine_rss / len(t)),
    )


def feasible_order(score, preliminary, residual, times):
    """Rank candidates after every gate, rather than reject only one winner."""
    candidates = np.flatnonzero(preliminary)
    if not len(candidates):
        return np.array([], dtype=int), None
    diagnostics = batch_noise_screen(residual, times)
    passed = candidates[diagnostics["noise_screen_pass"]]
    ordered = passed[np.argsort(score[passed], kind="stable")]
    return ordered, diagnostics
