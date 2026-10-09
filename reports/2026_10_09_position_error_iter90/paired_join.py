"""Exact frozen-assignment RX pairing, including existing smooth-clock columns."""

from collections import defaultdict

import numpy as np


def _vector(values, length, name, *, integer=False):
    values = np.asarray(values, dtype=float)
    if values.shape != (length,) or not np.isfinite(values).all():
        raise ValueError(f"{name} must be a finite observation-length vector")
    if integer:
        if np.any(values != np.floor(values)):
            raise ValueError(f"{name} must contain integers")
        values = values.astype(np.int64)
    return values


def extract_pairs(
    observations, numbers, residuals, *, assignment_probability, smooth_clock_design=None
):
    """Join RX1-RX0 on satellite/channel/rounded-ms; average duplicates first.

    Assignment satellite IDs and probabilities must be frozen from fitted B7 and
    supplied unchanged to both arms. Smooth design is only the existing B7 smooth
    clock block supplied by the caller; this helper constructs no extra RF terms.
    All supplied numeric rows must be finite, including omitted/noise observations.
    """
    count = len(observations.times_s)
    times = _vector(observations.times_s, count, "times_s")
    receivers = _vector(observations.receiver, count, "receiver", integer=True)
    channels = _vector(observations.channel, count, "channel", integer=True)
    satellites = _vector(numbers, count, "numbers", integer=True)
    residuals = _vector(residuals, count, "residuals")
    probabilities = _vector(assignment_probability, count, "assignment_probability")
    if np.any(~np.isin(receivers, [0, 1])):
        raise ValueError("receiver must be RX0 or RX1")
    if np.any((probabilities < 0) | (probabilities > 1)):
        raise ValueError("assignment_probability must be in [0,1]")
    if smooth_clock_design is None:
        design = np.zeros((count, 0))
    else:
        design = np.asarray(smooth_clock_design, dtype=float)
        if design.ndim != 2 or design.shape[0] != count or not np.isfinite(design).all():
            raise ValueError("smooth_clock_design must be a finite observation-row matrix")
    groups = defaultdict(dict)
    selected = (satellites > 0) & (probabilities > 0.5)
    for index in np.flatnonzero(selected):
        key = (int(satellites[index]), int(channels[index]), round(float(times[index]) * 1000))
        groups[key].setdefault(int(receivers[index]), []).append(int(index))
    rows = []
    for (satellite, channel, tick), receivers_at_key in sorted(groups.items()):
        if 0 not in receivers_at_key or 1 not in receivers_at_key:
            continue
        indices0, indices1 = receivers_at_key[0], receivers_at_key[1]
        difference = float(np.mean(residuals[indices1]) - np.mean(residuals[indices0]))
        smooth_difference = np.mean(design[indices1], axis=0) - np.mean(design[indices0], axis=0)
        rows.append(
            dict(
                satellite=satellite,
                channel=channel,
                tick_ms=tick,
                time_s=tick / 1000,
                difference_hz=difference,
                rx0_indices=indices0,
                rx1_indices=indices1,
                rx0_count=len(indices0),
                rx1_count=len(indices1),
                rx0_time_mean_s=float(np.mean(times[indices0])),
                rx1_time_mean_s=float(np.mean(times[indices1])),
                smooth_design_difference=smooth_difference.tolist(),
            )
        )
    return dict(
        y_hz=np.asarray([r["difference_hz"] for r in rows], dtype=float),
        time_s=np.asarray([r["time_s"] for r in rows], dtype=float),
        satellite=np.asarray([r["satellite"] for r in rows], dtype=np.int64),
        channel=np.asarray([r["channel"] for r in rows], dtype=np.int64),
        smooth_design=np.asarray(
            [r["smooth_design_difference"] for r in rows], dtype=float
        ).reshape(len(rows), design.shape[1]),
        pairs=rows,
        counts=dict(
            total=count,
            assigned=int(np.sum(satellites > 0)),
            eligible_assignment=int(np.sum(selected)),
            noise=int(np.sum(satellites <= 0)),
            nonfinite=0,
        ),
        convention="RX1-RX0; Python rounded milliseconds (ties to even); duplicate means",
    )
