"""Freeze early causal orbit and receiver levels, then predict raw held native peaks."""

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from itertools import product
from types import SimpleNamespace

import numpy as np
from scipy.spatial import cKDTree

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid
from ..scoring import distance_km
from . import orbit_proposals as inverse
from . import peak_paths as native

forward = inverse.forward
METHOD = "orbit_continuity"
BOUNDARY = "Early anonymous inverse geometry and immutable causal orbit predictions on later GLRT"
LEAD = 0.03
GATE_HZ = 900


@dataclass(frozen=True)
class Link:
    orbit: int
    receiver: int
    group: int
    rf_hz: float
    stop_s: float
    intercept_hz: float
    shape_loss: float


def early_profiles(rows, states):
    paths = defaultdict(list)
    for b, g, t, f, rf in rows:
        if (profile := forward.features(t, f * forward.REFERENCE / rf)) is not None:
            paths[g].append((b, t, f, rf, profile))
    result = []
    for g, entries in paths.items():
        if len({r[0] for r in entries}) < 2:
            continue
        for b, t, f, rf, (q, phi, sigma) in sorted(
            entries, key=lambda r: -(len(r[1]) * np.ptp(r[1]))
        )[:5]:
            p, v, _ = grid._interpolated_states(states, t)
            mid = p[:, len(t) // 2]
            radius = np.linalg.norm(mid, axis=1)
            tree = cKDTree(mid / radius[:, None])
            horizon = np.sqrt(max(0.0, 2 * (1 - 6350 / radius.max()))) + 0.015
            result.append(forward.Profile(b, g, t, f, rf, q, phi, sigma, p, v, tree, horizon))
    return result


def winner_links(spectra, profiles, drift, reference):
    linked = {}
    for a, (ids, f, delta) in zip(profiles, spectra, strict=True):
        if not len(ids):
            continue
        loss = forward.cost(delta, a.noise, drift[[a.group]], False)[0]
        j = int(loss.argmin())
        gap = np.partition(loss, 1)[1] - loss[j] if len(loss) > 1 else np.inf
        if loss[j] > 4 or gap < 0.35:
            continue
        observed = native.fold(
            a.f - (f[j] + drift[a.group] * (a.t - reference)) * (a.rf / forward.REFERENCE)
        )
        unwrapped = observed[0] + native.fold(observed - observed[0])
        offset = np.median(unwrapped)
        if np.mean(np.abs(unwrapped - offset) <= 650) < 0.75:
            continue
        k = int(ids[j]), a.group // 2, a.rf
        link = Link(
            k[0], k[1], a.group, a.rf, float(a.t[-1]), float(native.fold(offset)), float(loss[j])
        )
        if k not in linked or link.stop_s > linked[k].stop_s:
            linked[k] = link
    return sorted(linked.values(), key=lambda link: link.shape_loss)[:12]


def geometry(profiles, centers):
    cached, work = {}, 0

    def fit(point):
        nonlocal work
        p = tuple(map(float, np.round(point, 8)))
        if p not in cached:
            x, up = geodetic_to_ecef_km(*p, 0), ecef_to_enu_matrix(*p)[2]
            s = [forward.spectrum(a, x, up) for a in profiles]
            work += sum(len(z[0]) for z in s)
            cached[p] = forward.clock_profile(s, profiles, False)
        return p

    def merit(p):
        return cached[p][0], p

    ordered = sorted(map(fit, centers), key=merit)
    ranked = ordered[:8]
    for step in (80, 32, 12):
        ranked = [
            min(
                (
                    fit(forward._offset(p, step * x, step * y))
                    for x, y in product((-1, 0, 1), repeat=2)
                ),
                key=merit,
            )
            for p in ranked
        ]
    best = min(ranked, key=merit)
    wider = [p for p in ordered if distance_km(p, best) >= 500][:4]
    local = [
        fit(forward._offset(best, 25 * np.cos(t), 25 * np.sin(t))) for t in np.arange(8) * np.pi / 4
    ]
    rivals = sorted({p for p in ranked if distance_km(p, best) >= 25} | set(wider) | set(local))
    return best, rivals, cached, work


def coherent(t, error):
    hits = np.flatnonzero(error <= GATE_HZ)
    groups = np.split(hits, np.flatnonzero(np.diff(t[hits]) > 3.5) + 1)
    support = [g for g in groups if len(g) >= 5 and t[g[-1]] - t[g[0]] >= 5.0]
    return np.concatenate(support) if support else np.empty(0, dtype=int)


def held_lanes(capture, late, is_null):
    lanes, _ = native.read_peaks(capture)
    filtered = defaultdict(list)
    for a in lanes:
        a = a.subset(a.t >= late)
        if is_null and len(a.t) > 1:
            shift = max(1, len(a.t) // 3)
            a = replace(a, y=np.roll(a.y, shift, axis=0), marks=np.roll(a.marks, shift, axis=0))
        filtered[a.key[0], a.key[2]].append(a)
    return filtered


def forecast(lanes, states, point, links, drift, reference):
    xyz, up = geodetic_to_ecef_km(*point, 0), ecef_to_enu_matrix(*point)[2]
    eligible, mature = set(), set()
    coincident = [dict() for _ in range(3)]
    for link in links:
        for lane in lanes.get((link.receiver, link.rf_hz), ()):
            if int(lane.key[1] > 4) != link.group % 2:
                continue
            use = (lane.t >= link.stop_s + 6) & (lane.t <= link.stop_s + 210)
            if not use.any():
                continue
            c = lane.subset(use)
            one = native.slice_orbit(states, slice(link.orbit, link.orbit + 1))
            p, v, _ = grid._interpolated_states(one, c.t)
            rel = p[0] - xyz
            distance = np.linalg.norm(rel, axis=1)
            visible = rel @ up > 0.01 * distance
            if not visible.any():
                continue
            c = c.subset(visible)
            mature.add(link.orbit)
            eligible.update((c.key, int(i)) for i in c.visit)
            rate = np.sum(rel[visible] * v[0, visible], axis=1) / distance[visible]
            prediction = (
                link.intercept_hz
                - rate * link.rf_hz / grid.LIGHT_SPEED_KM_S
                + drift[link.group] * (c.t - reference) * link.rf_hz / forward.REFERENCE
            )
            for delta, records in zip((0, -12000, 12000), coincident, strict=True):
                residual = np.abs(native.fold(c.y - prediction[:, None] - delta))
                error = np.where(c.marks > 0.05, residual, np.inf).min(axis=1)
                for i in coherent(c.t, error):
                    key = c.key, int(c.visit[i])
                    row = float(error[i]), int(c.t[i] // 30), link.orbit
                    records[key] = min(records.get(key, row), row)
    had, *shadows = coincident
    n, null = len(eligible), max(map(len, shadows))
    counts = Counter(orbit for _, _, orbit in had.values())
    return dict(
        held_visit_opportunities=n,
        held_eligible_orbits=len(mature),
        held_coherent_hits=len(had),
        held_placebo_hits=null,
        held_orbits=sum(v >= 5 for v in counts.values()),
        held_blocks=len({b for _, b, _ in had.values()}),
        held_strength=(len(had) - null) / max(1, n),
        held_cfo_rms_hz=float(np.sqrt(np.mean([e**2 for e, _, _ in had.values()])))
        if had
        else None,
    )


def solve(capture, *, is_null=False):
    late = 0.65 * capture.duration_s
    reference = capture.duration_s / 2
    head = [
        r
        for r in capture.probes
        if (r["valid_start_counter"] - capture.first_counter) / capture.sample_rate_hz
        + capture.probe_ms / 2000
        < late
    ]
    rows, counts = forward.extract(SimpleNamespace(**(vars(capture) | {"probes": head})))
    states, ids, _ = forward.bank(capture)
    early = early_profiles(rows, states) if len(ids) else []
    clouds = [(a.block, inverse.cloud(a, states)) for a in early]
    centers, count = inverse.nominate(clouds)
    m = dict(
        counts,
        train_profiles=len(early),
        candidate_orbits=len(ids),
        site_proposals=len(centers),
        inverse_points=sum(len(p) for _, p in clouds),
        proposal_blocks=count,
        time_shuffle=is_null,
        position_attempted=bool(centers),
        c_projected_column_norm=0.0,
    )
    if not centers:
        return forward.result(
            m | {"terminal_position_decision": True}, "no_independent_early_proposal"
        ) | {"boundary": BOUNDARY}
    best, rivals, early_fit, work = geometry(early, centers)
    hypotheses = {}
    for p in (best, *rivals):
        xyz, up = geodetic_to_ecef_km(*p, 0), ecef_to_enu_matrix(*p)[2]
        spectra = [forward.spectrum(a, xyz, up) for a in early]
        hypotheses[p] = winner_links(spectra, early, early_fit[p][1], reference)
        work += sum(len(z[0]) for z in spectra)
    lanes = held_lanes(capture, late, is_null)
    results = {
        p: forecast(lanes, states, p, a, early_fit[p][1], reference) for p, a in hypotheses.items()
    }
    v = results[best]
    rival = max(rivals, key=lambda p: results[p]["held_strength"])
    lead = v["held_strength"] - results[rival]["held_strength"]
    accepted = (
        v["held_visit_opportunities"] >= 40
        and v["held_orbits"] >= 2
        and v["held_blocks"] >= 3
        and v["held_coherent_hits"] - v["held_placebo_hits"] >= 8
        and lead >= LEAD
    )
    m.update(
        v,
        training_loss=early_fit[best][0],
        training_comparisons=work,
        world_sites=len(early_fit),
        early_links=len(hypotheses[best]),
        early_orbit_ids=sorted({int(ids[h.orbit]) for h in hypotheses[best]}),
        held_lead=lead,
        rival_distance_km=distance_km(best, rival),
        rival_held=results[rival],
        rivals=len(rivals),
    )
    return forward.result(
        m,
        None if accepted else "no_independent_held_orbit_continuity",
        list(best) if early_fit[best][0] < forward.CAP else None,
    ) | {"boundary": BOUNDARY}
