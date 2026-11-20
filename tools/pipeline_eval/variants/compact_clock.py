"""Fit one continuous fractional-frequency oscillator per physical receiver."""

from unittest.mock import patch

import numpy as np

from . import joint_clock_model as smooth
from . import robust_em as lean
from . import robust_orbit_fit as exact

METHOD = "native_compact_clock"
KNOTS_S = np.arange(0.0, 301.0, 75.0)
RATE_SD_HZ_S = 10.0
LANES = 4

# A second difference of integrated white acceleration is a triangular
# integral. Consecutive triangles have one quarter of their energy in common.
_SECOND = np.diff(np.eye(len(KNOTS_S)), n=2, axis=0)
_RBF_SECOND = _SECOND @ smooth.basis(KNOTS_S, smooth.REFERENCE_HZ)
ACCELERATION_SD_HZ = float(smooth.PRIOR_HZ * np.sqrt(np.mean(np.sum(_RBF_SECOND**2, axis=1))))
_NEIGHBOR = np.eye(3, k=1) + np.eye(3, k=-1)
_INNOVATION_FACTOR = np.linalg.cholesky(np.eye(3) + 0.25 * _NEIGHBOR) * ACCELERATION_SD_HZ
_RATE = (np.eye(5)[-1] - np.eye(5)[0]) / (KNOTS_S[-1] - KNOTS_S[0])
_PRIOR_MAP = np.zeros((5, 4))
_PRIOR_MAP[1, 0] = RATE_SD_HZ_S
_PRIOR_MAP[2:, 1:] = _INNOVATION_FACTOR
_KNOT_MAP = np.linalg.solve(np.vstack([np.eye(5)[2], _RATE, _SECOND]), _PRIOR_MAP)


def basis(times, rf_hz):
    """Evaluate four standardized clock coordinates in physical Hertz."""
    t = np.asarray(times, dtype=float)
    left = np.clip(np.searchsorted(KNOTS_S, t, side="right") - 1, 0, len(KNOTS_S) - 2)
    fraction = ((t - KNOTS_S[left]) / 75.0)[:, None]
    hertz = (1.0 - fraction) * _KNOT_MAP[left] + fraction * _KNOT_MAP[left + 1]
    return (rf_hz / smooth.REFERENCE_HZ) * hertz


def _state(xy, bias, phase, c, clock):
    return smooth.ClockState(xy, bias, np.zeros(LANES), phase, c, clock)


def _radio(track, state):
    return (
        state.bias[track.lane]
        + basis(track.t, track.rf) @ state.clock[track.lane // 2]
        + (track.rf / 1e9 - 11.5) * state.c_hz_per_ghz
    )


def fit(rows, n_orbits, half, arm):
    """Solve the bounded position, aliases and shared oscillator with fixed owners."""
    if not rows:
        return None
    used = sorted({row.orbit for row in rows})
    fitted = arm == "fitted_c"
    phase_start = 14 + int(fitted)
    columns = {sat: phase_start + i for i, sat in enumerate(used)}
    width = phase_start + len(used)
    matrix, right, raw_matrix, raw_right = [], [], [], []
    for row in rows:
        arc, j, track = row.arc, row.winner, row.arc.track
        design = np.zeros((len(track.t), width))
        design[:, :2] = arc.xy[j]
        design[:, 2 + track.lane] = 1000
        begin = 6 + 4 * (track.lane // 2)
        design[:, begin : begin + 4] = basis(track.t, track.rf)
        if fitted:
            design[:, 14] = 1000 * (track.rf / 1e9 - 11.5)
        design[:, columns[row.orbit]] = arc.phase[j]
        target = arc.residual[j] - row.alias * lean.PERIOD
        weight = smooth._scale(row)
        matrix.append(weight * (track.whiten @ design))
        right.append(weight * (track.whiten @ target))
        raw_matrix.append(design)
        raw_right.append(target)
    sigma = np.r_[
        [1000.0] * 2, [lean.PERIOD / np.sqrt(12) / 1000] * LANES, np.ones(8),
        [200.0] * int(fitted), [lean.PHASE_SD_S] * len(used),
    ]
    bound = np.r_[
        [half] * 2, [lean.PERIOD / 1000] * LANES, np.full(8, np.inf),
        [600.0] * int(fitted), [lean.PHASE_BOUND_S] * len(used),
    ]
    a = np.vstack([*matrix, np.diag(1 / sigma)])
    b = np.r_[np.concatenate(right), np.zeros(width)]
    solution = lean.lsq_linear(a, b, bounds=(-bound, bound), method="bvls", max_iter=30)
    if not solution.success:
        return None
    x = solution.x
    phases = np.zeros(n_orbits)
    phases[used] = x[phase_start:]
    state = _state(x[:2], 1000 * x[2:6], phases, x[14] * 1000 if fitted else 0.0,
                   x[6:14].reshape(2, 4))
    covariance = np.linalg.solve(a.T @ a, np.eye(width, 2))[:2]
    radius = float(np.sqrt(5.991 * np.linalg.eigvalsh(covariance)[-1]))
    residual = np.concatenate(raw_right) - np.vstack(raw_matrix) @ x
    return lean.Fit(state, float(np.sqrt(np.mean(residual**2))), float(2 * solution.cost), radius)


def _loss(rows, tile, region, state):
    site = region.site(state.xy)[0]
    points = raw = white = 0
    for row in rows:
        track = row.arc.track
        phase = state.phase[row.orbit]
        frequency = exact.project(tile, row.orbit, track.t, site, phase, track.rf)[0]
        residual = track.hz - frequency - _radio(track, state) - row.alias * lean.PERIOD
        innovation = (smooth._scale(row) * track.whiten) @ residual
        points += len(residual)
        raw += float(residual @ residual)
        white += float(innovation @ innovation)
    prior = np.r_[
        state.xy / 1000, state.bias / (lean.PERIOD / np.sqrt(12)),
        state.c_hz_per_ghz / 200000, state.phase / lean.PHASE_SD_S, state.clock.ravel(),
    ]
    return white + float(prior @ prior), float(np.sqrt(raw / points))


def refine(rows, start, tile, region, half, arm, *, clock=True):
    current = start.state
    initial = np.zeros((2, 4))
    initial[:, 0] = current.drift.reshape(2, 2).mean(axis=1) / (100.0 * RATE_SD_HZ_S)
    state = _state(current.xy, current.bias, current.phase, current.c_hz_per_ghz, initial)
    radius = start.radius_km
    score, rms = _loss(rows, tile, region, state)
    evaluations, steps = 1, 0
    for _ in range(exact.RELINEARIZATIONS):
        proposal = fit(exact._recenter(rows, tile, region, state),
                       len(tile.positions_km), half, arm)
        if proposal is None:
            break
        radius = proposal.radius_km
        for fraction in exact.BACKTRACK:
            trial = exact._blend(state, proposal.state, fraction)
            oscillator = state.clock + fraction * (proposal.state.clock - state.clock)
            candidate = _state(trial.xy, trial.bias, trial.phase, trial.c_hz_per_ghz, oscillator)
            objective, error = _loss(rows, tile, region, candidate)
            evaluations += 1
            if objective + 1e-8 < score:
                state, score, rms = candidate, objective, error
                steps += 1
                break
        else:
            break
    return lean.Fit(state, rms, score, radius), dict(
        accepted_steps=steps, exact_objective_evaluations=evaluations,
        knot_clock_rms_hz=float(np.sqrt(np.mean((state.clock @ _KNOT_MAP.T) ** 2))),
    )


def infer(observation, offer, catalogue):
    """Retain smooth-clock assignment and held scoring with a smaller fitter."""
    with patch.object(smooth, "refine", refine), patch.object(smooth, "_radio", _radio):
        result = smooth.infer(observation, offer, catalogue)
    result["metrics"]["receiver_clock_coordinates"] = 8
    result["metrics"]["static_hardware_coordinates"] = LANES
    return result
