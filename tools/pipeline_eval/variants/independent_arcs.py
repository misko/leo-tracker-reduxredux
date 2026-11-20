"""Use matched receiver peaks to corroborate, and never require, an orbital arc."""

from dataclasses import replace
from time import perf_counter

import numpy as np
from scipy.optimize import lsq_linear, minimize_scalar

from . import paired_peaks as paired
from . import peak_paths as paths

METHOD = "independent_arcs"
BOUNDARY = (
    "Full anonymous native GLRT peaks, one causal TLE, and one offered tile "
    "through independent-orbit Doppler fits"
)
LIMIT = 96


def corroborate(lanes, fused, flags, calibration, duration):
    """Attach a physical pair identifier to the nearest raw peak on each lane."""
    by_rf = {lane.key[1:]: (lane, flag) for lane, flag in zip(fused, flags, strict=True)}
    result = []
    for lane in lanes:
        rx, channel, rf = lane.key
        ids = np.full(lane.y.shape, -1, dtype=np.int16)
        if (channel, rf) in by_rf:
            other, pair = by_rf[channel, rf]
            positions = {int(v): i for i, v in enumerate(other.visit)}
            own = np.array([positions.get(int(v), -1) for v in lane.visit])
            rows = np.flatnonzero(own >= 0)
            model = calibration[int(channel > 4)]
            shift = rx * (
                model["offset_hz"] + model["drift_hz_per_s"] * (lane.t[rows] - duration / 2)
            )
            delta = abs(
                paths.fold(
                    lane.y[rows, :, None] - shift[:, None, None] - other.y[own[rows], None, :]
                )
            )
            delta = np.where(pair[own[rows], None, :], delta, np.inf)
            for j in range(paths.PEAKS):
                k = delta[:, :, j].argmin(axis=1)
                match = (
                    delta[np.arange(len(rows)), k, j] <= paired.PAIR_HZ / 2 + 1e-6
                ) & np.isfinite(lane.marks[rows, k])
                ids[rows[match], k[match]] = j
        result.append(ids)
    return result


def increments(lane):
    """Sample two-neighbour folded slopes without choosing a receiver clock level."""
    row = np.flatnonzero(np.max(lane.marks, axis=1) > 0)
    col = lane.marks[row].argmax(axis=1)
    t, y = lane.t[row], lane.y[row, col]
    right = np.searchsorted(t, t + 0.64)
    left = np.flatnonzero(right < len(t))
    left = left[t[right[left]] - t[left] <= 2.6]
    left = left[:: max(1, (len(left) + 159) // 160)]
    right = right[left]
    when, inverse = np.unique(np.r_[t[left], t[right]], return_inverse=True)
    i, j = np.split(inverse, 2)
    return when, i, j, paths.fold(y[right] - y[left]), (t[left] // 25).astype(int)


def shortlist(bank, lane, pair_ids, lane_no):
    times, i, j, dy, interval = increments(lane)
    found, evaluated = [], 0
    if len(i) < 2:
        return found, evaluated
    for phase in paths.PHASES:
        support = []
        for start in range(0, len(bank.positions_km), 128):
            sub = paths.slice_orbit(bank, slice(start, start + 128))
            f = paths.orbit_geometry(
                sub, times, phase, bank.ecef_center_km, lane.key[2], horizon=True
            )
            e = abs(paths.fold(dy - (f[:, j] - f[:, i])))
            reward = np.where(np.isfinite(e), np.maximum(0, 1 - e / 650), 0)
            support.extend(
                np.column_stack(
                    [reward[:, interval == k].sum(axis=1) for k in np.unique(interval)]
                ).max(axis=1)
            )
        ranking = np.argsort(-np.asarray(support), kind="stable")[:LIMIT]
        for start in range(0, len(ranking), 64):
            ids = ranking[start : start + 64]
            evaluated += len(ids)
            sub = paths.slice_orbit(bank, ids)
            f = paths.orbit_geometry(
                sub, lane.t, phase, bank.ecef_center_km, lane.key[2], horizon=True
            )
            score, trace = paths.decode(lane, f)
            for k in np.argsort(-score, kind="stable")[:18]:
                use = np.flatnonzero(trace[k] >= 0)
                x = lane.t[use]
                if len(x) < 12 or np.ptp(x) < 14:
                    continue
                y = lane.y[use, trace[k, use]]
                level = paths.fold(y - f[k, use])
                offset = paths.fold(np.median(level[0] + paths.fold(level - level[0])))
                rms = np.std(paths.fold(level - offset))
                t = x - x.mean()
                signal = f[k, use] - f[k, use].mean()
                if rms > 2200 or np.std(signal - t * (t @ signal) / (t @ t)) < 100:
                    continue
                found.append(
                    dict(
                        lane=lane_no,
                        orbit=int(ids[k]),
                        phase=phase,
                        t=x,
                        visit=lane.visit[use],
                        y=y,
                        offset=float(offset),
                        pairs=pair_ids[use, trace[k, use]],
                        strength=float(score[k] / (1 + (rms / 1200) ** 2)),
                    )
                )
    return sorted(found, key=lambda a: -a["strength"])[:32], evaluated


def unique(paths_selected, lanes):
    """Use one occurrence of a verified pair, even if two orbits claim it."""
    seen = set()
    selected = []
    for arc in paths_selected:
        channel, rf = lanes[arc["lane"]].key[1:]
        keys = [
            (channel, rf, int(v), int(p)) for v, p in zip(arc["visit"], arc["pairs"], strict=True)
        ]
        keep = np.array([k[-1] < 0 or k not in seen for k in keys])
        if keep.sum() < 5:
            continue
        seen.update(k for k in keys if k[-1] >= 0)
        selected.append(arc | {k: arc[k][keep] for k in ("t", "visit", "y", "pairs")})
    return selected


def clock_levels(lanes, arcs):
    """Estimate each clock level using the included training orbits alone."""
    values = np.zeros(4)
    for group in range(4):
        offsets = np.array([a["offset"] for a in arcs if lanes[a["lane"]].group == group])
        if len(offsets):
            values[group] = paths.fold(offsets[0] + np.median(paths.fold(offsets - offsets[0])))
    return values


def fit(bank, lanes, arcs, levels, bound, fitted):
    # Adjacent c columns are never constructed in the c=0 arm.
    base = 10 + fitted
    orbit = {o: base + i for i, o in enumerate(sorted({a["orbit"] for a in arcs}))}
    records = []
    for a in arcs:
        lane = lanes[a["lane"]]
        sub = paths.slice_orbit(bank, slice(a["orbit"], a["orbit"] + 1))
        rf, group = lane.key[2], lane.group
        f = paths.orbit_geometry(sub, a["t"], a["phase"], bank.ecef_center_km, rf)[0]
        nominal = f + levels[group]
        records.append((a, sub, rf, group, nominal + paths.fold(a["y"] - nominal)))
    prior = 1 / np.array([1000] * 2 + [3000] * 4 + [35] * 4 + [2000] * fitted + [3] * len(orbit))
    cap = np.array([bound] * 2 + [6000] * 4 + [125] * 4 + [8000] * fitted + [7.5] * len(orbit))
    state = np.zeros(len(prior))

    def evaluate(x, design=False):
        xyz = paths.site(bank, x[:2])[0]
        residuals, jacobians = [], []
        for a, sub, rf, group, y in records:
            j = orbit[a["orbit"]]
            phase = a["phase"] + x[j]
            time = a["t"] - bank.duration_s / 2
            f, g = paths.orbit_geometry(sub, a["t"], phase, xyz, rf)
            coeff = rf / 1e9 - 11.5
            nuisance = levels[group] + x[2 + group] + time * x[6 + group]
            residuals.append(y - f - nuisance - (coeff * x[10] if fitted else 0.0))
            if design:
                A = np.zeros((len(time), len(x)))
                A[:, :2], A[:, 2 + group], A[:, 6 + group] = g, 1, time
                if fitted:
                    A[:, 10] = coeff
                A[:, j] = (
                    paths.orbit_geometry(sub, a["t"], phase + 0.03, xyz, rf)[0]
                    - paths.orbit_geometry(sub, a["t"], phase - 0.03, xyz, rf)[0]
                ) / 0.06
                jacobians.append(A)
        return np.concatenate(residuals), np.vstack(jacobians) if design else None

    def cost(x, r):
        return np.log1p((r / 420) ** 2).sum() + np.square(x * prior).sum()

    for _ in range(5):
        r, A = evaluate(state, True)
        w = 1 / np.hypot(420, r)
        delta = lsq_linear(
            np.vstack((A * w[:, None], np.diag(prior))),
            np.r_[r * w, -state * prior],
            bounds=(-cap - state - 1e-10, cap - state + 1e-10),
            max_iter=36,
        ).x
        current = cost(state, r)
        for alpha in (1, 0.5, 0.25, 0.125):
            proposal = np.clip(state + alpha * delta, -cap, cap)
            if cost(proposal, evaluate(proposal)[0]) < current:
                state = proposal
                break
        else:
            break
    residual, A = evaluate(state, True)
    q = A / np.hypot(420, residual)[:, None]
    covariance = np.linalg.inv(q.T @ q + np.diag(prior**2))
    radius = float(2.45 * np.sqrt(np.linalg.eigvalsh(covariance[:2, :2])[-1]))
    # Keep the shared held-decoder state layout without adding a fitted parameter.
    if not fitted:
        state = np.insert(state, 10, 0.0)
    return (
        state,
        {o: j - base for o, j in orbit.items()},
        float(np.sqrt(np.mean(residual**2))),
        radius,
    )


def test_identity(bank, lane, arc, alternatives, nuisance, level):
    """Fit shared state on other orbits and tune this orbit's phase on training peaks."""
    x = nuisance[0]
    group, rf = lane.group, lane.key[2]
    site = paths.site(bank, x[:2])[0]

    def model(o, t, phase, horizon=False):
        sub = paths.slice_orbit(bank, slice(o, o + 1))
        f = paths.orbit_geometry(sub, t, phase, site, rf, horizon=horizon)[0]
        return (
            f
            + level
            + x[2 + group]
            + x[6 + group] * (t - bank.duration_s / 2)
            + x[10] * (rf / 1e9 - 11.5)
        )

    held = (
        paths.blocks(lane.t)[1] & (lane.t >= arc["t"].min() - 60) & (lane.t <= arc["t"].max() + 60)
    )
    query = lane.subset(held)

    def prediction(a):
        def loss(d):
            r = paths.fold(arc["y"] - model(a["orbit"], arc["t"], a["phase"] + d))
            return np.log1p((r / 420) ** 2).sum() + (d / 3) ** 2

        d = minimize_scalar(loss, bounds=(-7.5, 7.5), method="bounded", options={"maxiter": 20}).x
        return model(a["orbit"], query.t, a["phase"] + d, horizon=True)

    tested = [arc, *alternatives]
    score, rows = paths.decode(query, np.asarray([prediction(a) for a in tested]), fixed=True)
    return dict(
        orbit=arc["orbit"],
        held_points=int((rows[0] >= 0).sum()),
        picked_score=float(score[0]),
        rival_scores=[float(s) for s in score[1:]],
        rival_count=len(alternatives),
    )


def checked_time(bank, lanes, pair_ids, arcs, levels, fit_value):
    x, phase_index, _, _ = fit_value
    xyz = paths.site(bank, x[:2])[0]
    options = []
    for a in arcs:
        lane_no, o = a["lane"], a["orbit"]
        held = paths.blocks(lanes[lane_no].t)[1]
        lane = lanes[lane_no].subset(held)
        sub = paths.slice_orbit(bank, slice(o, o + 1))
        rf, group = lane.key[2], lane.group
        pred = paths.orbit_geometry(
            sub, lane.t, a["phase"] + x[11 + phase_index[o]], xyz, rf, horizon=True
        )[0]
        pred += (
            levels[group]
            + x[2 + group]
            + x[6 + group] * (lane.t - bank.duration_s / 2)
            + x[10] * (rf / 1e9 - 11.5)
        )
        score, decoded = paths.decode(lane, pred[None], fixed=True)
        use = np.flatnonzero(decoded[0] >= 0)
        if len(use) >= 5:
            ranks = decoded[0, use]
            options.append(
                (
                    score[0],
                    a
                    | dict(
                        t=lane.t[use],
                        visit=lane.visit[use],
                        y=paths.fold(lane.y[use, ranks] - pred[use]),
                        pairs=pair_ids[lane_no][held][use, ranks],
                    ),
                )
            )
    occupied = set()
    disjoint = []
    for _, a in sorted(options, key=lambda item: -item[0]):
        slots = {(lanes[a["lane"]].key[0], int(v)) for v in a["visit"]}
        if not occupied & slots:
            occupied |= slots
            disjoint.append(a)
    checked = unique(disjoint, lanes)
    residuals = np.concatenate([a["y"] for a in checked]) if checked else np.array([])
    return dict(
        held_points=len(residuals),
        held_orbits=len({a["orbit"] for a in checked}),
        held_blocks=len({int(t // 15) for a in checked for t in a["t"]}),
        held_rms_hz=float(np.sqrt(np.mean(residuals**2))) if len(residuals) else None,
    )


def solve(capture, *, tile, misalign=False):
    start = perf_counter()
    raw_lanes, stats = paths.read_peaks(capture)
    fused, flags, pair_stats = paired.observations(capture, misalign)
    ids = corroborate(raw_lanes, fused, flags, pair_stats["calibration"], capture.duration_s)
    lanes = [
        replace(lane, marks=lane.marks + 0.4 * (key >= 0))
        for lane, key in zip(raw_lanes, ids, strict=True)
    ]
    bank, norads, sky = paths.orbital_bank(capture, tile["center"])
    options, search_count = [], 0
    for n, (lane, ids_for_lane) in enumerate(zip(lanes, ids, strict=True)):
        train = paths.blocks(lane.t)[0]
        arcs, searched = shortlist(bank, lane.subset(train), ids_for_lane[train], n)
        search_count += searched
        options.extend(arcs)
    selected, levels = paths.choose(lanes, options)
    before = sum(len(a["t"]) for a in selected)
    selected = unique(selected, lanes)
    count = sum(len(a["t"]) for a in selected)
    families = {a["orbit"] for a in selected}
    groups = {lanes[a["lane"]].group for a in selected}
    arms = {a: dict(latlon=None, forced_latlon=None) for a in paths.ARMS}
    reason = "insufficient_independent_arcs"
    if len(families) >= 4 and len(groups) >= 2:
        anchors = []
        for arc in sorted(selected, key=lambda a: -len(a["t"])):
            orbit = arc["orbit"]
            if any(a["orbit"] == orbit for a, _ in anchors):
                continue
            alternatives = sorted(
                (
                    p
                    for p in options
                    if p["lane"] == arc["lane"]
                    and p["orbit"] != orbit
                    and len(np.intersect1d(p["visit"], arc["visit"])) >= 5
                ),
                key=lambda a: -a["strength"],
            )
            rivals = {}
            for alternate in alternatives:
                rivals.setdefault(alternate["orbit"], alternate)
            anchors.append((arc, list(rivals.values())[:2]))
            if len(anchors) == 2:
                break
        reason = None
        half = float(tile.get("width_km", 25.0)) / 2
        for name in paths.ARMS:
            fitted = name == "fitted_c"
            solution = fit(bank, lanes, selected, levels, half, fitted)
            x, _, rms, radius = solution
            checked = checked_time(bank, raw_lanes, ids, selected, levels, solution)
            evidence, shifts = [], []
            for arc, alternatives in anchors:
                others = [a for a in selected if a["orbit"] != arc["orbit"]]
                group = lanes[arc["lane"]].group
                if not any(lanes[a["lane"]].group == group for a in others):
                    continue
                independent_levels = clock_levels(lanes, others)
                leave = fit(bank, lanes, others, independent_levels, half, fitted)
                shifts.append(float(np.linalg.norm(leave[0][:2] - x[:2])))
                check = test_identity(
                    bank,
                    raw_lanes[arc["lane"]],
                    arc,
                    alternatives,
                    leave,
                    independent_levels[group],
                )
                evidence.append(
                    check
                    | dict(
                        norad=norads[arc["orbit"]],
                        rival_norads=[norads[a["orbit"]] for a in alternatives],
                    )
                )
            informative = sum(
                e["held_points"] >= 5 and e["picked_score"] > max([0.0, *e["rival_scores"]])
                for e in evidence
            )
            defeats = sum(max([0.0, *e["rival_scores"]]) > e["picked_score"] + 3 for e in evidence)
            shift = max(shifts, default=None)
            arms[name].update(
                forced_latlon=paths.site(bank, x[:2])[1],
                rf_rms_hz=rms,
                c_hz_per_ghz=float(x[10]),
                radius_km=radius,
                orbit_checks=evidence,
                leave_orbit_max_shift_km=shift,
                independently_supported_orbits=informative,
                held_rival_wins=defeats,
                **checked,
            )
            if (
                checked["held_points"] < 25
                or checked["held_orbits"] < 3
                or checked["held_blocks"] < 2
            ):
                reason = reason or "insufficient_contiguous_held_path_support"
            elif (
                np.max(abs(x[:2])) > half - 0.75 or radius > 6 or (shift is not None and shift > 6)
            ):
                reason = reason or "weak_position_geometry"
            elif informative < 1 or defeats:
                reason = reason or "insufficient_leave_orbit_identity_support"
    if reason is None:
        for arm in arms.values():
            arm["latlon"] = arm["forced_latlon"]
    stats.update(
        sky,
        calibrated_bands=sum(v["supported"] for v in pair_stats["calibration"].values()),
        simultaneous_visits=pair_stats["simultaneous_same_rf_visits"],
        corroborated_candidates=sum(int((key >= 0).sum()) for key in ids),
        decoded_orbit_lane_phases=search_count,
        proposed_arcs=len(options),
        selected_paths=len(selected),
        selected_orbits=len(families),
        selected_points=count,
        coobserved_duplicates=before - count,
        paired_selected_points=sum(int((a["pairs"] >= 0).sum()) for a in selected),
        solve_elapsed_s=perf_counter() - start,
    )
    return dict(
        status="ok" if reason is None else "withheld",
        boundary=BOUNDARY,
        reason=reason,
        metrics=stats,
        arms=arms,
    )
