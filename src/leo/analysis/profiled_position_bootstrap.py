"""Separate orbital-shape profiling from construction of a receiver-clock seed.

Selected shapes are reused from a common pool; each original window retains its
single downstream observation. The published bootstrap remains the test oracle.
"""

import time

import numpy as np
from scipy.optimize import least_squares

from leo.analysis.regional_position_bootstrap import (
    BootstrapMatch,
    PositionBootstrap,
    observation_subset,
)
from leo.analysis.regional_position_score import ALIAS_HZ, circular, predict_orbits, zero_sum_basis


def _work_bounds(maximum_seconds, samples_per_track=12):
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800 or samples_per_track < 3:
        raise ValueError("invalid profiled bootstrap work bounds")


def _track_rows(observations, track):
    rows = np.asarray(track, int)
    if (
        rows.ndim != 1
        or len(rows) < 3
        or len(np.unique(rows)) != len(rows)
        or np.any(rows < 0)
        or np.any(rows >= len(observations.window_ids))
    ):
        raise ValueError("invalid profiled bootstrap track indices")
    if (
        len(np.unique(observations.receiver[rows])) != 1
        or len(np.unique(observations.rf_hz[rows])) != 1
        or np.any(np.diff(observations.times_s[rows]) <= 0)
    ):
        raise ValueError("profiled track must be time-ordered on one receiver/RF lane")
    return rows


def profile_bootstrap_shapes(
    observations,
    bank,
    prior,
    point,
    tracks,
    *,
    maximum_seconds=5.0,
    samples_per_track=12,
    orbit_predictor=predict_orbits,
):
    """Use the original shape/alias/timing calculation without fitting a clock."""
    _work_bounds(maximum_seconds, samples_per_track)
    begun = time.monotonic()
    all_rows, unwrapped, offsets = [], [], [0]
    for track in tracks:
        rows = _track_rows(observations, track)
        values = np.unwrap(observations.measured_hz[rows] * 2 * np.pi / ALIAS_HZ)
        values *= ALIAS_HZ / (2 * np.pi)
        take = np.unique(
            np.linspace(0, len(rows) - 1, min(samples_per_track, len(rows))).astype(int)
        )
        all_rows.extend(rows[take].tolist())
        unwrapped.extend(values[take].tolist())
        offsets.append(len(all_rows))
    if not all_rows:
        raise ValueError("no profiled bootstrap tracks")
    unique_rows, inverse = np.unique(all_rows, return_inverse=True)
    sparse = observation_subset(observations, unique_rows)
    unwrapped = np.asarray(unwrapped)
    best = [None] * len(tracks)
    for timing in np.arange(-20.0, 20.001, 2.0):
        if time.monotonic() - begun >= maximum_seconds:
            raise TimeoutError("profiled shape time budget")
        prediction, visible, _, _ = orbit_predictor(
            bank, sparse, prior, point, np.full(len(bank.numbers), timing), derivatives=False
        )
        prediction, visible = prediction[inverse], visible[inverse]
        for i, track in enumerate(tracks):
            a, b = offsets[i : i + 2]
            residual = unwrapped[a:b, None] - prediction[a:b]
            location = np.median(residual, axis=0)
            for _ in range(10):
                weights = 1 / np.sqrt(1 + ((residual - location) / 200) ** 2)
                updated = np.sum(weights * residual, axis=0) / weights.sum(axis=0)
                if np.max(abs(updated - location), initial=0) < 0.01:
                    location = updated
                    break
                location = updated
            centered = residual - location
            cost = np.mean(2 * 200**2 * (np.sqrt(1 + (centered / 200) ** 2) - 1), axis=0)
            cost[np.mean(visible[a:b], axis=0) < 0.9] = np.inf
            index = min(range(len(cost)), key=lambda j: (cost[j], int(bank.numbers[j])))
            if not np.isfinite(cost[index]):
                continue
            rms = float(np.sqrt(np.mean(centered[:, index] ** 2)))
            key = (float(cost[index]), abs(timing), int(bank.numbers[index]), timing)
            if best[i] is None or key < best[i][0]:
                best[i] = (
                    key,
                    BootstrapMatch(tuple(track), index, float(timing), rms, float(cost[index])),
                )
    return tuple(row[1] for row in best if row is not None and row[1].shape_rms_hz < 2000)


def seed_from_profiled_shapes(
    observations,
    bank,
    prior,
    point,
    matches,
    *,
    maximum_seconds=5.0,
    orbit_predictor=predict_orbits,
):
    """Construct the original timing gauge and robust receiver line from matches."""
    _work_bounds(maximum_seconds)
    begun = time.monotonic()
    matches = tuple(matches)
    for match in matches:
        _track_rows(observations, match.rows)
        if not 0 <= match.satellite_index < len(bank.numbers):
            raise ValueError("profiled candidate index outside bank")
    if {int(observations.receiver[m.rows[0]]) for m in matches} != {0, 1}:
        raise ValueError("no accepted profiled shapes on both receivers")
    indices = tuple(sorted({m.satellite_index for m in matches}, key=lambda i: bank.numbers[i]))
    if len(indices) < 2:
        raise ValueError("fewer than two profiled satellite candidates")
    shifts = np.array(
        [np.median([m.timing_s for m in matches if m.satellite_index == i]) for i in indices]
    )
    common = np.clip(np.mean(shifts), -10, 10)
    shifts = shifts - np.mean(shifts) + common
    shifts *= min(1.0, 20 / max(20, float(np.max(abs(shifts)))))
    common = float(shifts.mean())
    predicted = orbit_predictor(
        bank.select(list(indices)), observations, prior, point, shifts, derivatives=False
    )[0]
    vector = np.zeros(8 + len(indices) - 1)
    vector[:2], vector[7], vector[8:] = point, common, zero_sum_basis(len(indices)).T @ shifts
    centered_time = observations.times_s - observations.time_center_s
    for rx in (0, 1):
        rows, residuals, weights = [], [], []
        for match in matches:
            if observations.receiver[match.rows[0]] != rx:
                continue
            ix = np.array(match.rows)
            rows.extend(ix)
            residuals.extend(
                circular(
                    observations.measured_hz[ix]
                    - predicted[ix, indices.index(match.satellite_index)]
                )
            )
            weights.extend([np.sqrt(min(len(ix), 100)) / len(ix)] * len(ix))
        residuals, weights = np.array(residuals), np.sqrt(weights)
        times = centered_time[rows]
        counts, edges = np.histogram(residuals, bins=128, range=(-ALIAS_HZ / 2, ALIAS_HZ / 2))
        centers = (edges[:-1] + edges[1:]) / 2
        starts = np.argsort(-counts, kind="stable")[:3]
        fits = []
        for index in starts:
            for slope in (-20.0, 0.0, 20.0):
                if time.monotonic() - begun >= maximum_seconds:
                    raise TimeoutError("profiled receiver-line time budget")
                result = least_squares(
                    lambda v, w=weights, r=residuals, t=times: (
                        w * circular(r - v[0] - v[1] * t) / 200
                    ),
                    [centers[index], slope],
                    bounds=([-np.inf, -50], [np.inf, 50]),
                    loss="soft_l1",
                    max_nfev=80,
                    x_scale=[200, 2],
                )
                fits.append(result)
        vector[2 + 2 * rx : 4 + 2 * rx] = min(fits, key=lambda f: f.cost).x
    return PositionBootstrap(indices, vector, matches)


def bootstrap_coherence_cost(
    observations, bank, prior, point, tracks, seed, orbit_predictor=predict_orbits
):
    """Evaluate identical original supports/weights with a physical common clock."""
    shifts = seed.vector[7] + zero_sum_basis(len(seed.satellite_indices)) @ seed.vector[8:]
    predicted, visible, _, _ = orbit_predictor(
        bank.select(list(seed.satellite_indices)),
        observations,
        prior,
        point,
        shifts,
        derivatives=False,
    )
    centered = observations.times_s - observations.time_center_s
    correction = seed.vector[2 + 2 * observations.receiver]
    correction = correction + seed.vector[3 + 2 * observations.receiver] * centered
    total = 0.0
    for track in tracks:
        rows = _track_rows(observations, track)
        matches = [m for m in seed.matches if set(track) <= set(m.rows)]
        if len(matches) > 1:
            raise ValueError("ambiguous original support assignment")
        residual = np.full(len(rows), ALIAS_HZ / 2)
        if matches:
            column = seed.satellite_indices.index(matches[0].satellite_index)
            supported = visible[rows, column]
            residual[supported] = circular(
                observations.measured_hz[rows[supported]]
                - predicted[rows[supported], column]
                - correction[rows[supported]]
            )
        squared_weight = np.sqrt(min(len(rows), 100)) / len(rows)
        total += squared_weight * np.sum(2 * 200**2 * (np.sqrt(1 + (residual / 200) ** 2) - 1))
    return float(total)
