"""Acquire shared nonlinear orbit phases before the unchanged joint regional fit."""

from dataclasses import replace
from itertools import combinations
from time import perf_counter

import numpy as np

from ..reference import grid
from . import joint_orbits as joint
from . import robust_em as lean
from . import robust_orbit_fit as exact

METHOD = "phase_capture"
BOUNDARY = "Native GLRT Graph through blind orbit phase acquisition and unchanged joint gates"
PHASES = np.arange(-15.0, 16.0)
ZERO = int(np.flatnonzero(PHASES == 0)[0])
MAX_POINTS = 12
TRACK_LIMIT = 6
SHAPE_HZ = 500.0
LEVEL_HZ = 3000.0
CEILING = 6.25
MIN_GAIN = 3.0
MIN_PHASE = 3.0
MARGIN = 0.25


def _held(track):
    return int(track.t.mean() // 12) % 5 == 2


def _anchor_check(track):
    return int(track.t.mean() // 12) % 5 == 4


def _independent(a, b):
    return a.lane != b.lane or a.rf != b.rf or a.t[-1] < b.t[0] or b.t[-1] < a.t[0]


def _rotation(phase):
    c, s = np.cos(exact.EARTH_RATE * phase), np.sin(exact.EARTH_RATE * phase)
    zero, one = np.zeros_like(c), np.ones_like(c)
    return np.stack((c, -s, zero, s, c, zero, zero, zero, one), axis=-1).reshape(-1, 3, 3)


def _shift_bank(sky, nominal):
    d = sky.positions_km - nominal.ecef_center_km
    visible = ((d @ nominal.enu_frame[2]) >= -0.08 * np.linalg.norm(d, axis=-1)).any(axis=1)
    sats = tuple(sat for sat, keep in zip(sky.satellites, visible, strict=True) if keep)
    available = grid._valid_states(sats, sky.anchor_utc_ns, nominal.knots_s)[0]
    if len(available) != len(nominal.positions_km):
        raise ValueError("orbital positions differ from the nominal regional bank")
    # Keep original knot alignment and reserve extra support for a shifted bank.
    extra = np.arange(1, 5) * grid.FINE_ORBIT_STEP_S
    knots = np.r_[nominal.knots_s[0] - extra[::-1], nominal.knots_s, nominal.knots_s[-1] + extra]
    valid, position, velocity = grid._valid_states(available, sky.anchor_utc_ns, knots)
    rows = {sat.satnum: i for i, sat in enumerate(available)}
    order = np.array([rows[sat.satnum] for sat in valid], dtype=int)
    return (
        replace(nominal, knots_s=knots, positions_km=position, velocities_km_s=velocity),
        order,
        [int(sat.satnum) for sat in valid],
    )


def cells(bank, track, sites, lane_state):
    """Score phase/identity cells with shape plus harmonic residual level."""
    sampled = np.rint(np.linspace(0, len(track.t) - 1, min(len(track.t), MAX_POINTS))).astype(int)
    t, y = track.t[sampled], track.hz[sampled]
    nt = len(t)
    time = (t + PHASES[:, None]).ravel()
    p, v, _ = grid._interpolated_states(bank, time)
    rotation = _rotation(PHASES)
    p, v = (
        np.einsum("pij,optj->opti", rotation, x.reshape(len(x), len(PHASES), nt, 3)) for x in (p, v)
    )
    d = p - bank.ecef_center_km
    length = np.linalg.norm(d, axis=-1)
    ray = d / length[..., None]
    radial = (ray * v).sum(axis=-1)
    scale = track.rf / grid.LIGHT_SPEED_KM_S
    gradient = scale * ((v - ray * radial[..., None]) @ bank.enu_frame[:2].T) / length[..., None]
    residual = y + scale * radial
    visible = (ray @ bank.enu_frame[2] >= -0.05).all(axis=-1)
    drift = track.drift[sampled]
    residual -= lane_state.bias[track.lane] + lane_state.drift[track.lane] * drift
    # Evaluate all site sentinels with one linear site projection from exact shifted geometry.
    result = np.empty((len(sites), len(p), len(PHASES)), dtype=np.float32)
    for j, site in enumerate(sites):
        shifted = residual - gradient @ site
        center = shifted.mean(axis=-1)
        shape = np.mean((shifted - center[..., None]) ** 2, axis=-1) / SHAPE_HZ**2
        result[j] = np.where(visible, shape + (lean.fold(center) / LEVEL_HZ) ** 2, np.inf)
    return result


def _support(tensor):
    costs = tensor.min(axis=(0, 2))
    order = np.argsort(costs, kind="stable")[:TRACK_LIMIT]
    keep = order[costs[order] < CEILING]
    return keep, tensor[:, keep].copy()


def _anchors(training, tracks, sites, n):
    scores = np.zeros((len(sites), n, len(PHASES)), dtype=np.float32)
    for _, order, cost in training:
        scores[:, order] += np.maximum(0.0, CEILING - cost)
    winners = {}
    for orbit in range(n):
        best = scores[:, orbit] - ((PHASES / 10) ** 2 / 2).astype(np.float32)
        site, phase = np.unravel_index(np.argmax(best), best.shape)
        fixed = float(scores[:, orbit, ZERO].max())
        gain = float(best[site, phase] - fixed)
        if best[site, phase] <= 0:
            continue
        votes = {}
        for k, order, loss in training:
            where = np.flatnonzero(order == orbit)
            if len(where) and loss[site, where[0], phase] < CEILING:
                votes[k] = float(loss[site, where[0], phase])
        independent = any(_independent(tracks[a], tracks[b]) for a, b in combinations(votes, 2))
        winners[orbit] = dict(
            site=int(site),
            phase_index=int(phase),
            phase_s=float(PHASES[phase]),
            zero_score=fixed,
            gain=gain,
            votes=votes,
            independent=independent,
            eligible=bool(independent and abs(PHASES[phase]) >= MIN_PHASE and gain >= MIN_GAIN),
            held=[],
        )
    return winners


def acquire(wide, tracks, lane_state, half):
    """Choose orbit basins by shared support and freeze before held-track evaluation."""
    sites = np.array([(0.0, 0.0), (-half, -half), (-half, half), (half, -half), (half, half)])
    training, hold = [], []
    audited = [i for i, track in enumerate(tracks) if track.curved and not _held(track)]
    count = len(wide.positions_km)
    for index in audited:
        track = tracks[index]
        if _anchor_check(track):
            hold.append(index)
            continue
        keep, loss = _support(cells(wide, track, sites, lane_state))
        training.append((index, keep, loss))
    winners = _anchors(training, tracks, sites, count)
    sites_i, phases_i = np.zeros(count, int), np.full(count, ZERO)
    for orbit, basin in winners.items():
        # Rank each held component against all candidates with training-set choices frozen.
        if basin["independent"]:
            sites_i[orbit], phases_i[orbit] = basin["site"], basin["phase_index"]
    checks = []
    for i in hold:
        losses = cells(wide, tracks[i], sites, lane_state)
        fixed = losses[sites_i, np.arange(count), phases_i]
        order = np.argsort(fixed, kind="stable")[:TRACK_LIMIT]
        finalists = [[int(o), float(fixed[o])] for o in order if np.isfinite(fixed[o])]
        checks.append(dict(track=i, finalists=finalists))
        if len(finalists) < 2:
            continue
        (orbit, cost), (_, competitor) = finalists[:2]
        candidate = winners.get(orbit)
        if (
            candidate
            and cost < CEILING
            and competitor - cost >= MARGIN
            and any(_independent(tracks[i], tracks[j]) for j in candidate["votes"])
        ):
            candidate["held"].append(dict(track=i, loss=cost, margin=competitor - cost))
    picked = {
        orbit: row["phase_s"] for orbit, row in winners.items() if row["eligible"] and row["held"]
    }
    return picked, dict(
        queried_cells=len(audited) * len(sites) * len(PHASES) * count,
        sites_en_km=sites.tolist(),
        training_rows=len(training),
        held_rows=len(hold),
        downstream_held_curved_rows=sum(track.curved and _held(track) for track in tracks),
        held_comparisons=checks,
        basins=winners,
    )


def _shifted(nominal, wide, order, picked):
    if not picked:
        return nominal
    position, velocity = nominal.positions_km.copy(), nominal.velocities_km_s.copy()
    for k, phase in picked.items():
        row = slice(k, k + 1)
        single = replace(
            wide, positions_km=wide.positions_km[row], velocities_km_s=wide.velocities_km_s[row]
        )
        p, v, _ = grid._interpolated_states(single, nominal.knots_s + phase)
        rotation = _rotation(np.asarray([phase]))[0]
        position[order[k]], velocity[order[k]] = p[0] @ rotation.T, v[0] @ rotation.T
    return replace(nominal, positions_km=position, velocities_km_s=velocity)


def infer(document, offer, catalogue):
    """Use current causal TLEs and anonymous tracks. No archived fit enters inference."""
    start = perf_counter()
    tracks, observation = lean.observations(document)
    half = float(offer.get("width_km", 25)) / 2
    if not np.isfinite(half) or half <= 1:
        raise ValueError("expected positive finite tile width over 2 km")
    if len(tracks) < 7:
        return joint.infer(document, offer, catalogue), {}
    sky = grid.prepare_sky(document, catalogue)
    center = tuple(offer["center"])
    nominal = grid.make_tile(sky, center)
    region = exact.Region(offer["id"], center, nominal.ecef_center_km, nominal.enu_frame)
    arcs = [a for track in tracks if (a := lean.shortlist(nominal, track)) is not None]
    train = [a for a in arcs if not _held(a.track) and not _anchor_check(a.track)]
    prep_s = perf_counter() - start
    start = perf_counter()
    wide, order, ids = _shift_bank(sky, nominal)
    lane = lean.initial(train, len(nominal.positions_km))
    if len(train) >= 5:
        trained, _, _ = joint._train(train, lane, len(nominal.positions_km), half)
        lane = trained if trained is not None else lane
    picked, evidence = (
        acquire(wide, tracks, lane, half) if len(ids) and len(train) >= 5 else ({}, {})
    )
    tile = _shifted(nominal, wide, order, picked)
    if picked:
        arcs = [a for track in tracks if (a := lean.shortlist(tile, track)) is not None]
    capture_s = perf_counter() - start
    start = perf_counter()
    fits, metrics, reason = joint.solve(arcs, tile, region, half)
    metrics.update(
        observation,
        **sky.stats,
        **tile.stats,
        shortlisted_tracks=len(arcs),
        prep_s=prep_s,
        phase_capture_s=capture_s,
        fit_s=perf_counter() - start,
        captured_orbits=len(picked),
    )
    arms = {}
    for arm in lean.ARMS:
        fit = fits.get(arm)
        point = region.site(fit.state.xy)[1] if fit else None
        arms[arm] = dict(latlon=point if reason is None else None, forced_latlon=point)
        if fit is not None:
            held = metrics["held_by_arm"].get(arm, {})
            arms[arm].update(
                region_id=None if reason else offer["id"],
                forced_region_id=offer["id"],
                rf_rms_hz=fit.rms_hz,
                radius_km=fit.radius_km,
                frequency_score=fit.score,
                c_hz_per_ghz=fit.state.c_hz_per_ghz,
                held_score=held.get("held_score"),
                held_normalized_mean_loss=held.get("held_normalized_mean_loss"),
            )
    trace = dict(
        **evidence,
        norads=ids,
        accepted=picked,
        lane_bias_hz=lane.bias.tolist(),
        lane_drift_hz_per_100s=lane.drift.tolist(),
        tracks=[
            dict(
                start_s=float(t.t[0]),
                end_s=float(t.t[-1]),
                count=len(t.t),
                lane=t.lane,
                rf_hz=t.rf,
                curved=t.curved,
            )
            for t in tracks
        ],
    )
    result = dict(
        status="ok" if reason is None else "withheld",
        reason=reason,
        boundary=BOUNDARY,
        arms=arms,
        metrics=metrics,
    )
    return result, trace
