"""Position-conditioned track-shape initialization without reference coordinates.

Track identities and samples are fixed before seeing orbits. Bounded sampling
only proposes initial calibration; the subsequent likelihood uses every window.
"""

import time
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from leo.analysis.regional_position_score import ALIAS_HZ, circular, predict_orbits, zero_sum_basis
from leo.contracts.regional_position import PositionObservations


@dataclass(frozen=True)
class BootstrapMatch:
    rows: tuple[int, ...]
    satellite_index: int
    timing_s: float
    shape_rms_hz: float
    shape_cost: float


@dataclass(frozen=True)
class PositionBootstrap:
    satellite_indices: tuple[int, ...]
    vector: np.ndarray
    matches: tuple[BootstrapMatch, ...]


def observation_subset(observations, rows):
    indices = np.asarray(rows, int)
    return PositionObservations(
        tuple(observations.window_ids[i] for i in indices),
        observations.times_s[indices],
        observations.measured_hz[indices],
        observations.rf_hz[indices],
        observations.receiver[indices],
        observations.channel[indices],
        observations.margin[indices],
    )


def bootstrap_position(
    observations, bank, prior, point, tracks, *, maximum_seconds=5.0, samples_per_track=12
):
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800 or samples_per_track < 3:
        raise ValueError("invalid bootstrap work bounds")
    begun = time.monotonic()
    all_rows, unwrapped, offsets = [], [], [0]
    for track in tracks:
        rows = np.asarray(track, int)
        if (
            rows.ndim != 1
            or len(rows) < 3
            or len(np.unique(rows)) != len(rows)
            or np.any(rows < 0)
            or np.any(rows >= len(observations.window_ids))
        ):
            raise ValueError("invalid bootstrap track indices")
        if (
            len(np.unique(observations.receiver[rows])) != 1
            or len(np.unique(observations.rf_hz[rows])) != 1
            or np.any(np.diff(observations.times_s[rows]) <= 0)
        ):
            raise ValueError("bootstrap track must be time-ordered on one receiver/RF lane")
        values = np.unwrap(observations.measured_hz[rows] * 2 * np.pi / ALIAS_HZ)
        values *= ALIAS_HZ / (2 * np.pi)
        take = np.unique(
            np.linspace(0, len(rows) - 1, min(samples_per_track, len(rows))).astype(int)
        )
        all_rows.extend(rows[take].tolist())
        unwrapped.extend(values[take].tolist())
        offsets.append(len(all_rows))
    if not all_rows:
        raise ValueError("no bootstrap tracks")
    # Orbit-blind tracklet proposals can overlap. Predict each sampled window
    # once, then gather its values for each shape proposal. This affects seeds
    # only: the final likelihood still has exactly one row per original window.
    unique_rows, inverse = np.unique(all_rows, return_inverse=True)
    sparse = observation_subset(observations, unique_rows)
    unwrapped = np.asarray(unwrapped)
    best = [None] * len(tracks)
    for timing in np.arange(-20.0, 20.001, 2.0):
        if time.monotonic() - begun >= maximum_seconds:
            raise TimeoutError("regional bootstrap time budget")
        prediction, visible, _, _ = predict_orbits(
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
    matches = tuple(row[1] for row in best if row is not None and row[1].shape_rms_hz < 2000)
    if {int(observations.receiver[m.rows[0]]) for m in matches} != {0, 1}:
        raise ValueError("no accepted bootstrap shapes on both receivers at this point")
    indices = tuple(sorted({m.satellite_index for m in matches}, key=lambda i: bank.numbers[i]))
    if len(indices) < 2:
        raise ValueError("fewer than two bootstrap satellite candidates")
    shifts = np.array(
        [np.median([m.timing_s for m in matches if m.satellite_index == i]) for i in indices]
    )
    common = np.clip(np.mean(shifts), -10, 10)
    # The timing gauge is zero-sum. If the mean lies outside the common bound,
    # translate all shifts together instead of misrepresenting their mean.
    shifts = shifts - np.mean(shifts) + common
    shifts *= min(1.0, 20 / max(20, float(np.max(abs(shifts)))))
    common = float(shifts.mean())
    selected_bank = bank.select(list(indices))
    predicted = predict_orbits(
        selected_bank, observations, prior, point, shifts, derivatives=False
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
                    raise TimeoutError("regional receiver-line bootstrap time budget")
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
        chosen = min(fits, key=lambda f: f.cost)
        vector[2 + 2 * rx : 4 + 2 * rx] = chosen.x
    return PositionBootstrap(indices, vector, matches)
