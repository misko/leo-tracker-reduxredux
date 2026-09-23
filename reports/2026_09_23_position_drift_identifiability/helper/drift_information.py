"""Small linear-algebra helpers for the training-only drift audit."""

from __future__ import annotations

import numpy as np


def profiled_information(derivatives_hz_per_m, track_ids, times_s):
    """Return 2-D information after track CFOs, then a common scan slope.

    Every track has a free constant term.  The optional scan nuisance is one
    coefficient multiplying time, after time has also been centred per track.
    This is an unweighted local design diagnostic, not a noise model.
    """
    derivative = np.asarray(derivatives_hz_per_m, dtype=float)
    ids = np.asarray(track_ids)
    time = np.asarray(times_s, dtype=float)
    if derivative.ndim != 2 or derivative.shape[1] != 2:
        raise ValueError("derivatives must have east/north columns")
    if len(ids) != len(derivative) or len(time) != len(derivative):
        raise ValueError("row metadata lengths must match derivatives")
    centered = derivative.copy()
    slope = time.copy()
    for track in np.unique(ids):
        rows = ids == track
        if rows.sum() < 2:
            raise ValueError("each included track requires at least two rows")
        centered[rows] -= centered[rows].mean(axis=0)
        slope[rows] -= slope[rows].mean()
    before_slope = centered.T @ centered
    slope_norm = float(slope @ slope)
    after_slope = before_slope.copy()
    if slope_norm > 0:
        cross = centered.T @ slope
        after_slope -= np.outer(cross, cross) / slope_norm
    return before_slope, after_slope, centered, slope


def eigensummary(information):
    """Stable eigenvalue and conditioning summary for a symmetric 2x2 matrix."""
    values = np.linalg.eigvalsh(np.asarray(information, dtype=float))
    if values[0] < -1e-12:
        raise ValueError("profiled information must be positive semidefinite")
    values = np.maximum(values, 0.0)
    return {
        "smallest_hz2_per_m2": float(values[0]),
        "largest_hz2_per_m2": float(values[1]),
        "condition_number": float(values[1] / values[0]) if values[0] > 0 else None,
        "determinant_hz4_per_m4": float(np.linalg.det(information)),
        "trace_hz2_per_m2": float(np.trace(information)),
    }
