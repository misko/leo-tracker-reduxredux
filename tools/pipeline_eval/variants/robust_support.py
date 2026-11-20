"""Validate the lean position fit against guarded observations on physical tracks."""

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from struct import pack
from time import perf_counter

import numpy as np
from scipy.linalg import cholesky, solve_triangular

from ..reference import grid
from . import robust_em as lean
from .projected_fit import Region

METHOD = "robust_support"
BOUNDARY = "Anonymous GLRT tracks and causal TLEs through a guarded predictive position fit"
HOLD_HALF_S = 4.0
GUARD_S = 8.0
LOSS_LIMIT = 6.25


def _covariance(left, right):
    return lean.CORRELATED_HZ**2 * np.exp(-abs(left[:, None] - right) / lean.CORRELATION_S)


def _noise(times):
    covariance = _covariance(times, times)
    covariance.flat[:: len(times) + 1] += lean.WHITE_HZ**2
    return covariance


def split(track):
    """Choose the withheld block from timestamps before seeing its measurements."""
    times = track.t
    first, last = times[0], times[-1]
    bit = sha256(pack(">dd", first, last)).digest()[0] & 1
    center = first + (0.35, 0.65)[bit] * (last - first)
    delta = abs(times - center)
    held = delta <= HOLD_HALF_S
    train = delta > HOLD_HALF_S + GUARD_S
    if held.sum() < 4 or train.sum() < 8:
        return track, None
    t, y = times[train], track.hz[train]
    dt, dy = t - t.mean(), y - y.mean()
    curvature = dy - dt * (dy @ dt) / (dt @ dt)
    whiten = solve_triangular(cholesky(_noise(t), lower=True), np.eye(len(t)), lower=True)
    return replace(
        track,
        t=t,
        hz=y,
        drift=track.drift[train],
        whiten=whiten,
        curved=bool(np.ptp(t) >= 20 and np.sqrt(np.mean(curvature**2)) >= 250),
    ), held


def _innovation(train_t, held_t, whiten, train_residual, held_residual):
    cross = _covariance(held_t, train_t) @ whiten.T
    conditional = held_residual - cross @ (whiten @ train_residual)
    conditional_covariance = _noise(held_t) - cross @ cross.T
    return solve_triangular(cholesky(conditional_covariance, lower=True), conditional, lower=True)


def _training_residual(row, state):
    arc, j = row.arc, row.winner
    return arc.residual[j] - arc.xy[j] @ state.xy - arc.phase[j] * state.phase[row.orbit]


def _radio(track, state, drift, alias):
    return (
        state.bias[track.lane]
        + drift * state.drift[track.lane]
        + (track.rf / 1e9 - 11.5) * state.c_hz_per_ghz
        + alias * lean.PERIOD
    )


def held_loss(row, tile, track, mask, state):
    """Predict the fixed training satellite, phase and alias on original withheld points."""
    orbit = slice(row.orbit, row.orbit + 1)
    one = replace(
        tile, positions_km=tile.positions_km[orbit], velocities_km_s=tile.velocities_km_s[orbit]
    )
    t = track.t[mask]
    position, velocity, accel = (x[0] for x in grid._interpolated_states(one, t))
    delta = position - tile.ecef_center_km
    distance = np.linalg.norm(delta, axis=1)
    ray = delta / distance[:, None]
    if (ray @ tile.enu_frame[2] < -0.035).any():
        return float("inf")
    radial = (ray * velocity).sum(axis=1)
    transverse = velocity - radial[:, None] * ray
    scale = track.rf / grid.LIGHT_SPEED_KM_S
    fdot = -scale * ((ray * accel).sum(axis=1) + (transverse**2).sum(axis=1) / distance)
    xy = scale * (transverse @ tile.enu_frame[:2].T) / distance[:, None]
    held = track.hz[mask] + scale * radial - xy @ state.xy - fdot * state.phase[row.orbit]
    held -= _radio(track, state, track.drift[mask], row.alias)
    train = row.arc.track
    residual = _training_residual(row, state) - _radio(train, state, train.drift, row.alias)
    innovation = _innovation(train.t, t, train.whiten, residual, held)
    return float(np.mean(innovation**2))


def solve(arcs, training, holdouts, tile, half):
    n = len(tile.positions_km)
    details = dict(guarded_tracks=len(holdouts), training_tracks=len(training))
    if len(training) < 5:
        return None, details, "insufficient_track_blocks"
    state = lean.iterate(training, lean.initial(training, n), n, half)
    if state is None:
        return None, details, "no_training_assignment"
    known = [r for r in lean.assign(training, state, update_phase=False) if r.loss <= LOSS_LIMIT]
    pooled = lean.iterate(arcs, state, n, half)
    if pooled is None:
        return None, details, "no_pooled_assignment"
    owners = [r for r in lean.assign(arcs, pooled, update_phase=False) if r.loss <= LOSS_LIMIT]
    training_fits = {a: lean.fit(known, n, half, a) for a in lean.ARMS}
    fits = {a: lean.fit(owners, n, half, a) for a in lean.ARMS}
    if any(value is None for value in (*fits.values(), *training_fits.values())):
        return None, details, "no_paired_fit"

    evidence = {}
    held_rows = [row for row in known if id(row.arc.track) in holdouts]
    for arm, training_fit in training_fits.items():
        tests = [
            (r, held_loss(r, tile, *holdouts[id(r.arc.track)], training_fit.state))
            for r in held_rows
        ]
        supported = [r for r, loss in tests if loss <= LOSS_LIMIT and r.margin >= 0.25]
        evidence[arm] = dict(
            held_tracks=len(tests),
            held_points=sum(int(holdouts[id(r.arc.track)][1].sum()) for r, _ in tests),
            held_compatible_tracks=len(supported),
            held_orbits=len({r.orbit for r in supported}),
            held_score=float(np.mean([1 / (1 + loss) for _, loss in tests])) if tests else 0.0,
            training_radius_km=training_fit.radius_km,
            pooled_shift_km=float(np.linalg.norm(fits[arm].state.xy - training_fit.state.xy)),
        )
    details.update(
        orbit_count=len({r.orbit for r in owners}),
        distinct_radio_lanes=len({r.arc.track.lane for r in owners}),
        fit_tracks=len(owners),
        associated_observations=sum(len(r.arc.track.t) for r in owners),
        curved_fit_tracks=sum(r.arc.track.curved for r in owners),
        separated_orbits=len({r.orbit for r in owners if r.margin >= 0.25}),
        held=evidence,
    )
    reason = None
    if (
        details["orbit_count"] < 4
        or details["curved_fit_tracks"] < 4
        or details["distinct_radio_lanes"] < 2
    ):
        reason = "insufficient_independent_orbit_support"
    elif details["separated_orbits"] < 3:
        reason = "ambiguous_orbit_assignments"
    elif any(e["held_orbits"] < 2 or e["held_score"] < 0.28 for e in evidence.values()):
        reason = "weak_guarded_track_support"
    elif any(e["pooled_shift_km"] > 4 for e in evidence.values()) or any(
        f.radius_km > 6 for f in fits.values()
    ):
        reason = "weak_position_geometry"
    elif any(np.max(np.abs(f.state.xy)) >= half - 0.75 for f in fits.values()):
        reason = "position_at_tile_boundary"
    return fits, details, reason


def infer(document, offer, catalogue):
    start = perf_counter()
    tracks, metrics = lean.observations(document)
    metrics["observation_s"] = perf_counter() - start
    center = tuple(offer["center"])
    half = float(offer.get("width_km", 25)) / 2
    if half <= 1 or not np.isfinite(half):
        raise ValueError("expected positive finite tile width greater than 2 km")
    arms = {arm: {"latlon": None} for arm in lean.ARMS}
    fits, reason = None, "insufficient_track_inventory"
    if len(tracks) >= 7:
        start = perf_counter()
        sky = grid.prepare_sky(document, catalogue)
        tile = grid.make_tile(sky, center)
        region = Region(offer["id"], center, tile.ecef_center_km, tile.enu_frame)
        metrics.update(sky.stats, **tile.stats)
        metrics["orbit_s"] = perf_counter() - start
        start = perf_counter()
        arcs, training, holdouts = [], [], {}
        for track in tracks:
            arc = lean.shortlist(tile, track)
            if arc is not None:
                arcs.append(arc)
            retained, held = split(track)
            train_arc = arc if held is None else lean.shortlist(tile, retained)
            if train_arc is None:
                continue
            training.append(train_arc)
            if held is not None:
                holdouts[id(retained)] = (track, held)
        metrics.update(shortlisted_tracks=len(arcs), shortlist_s=perf_counter() - start)
        start = perf_counter()
        fits, fitted, reason = solve(arcs, training, holdouts, tile, half)
        metrics.update(fitted, fit_s=perf_counter() - start)
    if fits is not None:
        for arm, fit in fits.items():
            point = region.site(fit.state.xy)[1]
            arms[arm] = dict(
                latlon=None if reason else point,
                forced_latlon=point,
                region_id=None if reason else offer["id"],
                forced_region_id=offer["id"],
                rf_rms_hz=fit.rms_hz,
                frequency_score=fit.score,
                c_hz_per_ghz=fit.state.c_hz_per_ghz,
                radius_km=fit.radius_km,
            )
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        arms=arms,
        metrics=metrics,
        boundary=BOUNDARY,
    )


def run(case, work_dir):
    observation, catalogue = (case.get(field) for field in ("observation_path", "catalog_path"))
    if (
        any(not path or not Path(path).is_file() for path in (observation, catalogue))
        or len(case["regions"]) != 1
    ):
        return dict(
            status="unavailable",
            reason="requires anonymous tracks, causal catalogue and one supplied tile",
            boundary=BOUNDARY,
            arms={a: {"latlon": None} for a in lean.ARMS},
            metrics={},
        )
    return infer(
        json.loads(Path(observation).read_bytes()), case["regions"][0], Path(catalogue).read_text()
    )
