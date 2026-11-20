"""Refine the lean receiver's fixed assignments using shifted orbital range rate."""

import json
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import numpy as np

from ..reference import grid
from . import robust_em as lean
from .projected_fit import Region

METHOD = "robust_orbit_fit"
BOUNDARY = "Anonymous tracks and causal TLEs through a fixed-assignment range-rate fit"
EARTH_RATE = 7.29211514670698e-5
RELINEARIZATIONS = 3
BACKTRACK = (1.0, 0.5, 0.25, 0.125)


def project(tile, orbit, times, site, phase, rf):
    """Range-rate CFO and its derivatives with respect to site ECEF and orbital phase."""
    orbit_rows = slice(orbit, orbit + 1)
    satellite = replace(
        tile,
        positions_km=tile.positions_km[orbit_rows],
        velocities_km_s=tile.velocities_km_s[orbit_rows],
    )
    position, velocity, acceleration = grid._interpolated_states(satellite, times + phase)
    angle = EARTH_RATE * phase
    c, s = np.cos(angle), np.sin(angle)
    rotate = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    p, v, a = (values[0] @ rotate.T for values in (position, velocity, acceleration))
    delta = p - site
    distance = np.linalg.norm(delta, axis=1)
    ray = delta / distance[:, None]
    radial = np.sum(ray * v, axis=1)
    transverse = v - radial[:, None] * ray
    scale = rf / grid.LIGHT_SPEED_KM_S
    site_gradient = scale * transverse / distance[:, None]
    spin = np.array([0.0, 0.0, EARTH_RATE])
    p_phase = v + np.cross(spin, p)
    v_phase = a + np.cross(spin, v)
    d_phase = np.sum(ray * v_phase, axis=1) + np.sum(transverse * p_phase, axis=1) / distance
    return -scale * radial, site_gradient, -scale * d_phase


def _tangent(region, xy):
    unit = np.eye(2) * 0.001
    return np.column_stack(
        [(region.site(xy + step)[0] - region.site(xy - step)[0]) / 0.002 for step in unit]
    )


def _recenter(rows, tile, region, state):
    site = region.site(state.xy)[0]
    tangent = _tangent(region, state.xy)
    result = []
    for row in rows:
        tr = row.arc.track
        phase = state.phase[row.orbit]
        prediction, d_site, d_phase = project(tile, row.orbit, tr.t, site, phase, tr.rf)
        d_xy = d_site @ tangent
        residual = tr.hz - prediction + d_xy @ state.xy + d_phase * phase
        centered = lean.Arc(
            tr,
            np.array([row.orbit]),
            residual[None],
            d_xy[None],
            d_phase[None],
            np.zeros(1),
            np.zeros(1),
        )
        result.append(replace(row, arc=centered, winner=0))
    return result


def _loss(rows, tile, region, state):
    site = region.site(state.xy)[0]
    exact_square = weighted_square = points = 0
    for row in rows:
        tr = row.arc.track
        prediction, _, _ = project(tile, row.orbit, tr.t, site, state.phase[row.orbit], tr.rf)
        radio = (
            state.bias[tr.lane]
            + tr.drift * state.drift[tr.lane]
            + (tr.rf / 1e9 - 11.5) * state.c_hz_per_ghz
        )
        residual = tr.hz - prediction - radio - row.alias * lean.PERIOD
        innovation = tr.whiten @ residual
        weight = min(1, 40 / len(residual)) / (1 + row.loss / 4)
        exact_square += residual @ residual
        weighted_square += weight * (innovation @ innovation)
        points += len(residual)
    prior = np.r_[
        state.xy / 1000,
        state.bias / (lean.PERIOD / np.sqrt(12)),
        state.drift / 1500,
        state.c_hz_per_ghz / 200000,
        state.phase / lean.PHASE_SD_S,
    ]
    return float(weighted_square + prior @ prior), float(np.sqrt(exact_square / points))


def _blend(first, after, fraction):
    def move(a, b):
        return a + fraction * (b - a)

    return lean.State(
        move(first.xy, after.xy),
        move(first.bias, after.bias),
        move(first.drift, after.drift),
        move(first.phase, after.phase),
        move(first.c_hz_per_ghz, after.c_hz_per_ghz),
    )


def refine(rows, starting_fit, tile, region, half, arm):
    n_orbits = len(tile.positions_km)
    state, radius = starting_fit.state, starting_fit.radius_km
    score, rms = _loss(rows, tile, region, state)
    initial_score = score
    steps = 0
    for _ in range(RELINEARIZATIONS):
        proposal = lean.fit(_recenter(rows, tile, region, state), n_orbits, half, arm)
        if proposal is None:
            break
        radius = proposal.radius_km
        for alpha in BACKTRACK:
            trial = _blend(state, proposal.state, alpha)
            loss, error = _loss(rows, tile, region, trial)
            if loss + 1e-8 < score:
                state, score, rms = trial, loss, error
                steps += 1
                break
        else:
            break
    return lean.Fit(state, rms, score, radius), dict(
        exact_score_at_linear_fit=initial_score,
        accepted_steps=steps,
    )


def solve(arcs, tile, region, half):
    n = len(tile.positions_km)
    held = [arc for arc in arcs if int(arc.track.t.mean() // 12) % 5 == 2]
    train = [arc for arc in arcs if int(arc.track.t.mean() // 12) % 5 != 2]
    if len(train) < 5 or len(held) < 2:
        return None, {}, "insufficient_track_blocks"
    train_state = lean.iterate(train, lean.initial(train, n), n, half)
    if train_state is None:
        return None, {}, "no_training_assignment"
    predicted = lean.assign(held, train_state, update_phase=False)
    supported = [row for row in predicted if row.loss <= 6.25]
    pooled = lean.iterate(arcs, train_state, n, half)
    if pooled is None:
        return None, {}, "no_pooled_assignment"
    owners = [row for row in lean.assign(arcs, pooled, update_phase=False) if row.loss <= 6.25]
    starts = {arm: lean.fit(owners, n, half, arm) for arm in lean.ARMS}
    if any(start is None for start in starts.values()):
        return None, {}, "no_paired_fit"
    paired = {arm: refine(owners, start, tile, region, half, arm) for arm, start in starts.items()}
    fits = {arm: pair[0] for arm, pair in paired.items()}
    m = dict(
        orbit_count=len({row.orbit for row in owners}),
        distinct_radio_lanes=len({row.arc.track.lane for row in owners}),
        fit_tracks=len(owners),
        associated_observations=sum(len(row.arc.track.t) for row in owners),
        curved_fit_tracks=sum(row.arc.track.curved for row in owners),
        held_tracks=len(held),
        held_compatible_tracks=len(supported),
        held_orbits=len({row.orbit for row in supported}),
        held_score=float(np.mean([1 / (1 + row.loss) for row in predicted])),
        separated_orbits=len({row.orbit for row in owners if row.margin >= 0.25}),
        pooled_shift_km=float(np.linalg.norm(fits["c0"].state.xy - train_state.xy)),
        refinement={arm: details for arm, (_, details) in paired.items()},
    )
    reason = None
    if m["orbit_count"] < 4 or m["curved_fit_tracks"] < 4 or m["distinct_radio_lanes"] < 2:
        reason = "insufficient_independent_orbit_support"
    elif m["separated_orbits"] < 3:
        reason = "ambiguous_orbit_assignments"
    elif m["held_orbits"] < 2 or m["held_score"] < 0.28:
        reason = "weak_held_track_support"
    elif m["pooled_shift_km"] > 4 or any(row.radius_km > 6 for row in fits.values()):
        reason = "weak_position_geometry"
    elif any(np.max(np.abs(row.state.xy)) >= half - 0.75 for row in fits.values()):
        reason = "position_at_tile_boundary"
    return fits, m, reason


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
        arcs = [arc for tr in tracks if (arc := lean.shortlist(tile, tr)) is not None]
        metrics.update(shortlisted_tracks=len(arcs), shortlist_s=perf_counter() - start)
        start = perf_counter()
        fits, fitted, reason = solve(arcs, tile, region, half)
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
    if any(not path or not Path(path).is_file() for path in (observation, catalogue)):
        return dict(
            status="unavailable",
            reason="missing anonymous tracks or causal catalogue",
            boundary=BOUNDARY,
            arms={a: {"latlon": None} for a in lean.ARMS},
            metrics={},
        )
    if len(case["regions"]) != 1:
        return dict(
            status="unavailable",
            reason="single supplied tile required",
            boundary=BOUNDARY,
            arms={a: {"latlon": None} for a in lean.ARMS},
            metrics={},
        )
    return infer(
        json.loads(Path(observation).read_bytes()), case["regions"][0], Path(catalogue).read_text()
    )
