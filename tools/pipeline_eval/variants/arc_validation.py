"""Fit anonymous Doppler arcs, then rank offered locations on unseen endpoints."""

import json
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from time import perf_counter

import numpy as np

from ..reference import grid, receiver

BOUNDARY = "Anonymous Doppler tracks and causal TLEs through held-out arc endpoints"
MIN_ORBITS = 3
MAX_LOSS = 9.0
SENTINELS = np.array(list(product((-grid.HALF_WIDTH_KM, 0.0, grid.HALF_WIDTH_KM), repeat=2)))


@dataclass(frozen=True)
class Arc:
    observations: np.ndarray
    training_count: int
    orbit_indices: np.ndarray
    states: grid._TrackArc


def _sample(track):
    count = min(len(track["times"]), grid.SAMPLES_PER_TRACK)
    index = np.rint(np.linspace(0, len(track["times"]) - 1, count)).astype(int)
    times = np.asarray(track["times"])[index]
    values = np.asarray(track["values"])[index]
    return times, values - values[0], 2 * count // 3


def _arc(tile, track):
    times, observations, split = _sample(track)
    position, velocity, acceleration = grid._interpolated_states(tile, times)
    delta = position[:, :split] - tile.ecef_center_km
    # No holdout frequencies or visibility tests enter the training shortlist.
    visible = ((delta @ tile.enu_frame[2]) >= -0.02 * np.linalg.norm(delta, axis=-1)).all(axis=1)
    indices = np.flatnonzero(visible)
    if not len(indices):
        return None
    rf = track["rf_hz"]
    position, velocity, acceleration = (
        array[indices] for array in (position, velocity, acceleration)
    )
    training = grid._TrackArc(
        grid._centered(observations[:split]),
        position[:, :split],
        velocity[:, :split],
        acceleration[:, :split],
        rf,
    )
    if len(indices) > grid.MAX_CANDIDATES:
        model, derivative, ray, distance = grid._orbit_shape(training, tile.ecef_center_km[None, :])
        radial = -model[0] * grid.LIGHT_SPEED_KM_S / rf
        transverse = training.velocities_km_s - radial[..., None] * ray[0]
        gradient = (rf / grid.LIGHT_SPEED_KM_S) * (transverse @ tile.enu_frame[:2].T)
        gradient /= distance[0, :, :, None]
        models = model + np.einsum("ksi,pi->pks", gradient, SENTINELS)
        loss, _ = grid._shape_loss(training.observed_hz, models, derivative)
        keep = np.argsort(loss.min(axis=0), kind="stable")[: grid.MAX_CANDIDATES]
        indices = indices[keep]
        position, velocity, acceleration = (
            array[keep] for array in (position, velocity, acceleration)
        )
    states = grid._TrackArc(observations, position, velocity, acceleration, rf)
    return Arc(observations, split, indices, states)


def _training_fit(observed, model, derivative):
    """Profile a regularized time shift and additive CFO on training data."""
    difference = observed - model
    residual = grid._centered(difference)
    rate = grid._centered(derivative)
    rate_power = np.mean(rate**2, axis=-1)
    cross = np.mean(residual * rate, axis=-1)
    phase = np.clip(
        cross / (rate_power + (grid.SHAPE_SD_HZ / grid.PHASE_SD_S) ** 2),
        -grid.PHASE_LIMIT_S,
        grid.PHASE_LIMIT_S,
    )
    offset = np.mean(difference - phase[..., None] * derivative, axis=-1)
    power = np.mean((residual - phase[..., None] * rate) ** 2, axis=-1)
    loss = power / grid.SHAPE_SD_HZ**2 + (phase / grid.PHASE_SD_S) ** 2
    return loss, offset, phase


def _distinct_support(indices):
    """Count distinct matched orbits per trial position, excluding -1 sentinels."""
    ordered = np.sort(indices, axis=0)
    changed = np.diff(ordered, axis=0, prepend=-2) != 0
    return np.count_nonzero((ordered >= 0) & changed, axis=0)


def _evaluate(tile, arcs, n_tracks, points, *, holdout=False):
    sites, up, _ = grid._sites(tile, points)
    train_score = np.zeros(len(points))
    assigned = np.full((len(arcs), len(points)), -1, dtype=int)
    test_score = np.zeros(len(points))
    test_squared = 0.0
    test_count = 0
    point_index = np.arange(len(points))
    for row, arc in enumerate(arcs):
        model, derivative, ray, _ = grid._orbit_shape(arc.states, sites)
        split = arc.training_count
        above = np.einsum("pksi,pi->pks", ray, up) >= 0.0
        loss, offset, phase = _training_fit(
            arc.observations[:split], model[..., :split], derivative[..., :split]
        )
        loss = np.where(above[..., :split].all(axis=-1), loss, np.inf)
        choice = loss.argmin(axis=1)
        select = point_index, choice
        fitted = loss[select]
        train_score += 1 / (1 + fitted / 4)
        supported = fitted <= MAX_LOSS
        if holdout:
            residual = (
                arc.observations[split:]
                - model[select][:, split:]
                - offset[select][:, None]
                - phase[select][:, None] * derivative[select][:, split:]
            )
            square_error = residual**2
            error = square_error.mean(axis=-1) / grid.SHAPE_SD_HZ**2
            supported &= (error <= MAX_LOSS) & above[select][:, split:].all(axis=-1)
            test_score += np.where(supported, 1 / (1 + error / 4), 0.0)
            test_squared += square_error[supported].sum()
            test_count += np.count_nonzero(supported) * square_error.shape[1]
        assigned[row] = np.where(supported, arc.orbit_indices[choice], -1)
    rms = float(np.sqrt(test_squared / test_count)) if test_count else None
    return train_score / n_tracks, _distinct_support(assigned), test_score / n_tracks, rms


def _best(points, scores, support):
    valid = np.flatnonzero(support >= MIN_ORBITS)
    if len(valid):
        return min(valid, key=lambda i: (-scores[i], points[i] @ points[i], *points[i]))
    return None


def _nomination(tile, tracks):
    arcs = [arc for track in tracks if (arc := _arc(tile, track)) is not None]
    if len(arcs) < MIN_ORBITS:
        return None
    axis = np.linspace(-grid.HALF_WIDTH_KM, grid.HALF_WIDTH_KM, grid.COARSE_STEPS)
    points = np.array(list(product(axis, repeat=2)))
    train, support, _, _ = _evaluate(tile, arcs, len(tracks), points)
    best = _best(points, train, support)
    if best is None or np.ptp(train) <= receiver.TIE_TOLERANCE:
        return None
    point, score, distinct = points[best], train[best], support[best]
    for divisor in (4, 16):
        shifts = np.arange(-2, 3) * (axis[1] - axis[0]) / divisor
        local = np.unique(
            np.clip(
                point + np.array(list(product(shifts, repeat=2))),
                -grid.HALF_WIDTH_KM,
                grid.HALF_WIDTH_KM,
            ),
            axis=0,
        )
        local = local[np.any(local != point, axis=1)]
        train, support, _, _ = _evaluate(tile, arcs, len(tracks), local)
        best = _best(local, train, support)
        if best is not None and train[best] > score:
            point, score, distinct = local[best], train[best], support[best]
    _, held_support, held_score, held_rms = _evaluate(
        tile, arcs, len(tracks), point[None, :], holdout=True
    )
    _, _, latlon = grid._sites(tile, point[None, :])
    return dict(
        latlon=latlon[0].tolist(),
        training_score=float(score),
        training_orbits=int(distinct),
        held_score=float(held_score[0]),
        held_orbits=int(held_support[0]),
        held_rms_hz=held_rms,
        boundary_clearance_km=float(grid.HALF_WIDTH_KM - np.max(np.abs(point))),
    )


def solve(observation, regions, catalog):
    duration = float(observation["duration_s"])
    if not np.isfinite(duration) or duration <= 0:
        raise ValueError("invalid observation duration")
    offered = receiver._offered_regions(regions)
    tracks = receiver._screen_tracks(observation["tracks"], duration)
    usable = [track for track in tracks if len(track["times"]) >= 6][: receiver.MAX_TRACKS]
    evidence = dict(
        screened_tracks=len(tracks), usable_tracks=len(usable), calibration_invariant=True
    )
    if len(usable) < MIN_ORBITS:
        return None, "insufficient_arc_tracks", evidence
    if not offered:
        return None, "no_regions", evidence
    sky = grid.prepare_sky(observation, catalog)
    scored = {
        region_id: _nomination(grid.make_tile(sky, center), usable) for region_id, center in offered
    }
    evidence["regional_scores"] = scored
    ordered = sorted(
        (row for row in offered if scored[row[0]] is not None),
        key=lambda row: (-scored[row[0]]["held_score"], row[1]),
    )
    if not ordered:
        return None, "insufficient_orbit_support", evidence
    selected = ordered[0][0]
    winner = scored[selected]
    runner_score = scored[ordered[1][0]]["held_score"] if len(ordered) > 1 else 0.0
    lead = winner["held_score"] - runner_score
    evidence.update(
        selected_region_id=selected,
        held_region_lead=lead,
        held_rms_hz=winner["held_rms_hz"],
        region_accepted=False,
    )
    if (
        winner["training_score"] < receiver.MIN_SHAPE_SCORE
        or winner["held_score"] < receiver.MIN_SHAPE_SCORE
        or winner["held_orbits"] < MIN_ORBITS
    ):
        return winner, "weak_held_arc_prediction", evidence
    if lead <= receiver.MIN_REGION_LEAD:
        return winner, "ambiguous_held_region", evidence
    evidence["region_accepted"] = True
    if winner["boundary_clearance_km"] <= receiver.MIN_BOUNDARY_CLEARANCE_KM:
        return winner, "position_at_tile_boundary", evidence
    return winner, "accepted", evidence


def run(case, work_dir):
    if not case.get("observation_path") or not case.get("catalog_path"):
        return dict(
            status="unavailable",
            reason="missing_observation_or_catalog",
            boundary=BOUNDARY,
            metrics={},
        )
    started = perf_counter()
    try:
        observation = json.loads(Path(case["observation_path"]).read_bytes())
        catalog = Path(case["catalog_path"]).read_bytes()
        winner, reason, evidence = solve(observation, case["regions"], catalog)
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        return dict(
            status="unavailable", reason=f"invalid_input: {error}", boundary=BOUNDARY, metrics={}
        )
    evidence["candidate_s"] = perf_counter() - started
    arm = dict(latlon=None, forced_latlon=None)
    if winner is not None:
        arm["forced_latlon"] = winner["latlon"]
    accepted = reason == "accepted"
    if accepted:
        arm.update(latlon=winner["latlon"], rf_rms_hz=winner["held_rms_hz"])
    return dict(
        status="ok" if accepted else "withheld",
        reason=reason,
        boundary=BOUNDARY,
        metrics=evidence,
        arms=dict(c0=dict(arm), fitted_c=dict(arm)),
    )
