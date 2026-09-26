"""Independent validation primitives for the five-dwell phase experiment.

All phase comparisons are circular.  Unwrapping is permitted only within an
explicit visit/segment; this module deliberately has no cross-gap unwrap.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

TRAIN_END_S = 0.020


def time_partition(time_in_dwell_s, train_end_s=TRAIN_END_S):
    """Return disjoint train/holdout masks using the declared 20 ms boundary."""
    t = np.asarray(time_in_dwell_s, dtype=float)
    finite = np.isfinite(t)
    return finite & (t < train_end_s), finite & (t >= train_end_s)


def support_partition(support_start_s, support_end_s, train_end_s=TRAIN_END_S):
    """Split on full interpolation support, excluding boundary-straddling frames."""
    start = np.asarray(support_start_s, dtype=float)
    end = np.asarray(support_end_s, dtype=float)
    if start.shape != end.shape:
        raise ValueError("support bounds must have identical shape")
    finite = np.isfinite(start) & np.isfinite(end) & (start <= end)
    return finite & (end <= train_end_s), finite & (start >= train_end_s)


def tone_partition(tone_indices):
    """Deterministic disjoint tone holdout: even trains, odd evaluates."""
    tone = np.asarray(tone_indices, dtype=int)
    return tone % 2 == 0, tone % 2 == 1


def wrap_radians(angle):
    return (np.asarray(angle, dtype=float) + np.pi) % (2 * np.pi) - np.pi


def circular_metrics(observed, predicted, mask=None):
    observed = np.asarray(observed, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    use = np.isfinite(observed) & np.isfinite(predicted)
    if mask is not None:
        use &= np.asarray(mask, dtype=bool)
    error = wrap_radians(observed[use] - predicted[use])
    if not len(error):
        return {"count": 0, "wrapped_rms_deg": None, "mean_error_deg": None,
                "concentration": None}
    resultant = np.mean(np.exp(1j * error))
    return {
        "count": int(len(error)),
        "wrapped_rms_deg": float(np.degrees(np.sqrt(np.mean(error ** 2)))),
        "mean_error_deg": float(np.degrees(np.angle(resultant))),
        "concentration": float(abs(resultant)),
    }


def common_finite_support(*values, extra_mask=None):
    """Intersection used for fair baseline/candidate comparisons."""
    if not values:
        raise ValueError("at least one value array is required")
    mask = np.ones(np.asarray(values[0]).shape, dtype=bool)
    for value in values:
        if np.asarray(value).shape != mask.shape:
            raise ValueError("all arrays must have identical shape")
        mask &= np.isfinite(value)
    if extra_mask is not None:
        mask &= np.asarray(extra_mask, dtype=bool)
    return mask


def unwrap_within_segments(phase, segment):
    """Unwrap each named contiguous segment independently, never across gaps."""
    phase = np.asarray(phase, dtype=float)
    segment = np.asarray(segment)
    if phase.shape != segment.shape:
        raise ValueError("phase and segment must have identical shape")
    result = np.full(phase.shape, np.nan)
    # Stable first-seen ordering; repeated non-contiguous IDs are rejected.
    seen = []
    for value in segment:
        if value not in seen:
            seen.append(value)
    for value in seen:
        positions = np.flatnonzero(segment == value)
        if len(positions) and np.any(np.diff(positions) != 1):
            raise ValueError(f"segment {value!r} is non-contiguous")
        valid = positions[np.isfinite(phase[positions])]
        if len(valid) and np.any(np.diff(valid) != 1):
            raise ValueError(f"segment {value!r} contains an internal data gap")
        result[valid] = np.unwrap(phase[valid])
    return result


def causal_linear_predictions(time_s, phase_rad, train_mask):
    """Fit only declared training samples and extrapolate; future phase is unused."""
    t = np.asarray(time_s, dtype=float)
    p = np.asarray(phase_rad, dtype=float)
    train = np.asarray(train_mask, dtype=bool) & np.isfinite(t) & np.isfinite(p)
    if train.sum() < 2:
        raise ValueError("at least two finite training samples are required")
    unwrapped = np.unwrap(p[train])
    slope, intercept = np.polyfit(t[train], unwrapped, 1)
    return wrap_radians(intercept + slope * t), {"slope_rad_s": float(slope),
                                                  "training_count": int(train.sum())}


def uncertainty_coverage(observed, predicted, half_width_rad, mask=None):
    """Coverage of symmetric wrapped intervals on the circle."""
    observed = np.asarray(observed, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    width = np.asarray(half_width_rad, dtype=float)
    use = common_finite_support(observed, predicted, width, extra_mask=mask)
    covered = np.abs(wrap_radians(observed[use] - predicted[use])) <= width[use]
    return {"count": int(use.sum()), "covered": int(covered.sum()),
            "coverage": float(covered.mean()) if len(covered) else None}


def write_json(path, payload):
    path = Path(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
