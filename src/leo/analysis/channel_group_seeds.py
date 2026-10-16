"""Transfer independent training bootstrap hypotheses into a shared candidate bank."""

from dataclasses import replace

import numpy as np

from leo.analysis.channel_group_calibration import project_calibration_seed
from leo.analysis.regional_position_score import zero_sum_basis


def declocked_training_observations(observations, correction):
    """Remove only a frozen receiver calibration for training proposal generation.

    Orbital predictions and satellite timing shifts never enter this transform.
    Final likelihoods must still use the original observations.
    """
    values = correction.predict(
        observations.times_s,
        observations.rf_hz,
        observations.receiver,
        observations.channel >= 5,
    )
    return replace(observations, measured_hz=observations.measured_hz - values)


def bootstrap_correction(bootstrap, training_observations, target_observations):
    """Evaluate a training-defined receiver/RF seed without target recentering."""
    coefficients = np.asarray(bootstrap.vector)[2:7]
    rx = target_observations.receiver
    return (
        coefficients[2 * rx]
        + coefficients[2 * rx + 1]
        * (target_observations.times_s - training_observations.time_center_s)
        + coefficients[4] * (target_observations.rf_hz - training_observations.rf_center_hz) / 1e9
    )


def shared_bootstrap_seed(
    model, shared_indices, hypotheses, *, carried_corrections=None, fallback_timings=None
):
    """Accept only bootstrap states/observations, never full-data fitted donors.

    Candidate timings use medians of the independent training proposals that
    actually include that satellite. Their physical correction functions, not
    reinterpreted coefficient arrays, initialize the shared nuisance layout.
    """
    indices = tuple(shared_indices)
    if not indices or len(set(indices)) != len(indices) or not hypotheses:
        raise ValueError("unique shared candidates and training hypotheses required")
    timings = {index: [] for index in indices}
    targets = {}
    points = []
    for view, (bootstrap, observations) in hypotheses.items():
        if view not in {"low", "high", "all"}:
            raise ValueError("unknown channel-group bootstrap view")
        vector = np.asarray(bootstrap.vector)
        source_indices = tuple(bootstrap.satellite_indices)
        if vector.shape != (7 + len(source_indices),) or not np.isfinite(vector).all():
            raise ValueError("bootstrap vector/candidate dimensions differ")
        shifts = vector[7] + zero_sum_basis(len(source_indices)) @ vector[8:]
        for index, shift in zip(source_indices, shifts, strict=True):
            if index in timings:
                timings[index].append(float(shift))
        points.append(vector[:2])
        targets[view] = bootstrap_correction(bootstrap, observations, model.observations)
        if carried_corrections is not None and view in carried_corrections:
            target = model.observations
            targets[view] += carried_corrections[view].predict(
                target.times_s, target.rf_hz, target.receiver, target.channel >= 5
            )
    if fallback_timings is not None:
        for index, values in timings.items():
            if not values and index in fallback_timings:
                value = float(fallback_timings[index])
                if not np.isfinite(value):
                    raise ValueError("finite training timing fallback required")
                values.append(value)
    if any(not values for values in timings.values()) or not all(
        np.array_equal(points[0], point) for point in points
    ):
        raise ValueError("shared candidates need training timings at one common discovery point")
    fallback = targets.get("all", next(iter(targets.values())))
    low, high = targets.get("low", fallback), targets.get("high", fallback)
    target = np.where(model.observations.channel >= 5, high, low)
    projection = project_calibration_seed(model, target)
    shifts = np.array([np.median(timings[index]) for index in indices])
    shifts -= shifts.mean() - np.clip(shifts.mean(), -9.9, 9.9)
    shifts *= min(1.0, 19.9 / max(19.9, float(abs(shifts).max())))
    coefficients = projection["coefficients"]
    vector = np.r_[
        points[0], coefficients[:5], shifts.mean(), model.basis.T @ (shifts - shifts.mean())
    ]
    return dict(vector=vector, nuisance=coefficients[5:], projection=projection)
