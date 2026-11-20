"""Measure curvature by time within the existing observed track support."""

import numpy as np

MIN_SECONDS = 20.0
RMS_HZ = 250.0
ROOT_THIRD = 1 / np.sqrt(3)


def measure(times, cfo, max_gap_s):
    """Return covered time and exact line-detrended piecewise-linear RMS."""
    t, y = np.asarray(times, dtype=float), np.asarray(cfo, dtype=float)
    if (
        t.ndim != 1
        or y.shape != t.shape
        or not np.all(np.isfinite(t))
        or not np.all(np.isfinite(y))
        or not np.isfinite(max_gap_s)
        or max_gap_s <= 0
    ):
        raise ValueError("finite aligned track arrays and positive maximum gap required")
    dt = np.diff(t)
    if np.any(dt <= 0):
        raise ValueError("track times must be strictly increasing")
    use = dt <= max_gap_s
    widths = dt[use]
    seconds = float(widths.sum())
    if seconds == 0:
        return seconds, 0.0
    # Two Gauss nodes integrate every affine moment and residual square exactly.
    t0, t1 = t[:-1][use] - t[0], t[1:][use] - t[0]
    y0, y1 = y[:-1][use] - y[0], y[1:][use] - y[0]
    offsets = np.array([-ROOT_THIRD, ROOT_THIRD])
    x = ((t0 + t1)[:, None] + widths[:, None] * offsets) / 2
    values = ((y0 + y1)[:, None] + (y1 - y0)[:, None] * offsets) / 2
    weights = widths[:, None] / (2 * seconds)
    x -= np.sum(weights * x)
    values -= np.sum(weights * values)
    slope = np.sum(weights * x * values) / np.sum(weights * x**2)
    return seconds, float(np.sqrt(np.sum(weights * (values - slope * x) ** 2)))


def active(track, max_gap_s):
    duration, rms = measure(track["times"], track["values"], max_gap_s)
    return duration >= MIN_SECONDS and rms >= RMS_HZ
