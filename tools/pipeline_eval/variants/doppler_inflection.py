"""Track the measured time of minimum Doppler rate and test regional observability."""

from itertools import product

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid, tracker
from . import doppler_turns as shared
from .folded_doppler import _offset
from .peak_paths import read_peaks

METHOD = "doppler_inflection"
BOUNDARY = "Anonymous native GLRT through bracketed steepest-descent timing and causal hypotheses"
HALF = 12.0
JERK = 1.5
SIGMAS = (0.3, 1.0, 3.0, 8.0, 18.0)


def crossing(t, f):
    if len(t) < 10 or np.ptp(t) < 16:
        return None
    x = t / HALF
    A = np.polynomial.polynomial.polyvander(x, 3)
    q, r = np.linalg.qr(A)
    if min(abs(np.diag(r))) < 1e-7:
        return None
    p = np.linalg.solve(r, q.T @ f)
    jerk = 6 * p[3] / HALF**3
    if jerk < JERK:
        return None
    root = -HALF * p[2] / (3 * p[3])
    sides = t - root
    if (
        abs(root) > 2.5
        or np.count_nonzero(sides < 0) < 4
        or np.count_nonzero(sides > 0) < 4
        or sides[0] > -6
        or sides[-1] < 6
        or not ((sides < 0) & (sides >= -2.5)).any()
        or not ((sides > 0) & (sides <= 2.5)).any()
    ):
        return None
    rms = np.sqrt(np.mean((f - A @ p) ** 2))
    grad = np.array([0, 0, -HALF / (3 * p[3]), -root / p[3]])
    sigma = max(95.0, rms) * np.sqrt(2) * np.linalg.norm(np.linalg.solve(r.T, grad))
    if rms > 350 or sigma > 1.25:
        return None
    return float(root), float(sigma), float(jerk)


def scan(t, f):
    head = np.arange(len(t)) % 2 == 0
    events, proposals = [], 0
    seeds = t[(t >= t[0] + 10) & (t <= t[-1] - 10)]
    last = -np.inf
    for at in seeds:
        if at - last < 1.0:
            continue
        last = at
        x = t - at
        primary = (abs(x) <= HALF) & head
        trial = crossing(x[primary], f[primary])
        if trial is None:
            continue
        proposals += 1
        hold = (abs(x) <= HALF) & ~head
        check = crossing(x[hold], f[hold])
        if check is not None and abs(trial[0] - check[0]) <= 1.25:
            events.append(
                dict(
                    time_s=float(at + trial[0]),
                    held_time_s=float(at + check[0]),
                    sigma_s=max(trial[1], check[1], abs(trial[0] - check[0]) / np.sqrt(2)),
                    jerk_hz_s3=trial[2],
                )
            )
    return proposals, events


def unique(events):
    result = []
    for event in sorted(events, key=lambda e: e["sigma_s"]):
        if all(abs(event["time_s"] - e["time_s"]) > 3 for e in result):
            result.append(event)
    return sorted(result, key=lambda e: e["time_s"])


def injections(arcs):
    rng = np.random.default_rng(8519)
    eligible = [a for a in arcs if np.ptp(a["t"]) >= 22][:12]
    rows = []
    for jerk in (2.0, 12.0):
        for arc in eligible:
            t = arc["t"]
            planted = float((t[0] + t[-1]) / 2)
            x = t - planted
            y = -2500 * x + jerk * x**3 / 6 + 40_000 + rng.normal(0, 75, len(t))
            _, found = scan(t, y)
            errs = [abs(e["time_s"] - planted) for e in unique(found)]
            rows.append(
                dict(
                    jerk_hz_s3=jerk,
                    sample_count=len(t),
                    span_s=float(np.ptp(t)),
                    fit_abs_error_s=min(errs, default=None),
                )
            )
    return rows


def empirical(capture):
    lanes, counts = read_peaks(capture)
    chronological = sorted(
        (float(t), i, j) for i, lane in enumerate(lanes) for j, t in enumerate(lane.t)
    )
    linked = shared.AnonymousTracks()
    for t, i, j in chronological:
        lane = lanes[i]
        distinct = []
        for hz in lane.y[j, lane.marks[j] > 0.05]:
            if all(abs(tracker.wrap(float(hz) - previous)) >= 160 for previous in distinct):
                distinct.append(float(hz))
        linked.ingest(t, lane.key, distinct)
    arcs, events, ledger = linked.arcs(), [], []
    for arc in arcs:
        t, f, lane = arc["t"], arc["f"], arc["lane"]
        suggested, observed = scan(t, f)
        ledger.append(
            dict(
                lane=lane,
                first_s=float(t[0]),
                last_s=float(t[-1]),
                points=len(t),
                proposed=suggested,
                held=len(observed),
            )
        )
        events.extend(dict(x, lane=lane) for x in observed)
    return dict(
        counts,
        arc_count=len(arcs),
        usable_arc_count=sum(a["last_s"] - a["first_s"] >= 20 for a in ledger),
        candidate_windows=sum(a["proposed"] for a in ledger),
        held_arcs=sum(bool(a["held"]) for a in ledger),
        events=unique(events),
        arc_inventory=ledger,
        injections=injections(arcs),
    )


def geometry(capture, center):
    sky = grid.prepare_sky(capture, capture.catalog)
    d = sky.positions_km - geodetic_to_ecef_km(*center, 0)
    include = ((d @ ecef_to_enu_matrix(*center)[2]) >= -0.10 * np.linalg.norm(d, axis=-1)).any(
        axis=1
    )
    t = np.arange(0.0, capture.duration_s + 1e-6, 2.0)
    sats, p, v = grid._valid_states(
        [s for s, ok in zip(sky.satellites, include, strict=True) if ok], capture.anchor_utc_ns, t
    )
    return {s.satnum: i for i, s in enumerate(sats)}, t, p, v


def modeled(site, t, p, v, by_id):
    d = p - geodetic_to_ecef_km(*site, 0)
    ray = d / np.linalg.norm(d, axis=-1)[..., None]
    above = ray @ ecef_to_enu_matrix(*site)[2] >= np.sin(np.deg2rad(12))
    f = -11.8e9 / grid.LIGHT_SPEED_KM_S * np.einsum("...i,...i->...", ray, v)
    curvature = np.diff(f, n=2, axis=1) / 4
    a, b = curvature[:, 3:-4], curvature[:, 4:-3]
    visible = np.lib.stride_tricks.sliding_window_view(above, 10, axis=1).all(axis=-1)
    idx, at = np.where(visible & (a < 0) & (b >= 0) & ((b - a) >= 2 * JERK))
    ratio = -a[idx, at] / (b[idx, at] - a[idx, at])
    time = t[at + 4] + 2 * ratio
    ids = list(by_id)
    return {ids[i]: float(s) for i, s in zip(idx, time, strict=True)}


def sensitivity(projections):
    centre, east, west, north, south = (
        projections[k] for k in ((0, 0), (10, 0), (-10, 0), (0, 10), (0, -10))
    )
    ids = sorted(set.intersection(*(set(m) for m in (centre, east, west, north, south))))
    support = [i for i in ids if max(abs(m[i] - centre[i]) for m in (east, west, north, south)) < 8]
    J = np.array([[(east[i] - west[i]) / 20, (north[i] - south[i]) / 20] for i in support]).reshape(
        -1, 2
    )
    span = np.linalg.norm(J, axis=1) * 25
    singular = np.linalg.svd(J, compute_uv=False)
    bound = (
        {str(s): float(s / singular[-1]) for s in SIGMAS}
        if (len(singular) == 2 and singular[-1] > 0)
        else {}
    )
    return dict(
        centre_modeled_events=len(centre),
        known_identity_events=len(J),
        contrast_25km_s=np.percentile(span, [10, 50, 90, 100]).tolist() if len(span) else [],
        ideal_worst_axis_km=bound,
        known_orbit_jacobian=J.tolist(),
    )


def likelihood(candidates, events, duration, held=False):
    pred = np.array(list(candidates.values()))
    if not len(pred):
        return np.log(0.35), 0
    scores, established = [], 0
    for e in events:
        delta = (e["held_time_s"] if held else e["time_s"]) - pred
        sigma = np.hypot(e["sigma_s"], 2)
        mass = (
            0.65
            * duration
            / (len(pred) * sigma * np.sqrt(2 * np.pi))
            * np.exp(-0.5 * (delta / sigma) ** 2)
        )
        denom = mass.sum() + 0.35
        established += mass.max() / denom >= 0.30
        scores.append(np.log(denom))
    return float(np.mean(scores)), int(established)


def measure(capture, tile):
    if tile.get("width_km", 25) != 25:
        raise ValueError("one 25 km square is required")
    center = tile["center"]
    empirical_data = empirical(capture)
    events = empirical_data["events"]
    inside = list(product((-10, 0, 10), repeat=2))
    outside = [(0, 50), (0, -50), (50, 0), (-50, 0)]
    by_id, t, p, v = geometry(capture, center)
    sites = {xy: _offset(center, *xy) for xy in inside + outside}
    profiles = {xy: modeled(site, t, p, v, by_id) for xy, site in sites.items()}
    metrics = empirical_data | sensitivity(profiles)
    metrics.update(
        exterior_modeled_events=[len(profiles[xy]) for xy in outside],
        position_attempted=len(events) >= 4,
    )
    reason, forced, published = "insufficient_bracketed_inflections", None, None
    if len(events) >= 4:
        train, held = events[::2], events[1::2]
        score = {xy: likelihood(z, train, capture.duration_s)[0] for xy, z in profiles.items()}
        test = {
            xy: likelihood(z, held, capture.duration_s, held=True) for xy, z in profiles.items()
        }
        top = max(inside, key=score.__getitem__)
        rivals = [xy for xy in profiles if np.linalg.norm(np.subtract(xy, top)) >= 10]
        gap = test[top][0] - max(test[xy][0] for xy in rivals)
        metrics.update(
            selected_offset_km=top,
            held_log_lead=gap,
            held_identified_events=test[top][1],
            centre_held_score=test[0, 0][0],
            held_score=test[top][0],
            exterior_held_scores=[test[xy][0] for xy in outside],
        )
        forced = list(sites[top])
        reason = "insufficient_held_orbit_or_spatial_separation"
        if test[top][1] >= 2 and gap >= 0.35:
            published, reason = forced, None
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        boundary=BOUNDARY,
        metrics=metrics,
        arms={a: dict(latlon=published, forced_latlon=forced) for a in ("c0", "fitted_c")},
    )
