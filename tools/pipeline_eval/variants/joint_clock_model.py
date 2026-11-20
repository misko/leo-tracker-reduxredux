"""Add the pinned v5 shared receiver clock to a fixed-assignment Doppler fit."""

from dataclasses import dataclass, fields
from hashlib import sha256
from unittest.mock import patch

import numpy as np

from . import joint_orbits as joint
from . import robust_em as lean
from . import robust_orbit_fit as exact

METHOD = "joint_clock_model"
BOUNDARY = "Anonymous archive GLRT tracks and causal TLE through a shared receiver clock fit"
CENTER_S = np.arange(0.0, 300.1, 30.0)
WIDTH_S = 20.0
PRIOR_HZ = 200.0
REFERENCE_HZ = 11.5e9


def _affine(t):
    return np.column_stack((np.ones(len(t)), (t - 150.0) / 150.0))


def _bumps(t):
    return np.exp(-0.5 * ((t[:, None] - CENTER_S) / WIDTH_S) ** 2)


_GRID = np.arange(301.0)
_AFFINE_COEFFICIENTS = np.linalg.lstsq(_affine(_GRID), _bumps(_GRID), rcond=None)[0]


def basis(times, rf_hz):
    """Fractional frequency perturbations with no scan-wide affine component."""
    t = np.asarray(times, dtype=float)
    return (rf_hz / REFERENCE_HZ) * (_bumps(t) - _affine(t) @ _AFFINE_COEFFICIENTS)


@dataclass
class ClockState(lean.State):
    clock: np.ndarray | None = None


def _state(base, clock):
    return ClockState(*(getattr(base, f.name) for f in fields(lean.State)), clock)


def _radio(track, state):
    result = (
        state.bias[track.lane]
        + state.drift[track.lane] * track.drift
        + (track.rf / 1e9 - 11.5) * state.c_hz_per_ghz
    )
    if state.clock is not None:
        result += basis(track.t, track.rf) @ state.clock[track.lane // 2]
    return result


def _scale(row):
    return np.sqrt(min(1, 40 / len(row.arc.track.t)) / (1 + row.loss / 4))


def fit(rows, n_orbits, half, arm, *, clock=True):
    """Solve the unchanged bounded calibration with a Gaussian clock block."""
    if not rows:
        return None
    used = sorted({row.orbit for row in rows})
    fitted_c = arm == "fitted_c"
    phase_start = 10 + int(fitted_c)
    columns = {sat: i + phase_start for i, sat in enumerate(used)}
    clock_start = phase_start + len(used)
    clock_columns = 2 * len(CENTER_S) if clock else 0
    width = clock_start + clock_columns
    matrix, right, raw_matrix, raw_right = [], [], [], []
    for row in rows:
        arc, j, track = row.arc, row.winner, row.arc.track
        design = np.zeros((len(track.t), width))
        design[:, :2] = arc.xy[j]
        design[:, 2 + track.lane] = 1000
        design[:, 6 + track.lane] = 1000 * track.drift
        if fitted_c:
            design[:, 10] = 1000 * (track.rf / 1e9 - 11.5)
        design[:, columns[row.orbit]] = arc.phase[j]
        if clock:
            begin = clock_start + track.lane // 2 * len(CENTER_S)
            design[:, begin : begin + len(CENTER_S)] = PRIOR_HZ * basis(track.t, track.rf)
        y = arc.residual[j] - row.alias * lean.PERIOD
        weight = _scale(row)
        matrix.append(weight * (track.whiten @ design))
        right.append(weight * (track.whiten @ y))
        raw_matrix.append(design)
        raw_right.append(y)
    scale = np.r_[
        [1000.0] * 2, [lean.PERIOD / np.sqrt(12) / 1000] * 4,
        [1.5] * 4, [200.0] * int(fitted_c),
        [lean.PHASE_SD_S] * len(used), np.ones(clock_columns),
    ]
    bounds = np.r_[
        [half] * 2, [lean.PERIOD / 1000] * 4, [6.0] * 4, [600.0] * int(fitted_c),
        [lean.PHASE_BOUND_S] * len(used), np.full(clock_columns, np.inf),
    ]
    a = np.vstack([*matrix, np.diag(1 / scale)])
    b = np.r_[np.concatenate(right), np.zeros(width)]
    solution = lean.lsq_linear(a, b, bounds=(-bounds, bounds), method="bvls", max_iter=30)
    if not solution.success:
        return None
    x = solution.x
    phases = np.zeros(n_orbits)
    phases[used] = x[phase_start:clock_start]
    smooth = x[clock_start:].reshape(2, -1) * PRIOR_HZ if clock else None
    state = ClockState(x[:2], 1000 * x[2:6], 1000 * x[6:10], phases,
                       float(x[10] * 1000) if fitted_c else 0.0, smooth)
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
        prediction = exact.project(tile, row.orbit, track.t, site, phase, track.rf)[0]
        error = track.hz - prediction - _radio(track, state) - row.alias * lean.PERIOD
        residual = (_scale(row) * track.whiten) @ error
        points += len(error)
        raw += float(error @ error)
        white += float(residual @ residual)
    prior = np.r_[
        state.xy / 1000, state.bias / (lean.PERIOD / np.sqrt(12)), state.drift / 1500,
        state.c_hz_per_ghz / 200000, state.phase / lean.PHASE_SD_S,
        [] if state.clock is None else state.clock.ravel() / PRIOR_HZ,
    ]
    return white + float(prior @ prior), float(np.sqrt(raw / points))


def refine(rows, start, tile, region, half, arm, *, clock):
    zeros = np.zeros((2, len(CENTER_S))) if clock else None
    state, radius = _state(start.state, zeros), start.radius_km
    score, rms = _loss(rows, tile, region, state)
    evaluations, steps = 1, 0
    for _ in range(exact.RELINEARIZATIONS):
        recentered = exact._recenter(rows, tile, region, state)
        proposal = fit(recentered, len(tile.positions_km), half, arm, clock=clock)
        if proposal is None:
            break
        radius = proposal.radius_km
        for fraction in exact.BACKTRACK:
            trial = exact._blend(state, proposal.state, fraction)
            smooth = (
                state.clock + fraction * (proposal.state.clock - state.clock) if clock else None
            )
            trial = _state(trial, smooth)
            objective, error = _loss(rows, tile, region, trial)
            evaluations += 1
            if objective + 1e-8 < score:
                state, score, rms = trial, objective, error
                steps += 1
                break
        else:
            break
    return lean.Fit(state, rms, score, radius), dict(
        accepted_steps=steps, exact_objective_evaluations=evaluations,
        clock_rms_hz=0.0 if not clock else float(np.sqrt(np.mean(state.clock**2))),
    )


def held_score(arcs, tile, region, state):
    """Predict held tracks with frozen parameters and the original alias convention."""
    site = region.site(state.xy)[0]
    losses, good, raw_error = [], [], []
    for arc in arcs:
        track = arc.track
        radio = _radio(track, state)
        one = track.whiten.sum(axis=1)
        options = []
        for orbit in arc.orbit:
            phase = state.phase[orbit]
            frequency = exact.project(tile, int(orbit), track.t, site, phase, track.rf)[0]
            raw = track.hz - frequency - radio
            innovation = track.whiten @ raw
            alias = np.rint((innovation @ one) / (lean.PERIOD * (one @ one)))
            z = innovation - alias * lean.PERIOD * one
            score = (z @ z + (phase / lean.PHASE_SD_S) ** 2) / len(z)
            options.append((float(score), int(orbit), raw - alias * lean.PERIOD))
        loss, orbit, residual = min(options, key=lambda item: item[0])
        losses.append(loss)
        raw_error.extend(residual)
        if loss <= joint.OUTLIER_CEILINGS[-1]:
            good.append(orbit)
    return dict(
        held_score=float(np.mean(1 / (1 + np.asarray(losses)))),
        held_normalized_mean_loss=float(np.mean(losses)),
        held_rf_rms_hz=float(np.sqrt(np.mean(np.square(raw_error)))),
        held_compatible_tracks=len(good),
        held_orbits=len(set(good)),
    )


def _ownership(rows):
    digest = sha256()
    for row in rows:
        track = row.arc.track
        digest.update(np.asarray([track.lane, row.orbit, row.alias], dtype="<i8").tobytes())
        digest.update(np.asarray([track.rf, row.loss, len(track.t)], dtype="<f8").tobytes())
        digest.update(track.t.astype("<f8").tobytes())
        digest.update(track.hz.astype("<f8").tobytes())
    return dict(
        sha256=digest.hexdigest(), tracks=len(rows), points=sum(len(r.arc.track.t) for r in rows)
    )


def infer(document, offer, catalogue, *, clock=True):
    """Use the as-built joint assignments and acceptance with an isolated fit."""
    original_solve = joint.solve
    training, fits = [], {}

    def solve(arcs, tile, region, half):
        original_train = joint._train

        def remember(train, initial, n, size):
            outcome = original_train(train, initial, n, size)
            if not training:
                training.append(outcome[1])
                fits["training_ownership"] = _ownership(outcome[1])
            return outcome

        def validate(held, state):
            arm = "c0" if "c0" not in fits else "fitted_c"
            start = lean.Fit(state, 0.0, 0.0, 0.0)
            trained, details = refine(training[0], start, tile, region, half, arm, clock=clock)
            fits[arm] = details
            return held_score(held, tile, region, trained.state)

        def finalize(rows, start, tile, region, half, arm):
            fits[f"final_{arm}_ownership"] = _ownership(rows)
            result, details = refine(rows, start, tile, region, half, arm, clock=clock)
            fits[f"final_{arm}"] = details
            return result, details

        with (
            patch.object(joint, "_train", remember),
            patch.object(joint, "_validation", validate),
            patch.object(exact, "refine", finalize),
        ):
            return original_solve(arcs, tile, region, half)

    with patch.object(joint, "solve", solve):
        result = joint.infer(document, offer, catalogue)
    result["boundary"] = BOUNDARY
    result["metrics"]["fixed_assignment_clock"] = clock
    result["metrics"]["clock_fit"] = fits
    return result
