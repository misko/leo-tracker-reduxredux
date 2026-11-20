"""Forecast held native CFO with common receiver clocks and carried satellite levels."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid
from . import absolute_doppler, joint_pass, multi_session, peak_paths

ARMS = ("c0", "fitted_c")
METHODS = ("carried", "clock_only", "free_track", "identity_sham", "offer_center")
BOUNDARY = "Anonymous native GLRT and causal orbital states through grouped carrier forecasts"
RF = 11.5e9
SIGMA = 500.0
CAP = 16.0
MIN_OVERLAP_S = 3.0


@dataclass(frozen=True)
class Track:
    block: int
    path: int
    rf: float
    time: np.ndarray
    observed: np.ndarray
    orbit: np.ndarray
    phase: np.ndarray
    levels: np.ndarray
    losses: np.ndarray
    p: np.ndarray
    v: np.ndarray
    held_time: np.ndarray
    held_peaks: np.ndarray
    held_keep: np.ndarray
    held_p: np.ndarray
    held_v: np.ndarray


def unwrap(value):
    return value[..., :1] + peak_paths.fold(value - value[..., :1])


def states(bank, ids, time, phases):
    pairs = []
    for idx, phase in zip(ids, phases, strict=True):
        tile = peak_paths.slice_orbit(bank, slice(idx, idx + 1))
        p, v, _ = grid._interpolated_states(tile, time + phase)
        pairs.append(
            (
                peak_paths.rotate(p[0], phase * peak_paths.EARTH_ROTATION),
                peak_paths.rotate(v[0], phase * peak_paths.EARTH_ROTATION),
            )
        )
    return tuple(np.asarray(block) for block in zip(*pairs, strict=True))


def exact_project(p, v, site, rf):
    ray = p - site
    return -rf / grid.LIGHT_SPEED_KM_S * np.sum(ray * v, axis=-1) / np.linalg.norm(ray, axis=-1)


def proposed(row, bank, ids, xyz, enu, lanes):
    arc = joint_pass.shortlist(row, bank, ids, xyz, enu)
    if arc is None:
        return None
    f = exact_project(arc.p, arc.v, xyz, arc.rf)
    residual = unwrap(peak_paths.fold(arc.cfo - f))
    error, phase, drift = joint_pass.profile(
        residual,
        arc.phase,
        arc.time_s,
        len(arc.time_s),
        independent=True,
    )
    loss = np.mean((error / SIGMA) ** 2, axis=1) + (phase / 6) ** 2 / len(arc.time_s)
    use = np.argsort(loss, kind="stable")[:5]
    norad, phase = arc.norad[use], phase[use]
    index = [ids.index(sat) for sat in norad]
    p, v = states(bank, index, arc.time_s, phase)
    r = unwrap(peak_paths.fold(arc.cfo - exact_project(p, v, xyz, arc.rf)))
    levels = peak_paths.fold(r.mean(axis=1) - drift[use] * (arc.time_s.mean() - 150))
    time, peaks, keep = np.empty(0), np.empty((0, 4)), np.empty((0, 4), dtype=bool)
    if arc.block % 3 == 1:
        lane = next(a for a in lanes if a.group == arc.group and a.key[-1] == arc.rf)
        mask = (lane.t // 30 == arc.block) & (lane.t % 30 >= 20) & (lane.marks > 0.05).any(axis=1)
        offsets = np.flatnonzero(mask)
        take = np.rint(np.linspace(0, len(offsets) - 1, min(len(offsets), 12))).astype(int)
        offsets = offsets[take]
        time, peaks, keep = lane.t[offsets], lane.y[offsets], lane.marks[offsets] > 0.05
        if len(time) < 4:
            return None
    hp, hv = states(bank, index, time, phase)
    return Track(
        arc.block,
        arc.group,
        arc.rf,
        arc.time_s,
        arc.cfo,
        norad,
        phase,
        levels,
        loss[use],
        p,
        v,
        time,
        peaks,
        keep,
        hp,
        hv,
    )


def donor_assignments(tracks):
    donors, seeds = [], {}
    for path in sorted({row.path for row in tracks}):
        local = [row for row in tracks if row.path == path]
        options = [(a.orbit, a.phase, a.levels, a.losses) for a in local]
        seed, choices, losses = absolute_doppler.common_level(options)
        seeds[path] = seed
        donors.extend(
            (row, j)
            for row, j, loss in zip(local, choices, losses, strict=True)
            if loss < absolute_doppler.CEILING
        )
    return donors, seeds


def overlap_families(assigned):
    contexts = defaultdict(list)
    for track, owner in assigned:
        contexts[int(track.orbit[owner])].append(track)
    return sorted(
        sat
        for sat, tracks in contexts.items()
        if any(
            (a.path, a.rf) != (b.path, b.rf)
            and min(a.time[-1], b.time[-1]) - max(a.time[0], b.time[0]) >= MIN_OVERLAP_S
            for a, b in combinations(tracks, 2)
        )
    )


def columns(time, path, rf, sat, paths, satellites):
    f = np.asarray(rf) / RF
    paths = np.equal.outer(path, paths).astype(float)
    group = np.equal.outer(sat, satellites).astype(float) * f[:, None]
    return np.hstack((paths, paths * ((time - 150) / 150 * f)[:, None], group))


def data_rank(matrix):
    norms = np.linalg.norm(matrix, axis=0)
    singular = np.linalg.svd(matrix / np.maximum(norms, 1e-30), compute_uv=False)
    return int(np.sum(singular > 1e-9))


def calibration_gauge(path, rf, sat):
    """Audit the exact RF-linear null before constraining satellite levels."""
    intercepts = np.equal.outer(path, np.unique(path)).astype(float)
    grouped = np.equal.outer(sat, np.unique(sat)).astype(float) * (rf / RF)[:, None]
    target = rf / 1e9 - 11.5
    # Summing all fractional satellite columns and subtracting all path gauges gives c.
    reproduced = 11.5 * (grouped.sum(axis=1) - intercepts.sum(axis=1))
    combined = np.hstack((intercepts, grouped))
    return dict(
        c_norm=float(np.linalg.norm(target)),
        c_null_error=float(np.linalg.norm(target - reproduced)),
        unrestricted_rank=data_rank(combined),
        rank_with_c=data_rank(np.column_stack((combined, target))),
    )


def design_for(donors, seeds, families):
    paths = sorted({row.path for row, _ in donors})
    records = [(row.time, row.path, row.rf, row.orbit[j]) for row, j in donors]
    t = np.concatenate([r[0] for r in records])
    lengths = [len(r[0]) for r in records]
    path, rf, sat = (np.repeat([r[i] for r in records], lengths) for i in (1, 2, 3))
    seed = np.repeat([seeds[row.path] for row, _ in donors], lengths)
    weights = np.repeat(1 / np.sqrt(lengths), lengths)
    d = columns(t, path, rf, sat, paths, families)
    b = 2 * len(paths)
    audit = calibration_gauge(path, rf, sat)
    audit.update(
        clock_rank=data_rank(d[:, :b]),
        grouped_rank=data_rank(d),
        arcs=len(donors),
        paths=len(paths),
        overlapped_norads=len(families),
        cross_rf_norads=sum(
            len({row.rf for row, j in donors if row.orbit[j] == k}) > 1 for k in families
        ),
    )
    return paths, seed, weights, d, audit


def fit(residual, design, weights, prior):
    """Fixed two robust updates. Strong satellite shrinkage defines the reported gauge."""
    coef = np.zeros(design.shape[1])
    for _ in range(2):
        z = peak_paths.fold(residual - design @ coef)
        weight = weights / np.sqrt(np.hypot(1, z / SIGMA))
        delta = np.linalg.lstsq(
            np.vstack((design * weight[:, None], prior)),
            np.r_[z * weight, -prior @ coef],
            rcond=None,
        )[0]
        coef += delta
    z = peak_paths.fold(residual - design @ coef)
    return coef, float(np.sum(weights**2 * np.minimum(CAP, (z / SIGMA) ** 2)))


def target_prediction(row, xyz, paths, seeds, families, coef, mode):
    head = exact_project(row.p, row.v, xyz, row.rf)
    suffix = exact_project(row.held_p, row.held_v, xyz, row.rf)
    receiver = paths.index(row.path) if row.path in paths else None
    middle = (row.time - 150) / 150 * row.rf / RF
    future = (row.held_time - 150) / 150 * row.rf / RF
    if mode == "free_track":
        value = unwrap(peak_paths.fold(row.observed - head))
        x = row.time - row.time.mean()
        drift = np.clip((value @ x) / (x @ x), -180, 180)
        head += value.mean(axis=1)[:, None] + drift[:, None] * x
        suffix += value.mean(axis=1)[:, None] + drift[:, None] * (row.held_time - row.time.mean())
    elif receiver is None:
        return None
    else:
        levels = np.zeros(len(row.orbit))
        if mode in ("carried", "identity_sham"):
            if mode == "identity_sham" and len(families) < 2:
                return None
            values = coef[2 * len(paths) :]
            if mode == "identity_sham":
                values = np.roll(values, 1)
            lookup = dict(zip(families, values, strict=True))
            allowed = [i for i, sat in enumerate(row.orbit) if int(sat) in lookup]
            if not allowed:
                return None
            levels = np.array([lookup.get(int(sat), 0.0) for sat in row.orbit]) * row.rf / RF
        base = seeds[row.path] + coef[receiver] + levels[:, None]
        slope = coef[len(paths) + receiver]
        head += base + slope * middle
        suffix += base + slope * future
    loss = np.mean(np.minimum(CAP, (peak_paths.fold(row.observed - head) / SIGMA) ** 2), axis=1)
    if mode in ("carried", "identity_sham"):
        loss[~np.isin(row.orbit, families)] = np.inf
    order = np.argsort(loss, kind="stable")
    pick = order[0]
    # The suffix is never linked or used to select this first unknown arc owner.
    error = np.min(
        np.where(
            row.held_keep, np.abs(peak_paths.fold(row.held_peaks - suffix[pick, :, None])), np.inf
        ),
        axis=1,
    )
    return dict(
        orbit=int(row.orbit[pick]),
        head_loss=float(loss[pick]),
        head_gap=float(loss[order[1]] - loss[pick])
        if len(order) > 1 and np.isfinite(loss[order[1]])
        else None,
        held_rms_hz=float(np.sqrt(np.mean(error**2))),
        held_loss=float(np.mean(np.minimum(CAP, (error / SIGMA) ** 2))),
        held_points=len(error),
        block=row.block,
        path=row.path,
        rf_hz=row.rf,
    )


def measures(matches, count):
    present = [row for row in matches if row is not None]
    supported = [r for r in present if r["head_loss"] <= 4 and r["held_rms_hz"] <= 1000]
    paired = len(present)
    return dict(
        loss=float((sum(r["held_loss"] for r in present) + (count - paired) * CAP) / max(count, 1)),
        rms_hz=float(np.sqrt(np.mean([r["held_rms_hz"] ** 2 for r in present])))
        if present
        else None,
        predicted_tracks=paired,
        held_points=sum(r["held_points"] for r in present),
        supported_blocks=len({r["block"] for r in supported}),
        supported_orbits=len({r["orbit"] for r in supported}),
    )


def evaluate(capture, center):
    from types import SimpleNamespace

    # Held blocks contribute only their first 20 seconds to anonymous track construction.
    probes = [
        p
        for p in capture.probes
        if (
            (
                time := (p["valid_start_counter"] - capture.first_counter) / capture.sample_rate_hz
                + capture.probe_ms / 2000
            )
            // 30
            % 3
            != 1
            or time % 30 < 20
        )
    ]
    prefix = SimpleNamespace(**(vars(capture) | {"probes": probes}))
    arcs, stats = joint_pass.extract(prefix)
    lanes, _ = peak_paths.read_peaks(capture)
    bank, ids, _ = peak_paths.orbital_bank(capture, center)
    origin, enu = geodetic_to_ecef_km(*center, 0.0), ecef_to_enu_matrix(*center)
    tracks = [a for r in arcs if (a := proposed(r, bank, ids, origin, enu, lanes)) is not None]
    donors, seeds = donor_assignments([row for row in tracks if row.block % 3 != 1])
    held = [row for row in tracks if row.block % 3 == 1]
    if not donors:
        return dict(status="unavailable", reason="no_anonymous_donor_assignments", stats=stats)
    families = overlap_families(donors)
    paths, seed, weights, d, audit = design_for(donors, seeds, families)
    width = len(paths)
    q = np.diag(
        np.r_[[SIGMA / 100_000] * width, [SIGMA / 8000] * width, [SIGMA / 1200] * len(families)]
    )
    sites, offers = multi_session.design(center)
    profiles = {}
    for key, point in sites.items():
        xyz = geodetic_to_ecef_km(*point, 0)
        residuals = [
            row.observed - exact_project(row.p[j], row.v[j], xyz, row.rf) for row, j in donors
        ]
        y = peak_paths.fold(np.concatenate(residuals) - seed)
        fitted, carried_loss = fit(y, d, weights, q)
        clock, clock_loss = fit(y, d[:, : 2 * width], weights, q[: 2 * width, : 2 * width])
        free_loss = 0.0
        for (row, _), raw in zip(donors, residuals, strict=True):
            value = unwrap(peak_paths.fold(raw))
            x = row.time - row.time.mean()
            error = value - value.mean() - x * np.clip(value @ x / (x @ x), -180, 180)
            free_loss += float(np.mean(np.minimum(CAP, (error / SIGMA) ** 2)))
        train = [carried_loss, clock_loss, free_loss, carried_loss]
        modes = [
            [target_prediction(row, xyz, paths, seeds, families, coef, mode) for row in held]
            for mode, coef in zip(METHODS, (fitted, clock, clock, fitted), strict=False)
        ]
        profiles[key] = (train, modes)
    out = []
    for offer, region in offers.items():
        eligible = region["points"]
        for mode, label in enumerate(METHODS):
            j = mode if mode < 4 else 0
            preferred = (
                multi_session.OFFERS[offer]
                if mode == 4
                else min(eligible, key=lambda k: profiles[k][0][j])
            )
            train, modes = profiles[preferred]
            measured = measures(modes[j], len(held))
            sham = measures(modes[3], len(held))
            rivals = [
                measures(a[j], len(held))["loss"]
                for k, (_, a) in profiles.items()
                if np.linalg.norm(np.subtract(k, preferred)) >= 10
            ]
            lead = min(rivals) - measured["loss"]
            gain = sham["loss"] - measured["loss"]
            cross_rank = audit["grouped_rank"] - audit["clock_rank"]
            ready = (
                label == "carried"
                and cross_rank >= 2
                and measured["supported_blocks"] >= 2
                and measured["supported_orbits"] >= 2
                and lead >= 0.5
                and gain >= 0.5
            )
            reason = (
                None
                if ready
                else (
                    "insufficient_carried_forecast_support"
                    if label == "carried"
                    else "experimental_comparison"
                )
            )
            endpoint = dict(
                latlon=sites[preferred] if ready else None,
                forced_latlon=sites[preferred] if not ready else None,
                rf_rms_hz=measured["rms_hz"],
            )
            matched = [
                dict(target=i, carried=a, clock_only=b, free_track=c, identity_sham=s)
                for i, (a, b, c, s) in enumerate(zip(*modes, strict=True))
            ]
            out.append(
                dict(
                    offer=offer,
                    tile=dict(center=region["center"], width_km=25),
                    method=label,
                    result=dict(
                        status="ok" if ready else "withheld",
                        reason=reason,
                        boundary=BOUNDARY,
                        arms=dict(
                            c0=endpoint,
                            fitted_c=dict(
                                status="unavailable",
                                latlon=None,
                                reason="rf_linear_term_is_a_receiver_satellite_gauge",
                            ),
                        ),
                        metrics=dict(
                            position_attempted=True,
                            training_loss=train[j],
                            held=measured,
                            held_site_loss_lead=lead,
                            held_sham_loss_lead=gain,
                            selected_cell_km=preferred,
                            held_targets=len(held),
                            carried_rank_increment=cross_rank,
                            retained_modes=matched,
                        ),
                    ),
                )
            )
    return dict(
        status="ok",
        records=out,
        audit=audit,
        stats=stats,
        nominal_held_targets=len(held),
        group_counts=dict(Counter(row.path for row, _ in donors)),
    )
