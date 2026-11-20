"""Worldwide anonymous Doppler search with wrapped shared receiver clocks."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from time import perf_counter

import numpy as np
from scipy.spatial import cKDTree

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid
from . import blind_track_identity as raw
from . import fixed_orbit_position as physical
from . import folded_doppler as geodesy
from . import peak_paths as orbit

METHOD = "absolute_doppler"
BOUNDARY = "Worldwide anonymous native GLRT arcs through causal Doppler and wrapped receiver clock"
MAX_ARCS_PER_GROUP = 4
SITES = 192
LEVELS = np.linspace(-physical.PERIOD_HZ / 2, physical.PERIOD_HZ / 2, 112, endpoint=False)
K = 6
CEILING = 12.0
PHASE_BOUND = 18.0


@dataclass(frozen=True)
class Arc:
    time: np.ndarray
    frequency: np.ndarray
    rf: float
    group: int
    channel: int
    train: int
    position: np.ndarray
    velocity: np.ndarray
    accel: np.ndarray
    overhead: cKDTree


@dataclass(frozen=True)
class Site:
    point: tuple
    losses: tuple
    assignments: tuple
    levels: tuple


def bank(capture):
    sky = grid.prepare_sky(capture, capture.catalog)
    t = np.arange(-25, capture.duration_s + 31, 5)
    sats, position, velocity = grid._valid_states(sky.satellites, capture.anchor_utc_ns, t)
    all_earth = grid.Tile(np.zeros(3), np.eye(3), capture.duration_s, t, position, velocity, {})
    return all_earth, np.array([s.satnum for s in sats]), sky.stats


def arc_data(tracks, states):
    slots = defaultdict(list)
    for track in tracks:
        t, y = track["times"], track["values"]
        first = np.searchsorted(t, t[0] + 0.61 * np.ptp(t))
        if first < 8 or len(t) - first < 5:
            continue
        group = 2 * track["receiver"] + int(track["channel"] > 4)
        slots[group].append((len(t) * np.ptp(t), track, first))
    arcs = []
    for group, tracks in slots.items():
        for _, a, first in sorted(tracks, key=lambda item: -item[0])[:MAX_ARCS_PER_GROUP]:
            t, y = (np.asarray(a[k]) for k in ("times", "values"))
            use = np.r_[
                np.linspace(0, first - 1, 6).astype(int),
                np.linspace(first, len(t) - 1, 5).astype(int),
            ]
            times, y = t[use], y[use]
            p, v, acc = grid._interpolated_states(states, times[:6])
            middle = p[:, 3, :]
            tree = cKDTree(middle / np.linalg.norm(middle, axis=1)[:, None])
            arcs.append(Arc(times, y, float(a["rf_hz"]), group, a["channel"], 6, p, v, acc, tree))
    return arcs


def linear_options(arc, xyz, up):
    idx = np.asarray(arc.overhead.query_ball_point(up, 0.51, return_sorted=True), dtype=int)
    d = arc.position[idx] - xyz
    ranges = np.linalg.norm(d, axis=-1)
    use = (d @ up >= 0.025 * ranges).all(axis=1)
    d, ranges, idx = d[use], ranges[use], idx[use]
    ray = d / ranges[..., None]
    v, acc = arc.velocity[idx], arc.accel[idx]
    radial = np.einsum("...i,...i->...", ray, v)
    gain = -arc.rf / grid.LIGHT_SPEED_KM_S
    f = gain * radial
    # Rotate the shifted ECEF state back to the receive-time frame.
    rotated_p = v + orbit.EARTH_ROTATION * np.cross([0, 0, 1], arc.position[idx])
    rotated_v = acc + orbit.EARTH_ROTATION * np.cross([0, 0, 1], v)
    orth = v - radial[..., None] * ray
    fdot = gain * (
        np.einsum("...i,...i->...", orth, rotated_p) / ranges
        + np.einsum("...i,...i->...", ray, rotated_v)
    )
    y = arc.frequency[: arc.train] - f
    z = y - y.mean(axis=1, keepdims=True)
    grad = fdot - fdot.mean(axis=1, keepdims=True)
    h = np.sum(grad**2, axis=1)
    phase = np.clip(np.sum(z * grad, axis=1) / (h + 120**2), -PHASE_BOUND, PHASE_BOUND)
    r = y - phase[:, None] * fdot
    level = r.mean(axis=1)
    shape = np.mean(((r - level[:, None]) / 450) ** 2, axis=1) + (phase / 12) ** 2
    j = np.argsort(shape, kind="stable")[:K]
    return idx[j], phase[j], level[j], shape[j]


def common_level(options):
    """Each arc contributes at most one capped vote to a shared circular offset."""
    if not options:
        return 0.0, [], []
    costs = []
    for _, _, level, fit in options:
        error = physical.fold(level[None, :] - LEVELS[:, None])
        costs.append(fit[None, :] + (error / 1300) ** 2)
    profile = np.array([np.minimum(z.min(axis=1), CEILING) for z in costs])
    i = int(np.argmin(profile.sum(axis=0)))
    j = [int(z[i].argmin()) for z in costs]
    return float(LEVELS[i]), j, list(profile[:, i])


def evaluate(arcs, point):
    xyz = geodetic_to_ecef_km(*point, 0)
    up = ecef_to_enu_matrix(*point)[2]
    options = [linear_options(a, xyz, up) for a in arcs]
    free, common = [None] * len(arcs), [None] * len(arcs)
    b = np.zeros(4)
    heads = np.full((2, len(arcs)), CEILING)
    for i, (o, p, offset, loss) in enumerate(options):
        if len(o) and loss[0] < CEILING:
            free[i] = (int(o[0]), float(p[0]), float(offset[0]))
            heads[1, i] = loss[0]
    for group in range(4):
        take = [i for i, a in enumerate(arcs) if a.group == group and len(options[i][0])]
        b[group], picked, loss = common_level([options[i] for i in take])
        for i, j, cost in zip(take, picked, loss, strict=True):
            if cost < CEILING:
                o, phase, offset, _ = options[i]
                common[i] = int(o[j]), float(phase[j]), float(offset[j])
                heads[0, i] = cost
    return Site(tuple(point), tuple(heads.sum(axis=1)), (common, free), (tuple(b), ()))


def nearby(point, step):
    return [
        geodesy._offset(point, east * step, north * step)
        for east, north in product((-1, 0, 1), repeat=2)
    ]


def search(arcs):
    data = {}

    def visit(p):
        key = tuple(float(s) for s in np.around(p, 8))
        if key not in data:
            data[key] = evaluate(arcs, key)
        return data[key]

    prior = [visit(p) for p in geodesy.earth_mesh(SITES)]
    beams = []
    for mode in range(2):
        found = sorted(prior, key=lambda s: s.losses[mode])[:4]
        for step in (400, 125, 38, 11):
            found = [
                min((visit(p) for p in nearby(f.point, step)), key=lambda s: s.losses[mode])
                for f in found
            ]
        beams.append(sorted(found, key=lambda s: s.losses[mode]))
    return data, beams


def exact(states, arcs, site, assignments):
    xyz = geodetic_to_ecef_km(*site, 0)
    predictions, observed, train, group, rf = [], [], [], [], []
    for a, (row, phase, _) in zip(arcs, assignments, strict=True):
        local = orbit.slice_orbit(states, slice(row, row + 1))
        f = orbit.orbit_geometry(local, a.time, phase, xyz, a.rf)[0]
        predictions.extend(f)
        observed.extend(a.frequency)
        train.extend(np.arange(len(a.time)) < a.train)
        group.extend([a.group] * len(a.time))
        rf.extend([a.rf] * len(a.time))
    return tuple(np.asarray(x) for x in (predictions, observed, train, group, rf))


def clock_fit(y, X, use, fitted):
    """Fit offsets on the training support and penalize only the RF slope."""
    prior = np.zeros((1, X.shape[1]))
    if fitted:
        prior[0, -1] = 1 / 3500
    state = np.zeros(X.shape[1])
    for _ in range(4):
        residual = y[use] - X[use] @ state
        w = 1 / np.hypot(500, residual)
        matrix = np.vstack((X[use] * w[:, None], prior))
        state = np.linalg.lstsq(matrix, np.r_[y[use] * w, 0.0], rcond=None)[0]
        if fitted:
            state[-1] = np.clip(state[-1], -8000, 8000)
    return state, y - X @ state


def refine(states, arcs, start, mode, numbers):
    rows = [(a, r) for a, r in zip(arcs, start.assignments[mode], strict=True) if r is not None]
    if len(rows) < 3:
        return None
    arcs, chosen = zip(*rows, strict=True)
    f, y, use, group, rf = exact(states, arcs, start.point, chosen)
    owner = [int(numbers[r[0]]) for r in chosen]
    offsets = physical.fold(
        np.array(
            [r[2] if mode else start.levels[0][a.group] for a, r in zip(arcs, chosen, strict=True)]
        )
    )
    lengths = np.array([len(a.time) for a in arcs])
    if mode:
        labels = np.repeat(np.arange(len(arcs)), lengths)
        design = np.eye(len(arcs))[labels]
    else:
        design = np.eye(4)[group]
    # One integer alias per continuously linked arc, retained through both arms and both time sets.
    res = [
        np.mean(a.frequency[: a.train] - z[: a.train])
        for a, z in zip(arcs, np.split(f, np.cumsum(lengths)[:-1]), strict=True)
    ]
    aliases = np.rint((np.array(res) - offsets) / physical.PERIOD_HZ).astype(int)
    base = np.repeat(offsets + aliases * physical.PERIOD_HZ, lengths)
    out = {}
    # Both arms evaluate exactly these sites and use exactly these owners and integer branches.
    lattice = nearby(start.point, 5)
    has_rf_contrast = not mode and any(len(set(rf[group == i])) >= 2 for i in np.unique(group))
    for arm in physical.ARMS:
        fitted = arm == "fitted_c" and has_rf_contrast
        X = np.column_stack((design, rf / 1e9 - 11.5)) if fitted else design
        options = []
        for point in lattice:
            f, _, _, _, _ = exact(states, arcs, point, chosen)
            x, residual = clock_fit(y - f - base, X, use, fitted)
            score = np.log1p((residual[use] / 500) ** 2).mean()
            options.append((score, point, x, residual))
        _, point, x, residual = min(options, key=lambda r: r[0])
        passed = [
            np.sqrt(np.mean(rr[a.train :] ** 2)) <= 1200
            for a, rr in zip(arcs, np.split(residual, np.cumsum(lengths)[:-1]), strict=True)
        ]
        groups = {a.group for a, ok in zip(arcs, passed, strict=True) if ok}
        carriers = {a.rf for a, ok in zip(arcs, passed, strict=True) if ok}
        families = {n for n, ok in zip(owner, passed, strict=True) if ok}
        out[arm] = dict(
            latlon=None,
            forced_latlon=list(point),
            rf_rms_hz=physical.rmshz(residual[use]),
            held_rms_hz=physical.rmshz(residual[~use]),
            held_cost=float(np.log1p((residual[~use] / 500) ** 2).mean()),
            held_points=int((~use).sum()),
            held_good_orbits=len(families),
            held_good_groups=len(groups),
            held_good_carriers=len(carriers),
            c_hz_per_ghz=float(x[-1]) if fitted else 0.0 if arm == "c0" else None,
            c_identifiable=has_rf_contrast,
            selected_norads=owner,
            train_aliases=aliases.tolist(),
            receiver_levels_hz=physical.fold(
                offsets + (x[:4][[a.group for a in arcs]] if not mode else x)
            ).tolist(),
        )
    return out


def finish(states, numbers, arcs, sites, finalists, mode, metrics):
    start = perf_counter()
    metrics = dict(metrics)
    arms = {k: dict(latlon=None, forced_latlon=None) for k in physical.ARMS}
    reason = "insufficient_anonymous_arcs"
    if finalists:
        fitted = [refine(states, arcs, point, mode, numbers) for point in finalists]
        metrics.update(
            world_sites=len(sites),
            evaluated_points=list(sites),
            coarse_sites=SITES,
            finalist_count=len(fitted),
            train_location_scores=[float(p.losses[mode]) for p in finalists],
        )
        reason = "insufficient_supported_orbits"
        if fitted[0] is not None:
            arms = fitted[0]
            reason = None
            for arm, value in arms.items():
                xyz = geodetic_to_ecef_km(*value["forced_latlon"], 0)
                rivals = [
                    f[arm]["held_cost"]
                    for f in fitted[1:]
                    if f is not None
                    and np.linalg.norm(geodetic_to_ecef_km(*f[arm]["forced_latlon"], 0) - xyz) >= 30
                ]
                gap = min(rivals) - value["held_cost"] if rivals else None
                value["held_geographic_lead"] = gap
                if (
                    value["held_good_orbits"] < 4
                    or value["held_good_carriers"] < 3
                    or value["held_good_groups"] < 2
                ):
                    reason = reason or "insufficient_held_absolute_frequency_support"
                elif value["held_rms_hz"] > 750 or gap is None or gap < 0.65:
                    reason = reason or "ambiguous_worldwide_position"
            if reason is None:
                for p in arms.values():
                    p["latlon"] = p["forced_latlon"]
    metrics["final_fit_s"] = perf_counter() - start
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        boundary=BOUNDARY,
        metrics=metrics,
        arms=arms,
    )


def paired(capture):
    start = perf_counter()
    _, tracks, stats = raw.observations(capture, False)
    states, numbers, sky = bank(capture)
    arcs = arc_data(tracks, states)
    sites, beams = search(arcs) if len(arcs) >= 4 else ({}, [[], []])
    metrics = dict(
        stats,
        **sky,
        selected_arcs=len(arcs),
        anonymous_arcs=len(tracks),
        accounted_orbits=len(numbers),
        supplied_location=False,
        shared_search_s=perf_counter() - start,
    )
    return [
        finish(states, numbers, arcs, sites, finalists, mode, metrics)
        for mode, finalists in enumerate(beams)
    ]


def solve(capture, *, shared_clock=True):
    return paired(capture)[0 if shared_clock else 1]
