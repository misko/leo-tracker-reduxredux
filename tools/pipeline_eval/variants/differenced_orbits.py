"""Fit causal orbit triplets to staggered, distinct-RF native measurements."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations, product

import numpy as np
from scipy.spatial import cKDTree

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid, tracker
from .folded_doppler import _offset
from .pass_hypotheses import field
from .peak_paths import orbital_bank

METHOD = "differenced_orbits"
BOUNDARY = "Anonymous native GLRT, causal orbit triplets and one offered square"
WIDTH = 8
WINDOWS = 5
TRAIN = 3
PAD = 350.0
GAP = 25.0
HELMERT = np.array([[1, -1, 0], [1, 1, -2]]) / np.sqrt([[2], [6]])
SEEDS = [(0, 0), (10, 0), (-10, 0), (0, 10), (0, -10)]
RIVALS = [(0, 0), *product((-12.5, 0, 12.5), repeat=2), (30, 0), (-30, 0), (0, 30), (0, -30)]


@dataclass(frozen=True)
class Stencil:
    time: np.ndarray
    cfo: np.ndarray
    weights: np.ndarray

    @property
    def rate(self):
        return float(self.weights @ self.cfo)


@dataclass(frozen=True)
class Group:
    block: int
    lanes: tuple
    arcs: tuple
    slots: tuple


class LaneLinks(tracker.Tracker):
    def __init__(self):
        super().__init__()
        self.completed = {}

    def retire(self, track):
        if track.confirmed:
            self.completed[track.ordinal] = track

    def tracks(self):
        live = {t.ordinal: t for layer in self.lanes.values() for t in layer if t.confirmed}
        return self.completed | live


def stencil(time, cfo, centre):
    if len(time) < 4 or not (time[0] <= centre - 1 and time[-1] >= centre + 1):
        return None
    if np.diff(time).max() > 3:
        return None
    u = (time - centre) / (WIDTH / 2)
    weights = np.linalg.pinv(np.stack((np.ones(len(u)), u, u**2), axis=1))[1] / (WIDTH / 2)
    if np.linalg.norm(weights) > 0.45:
        return None
    return Stencil(time, cfo, weights)


def moments(track, block, slots):
    points = np.asarray(track.samples, dtype=float)
    if track.samples[-1] != track.last:
        points = np.vstack((points, track.last))
    t, y = points.T
    out = {}
    for slot in slots:
        start = (block * WINDOWS + slot) * WIDTH
        take = (t >= start) & (t < start + WIDTH)
        if (result := stencil(t[take], y[take], start + WIDTH / 2)) is not None:
            out[slot] = result
    return out


def potential_copy(arcs, rfs):
    rates = np.array([[s.rate for s in arc] for arc in arcs]) * (12e9 / np.asarray(rfs))[:, None]
    return any(np.linalg.norm(a - b) / np.sqrt(len(a)) < 100 for a, b in combinations(rates, 2))


def prefix_groups(tracks, block):
    paths = defaultdict(list)
    for ordinal, track in tracks.items():
        rx, ch, _ = track.lane
        if pieces := moments(track, block, range(TRAIN)):
            paths[rx, ch > 4].append((ordinal, track.lane, pieces))
    best = {}
    excluded = defaultdict(int)
    for (_, band), options in paths.items():
        for rows in combinations(options, 3):
            ids, lanes, pieces = zip(*sorted(rows, key=lambda r: r[1][2]), strict=True)
            rfs = [lane[2] for lane in lanes]
            if len(set(rfs)) != 3:
                continue
            shared = tuple(sorted(set.intersection(*(set(p) for p in pieces))))
            if len(shared) < 2:
                continue
            stencils = tuple(tuple(p[i] for i in shared) for p in pieces)
            if potential_copy(stencils, rfs):
                excluded[band] += 1
                continue
            merit = len(shared), sum(len(s.time) for arc in stencils for s in arc)
            if band not in best or merit > best[band][0]:
                best[band] = (merit, ids, lanes, stencils, shared)
    return [v[1:] for _, v in sorted(best.items())], sum(excluded.values())


def support(capture):
    batches = defaultdict(list)
    exact_lanes = defaultdict(set)
    raw = {}
    for p in capture.probes:
        if p["probe_start_ms"] != 0:
            continue
        counter = p["valid_start_counter"]
        lane = p["receiver_id"], p["channel"], p["actual_rf_hz"]
        t = (counter - capture.first_counter) / capture.sample_rate_hz + capture.probe_ms / 2000
        exact_lanes[counter, lane[0], lane[1] > 4].add(lane[2])
        peaks = tracker.distinct_candidates(p["candidates"])
        batches[int(t // (WIDTH * WINDOWS))].append((t, lane, peaks))
        raw[t, lane] = p
    groups, rejected = [], 0
    for block, batch in sorted(batches.items()):
        links = LaneLinks()
        rows = sorted(batch)
        cutoff = block * WIDTH * WINDOWS + WIDTH * TRAIN
        split = np.searchsorted([r[0] for r in rows], cutoff)
        for t, lane, peaks in rows[:split]:
            links.ingest(t, lane, peaks)
        proposals, count = prefix_groups(links.tracks(), block)
        rejected += count
        for t, lane, peaks in rows[split:]:
            links.ingest(t, lane, peaks)
        available = links.tracks()
        for ids, lanes, stencils, slots in proposals:
            tail = tuple(moments(available[k], block, range(TRAIN, WINDOWS)) for k in ids)
            shared = tuple(sorted(set.intersection(*(set(p) for p in tail))))
            arcs = tuple(
                a + tuple(p[i] for i in shared) for a, p in zip(stencils, tail, strict=True)
            )
            groups.append(Group(block, lanes, arcs, slots + shared))
    figures = dict(
        native_zero_offset_visits=len(raw),
        exact_distinct_rf_path_windows=sum(len(rf) > 1 for rf in exact_lanes.values()),
        train_groups=len(groups),
        train_blocks=len({g.block for g in groups}),
        held_groups=sum(any(i >= TRAIN for i in g.slots) for g in groups),
        potential_copy_triples_rejected=rejected,
    )
    return groups, raw, figures


@dataclass(frozen=True)
class LaneModel:
    p: np.ndarray
    v: np.ndarray
    weights: np.ndarray
    rf: float

    def values(self, xyz, basis):
        cfo, jac = field(self.p, self.v, xyz, basis, self.rf)
        return cfo @ self.weights.T, np.einsum("st,ntd->nsd", self.weights, jac)


@dataclass(frozen=True)
class GroupModel:
    group: Group
    norad: np.ndarray
    lanes: tuple
    permuted_lanes: tuple
    observed: np.ndarray
    training: int
    visible_orbits: int
    evaluated: int


def ranked_triples(rates, observed, peers=8):
    """Retain a bounded set of all-anchor, two-edge candidates."""
    count = rates.shape[1]
    if count < 3:
        return np.zeros((0, 3), dtype=int), np.empty(0)
    depth = min(peers, count)
    peer = [
        cKDTree(rates[i]).query(rates[0] + observed[i] - observed[0], k=depth)[1] for i in (1, 2)
    ]
    a = np.broadcast_to(np.arange(count)[:, None, None], (count, depth, depth))
    b = np.broadcast_to(peer[0][:, :, None], a.shape)
    c = np.broadcast_to(peer[1][:, None, :], a.shape)
    distinct = (a != b) & (a != c) & (b != c)
    indices = np.stack((a[distinct], b[distinct], c[distinct]), axis=1)
    selected = np.stack([rates[i, indices[:, i]] for i in range(3)], axis=1)
    residual = HELMERT @ (observed - selected)
    rms = np.sqrt(np.mean(residual**2, axis=(1, 2)))
    return indices, rms


def compile_group(group, bank, ids, xyz, enu):
    observed = np.array([[s.rate for s in arc] for arc in group.arcs])
    n = sum(i < TRAIN for i in group.slots)
    visible = np.ones(len(ids), dtype=bool)
    lanes = []
    for lane, arc in zip(group.lanes, group.arcs, strict=True):
        p, v, _ = grid._interpolated_states(bank, np.concatenate([s.time for s in arc]))
        early = p[:, : sum(len(s.time) for s in arc[:n])] - xyz
        visible &= ((early @ enu[2]) > -0.02 * np.linalg.norm(early, axis=-1)).all(axis=1)
        weights = np.zeros((len(arc), p.shape[1]))
        cursor = 0
        for i, s in enumerate(arc):
            weights[i, cursor : cursor + len(s.time)] = s.weights
            cursor += len(s.time)
        lanes.append(LaneModel(p, v, weights, lane[2]))
    keep = np.flatnonzero(visible)
    if len(keep) < 3:
        return None
    compact = tuple(LaneModel(a.p[keep], a.v[keep], a.weights, a.rf) for a in lanes)
    vals, grad = (np.array(x) for x in zip(*(m.values(xyz, enu[:2]) for m in compact), strict=True))
    winners, evaluated = {}, 0
    for seed in SEEDS:
        predicted = vals[..., :n] + grad[..., :n, :] @ seed
        options, rms = ranked_triples(predicted, observed[:, :n])
        evaluated += len(rms)
        for i in np.argsort(rms, kind="stable")[:16]:
            key = tuple(options[i])
            winners[key] = min(winners.get(key, np.inf), rms[i])
    candidates = np.array(sorted(winners, key=winners.get)[:16])

    def sparse(choices):
        return tuple(
            LaneModel(m.p[choice], m.v[choice], m.weights, m.rf)
            for m, choice in zip(compact, choices.T, strict=True)
        )

    return GroupModel(
        group,
        np.asarray(ids)[keep[candidates]],
        sparse(candidates),
        sparse(candidates[:, [1, 2, 0]]),
        observed,
        n,
        len(keep),
        evaluated,
    )


def site_result(models, site, *, measure=False):
    xyz = geodetic_to_ecef_km(*site, 0)
    basis = ecef_to_enu_matrix(*site)[:2]
    details = []
    for model in models:
        values = [m.values(xyz, basis) for m in model.lanes]
        predicted, deriv = (np.stack(v, axis=1) for v in zip(*values, strict=True))
        r = HELMERT @ (model.observed - predicted)
        n = model.training
        early = np.sqrt(np.mean(r[:, :, :n] ** 2, axis=(1, 2)))
        rank = np.argsort(early, kind="stable")
        best, other = rank[:2]
        row = dict(train_rms=float(early[best]), train_gap=float(early[other] - early[best]))
        if n < model.observed.shape[1]:
            late = np.sqrt(np.mean(r[:, :, n:] ** 2, axis=(1, 2)))
            held_other = min((k for k in rank if k != best), key=lambda k: late[k])
            row.update(held_rms=float(late[best]), held_gap=float(late[held_other] - late[best]))
            if measure:
                placebo = [m.values(xyz, basis)[0][best, n:] for m in model.permuted_lanes]
                sham = HELMERT @ (model.observed[:, n:] - placebo)
                j = np.einsum("ab,btd->atd", HELMERT, deriv[best, :, n:])
                coupling = HELMERT @ (np.array([m.rf for m in model.lanes]) / 1e9)
                rf_free = np.array([-coupling[1], coupling[0]]) / np.linalg.norm(coupling)
                row.update(
                    sham_rms=float(np.sqrt(np.mean(sham**2))),
                    held_runner_up=model.norad[held_other].tolist(),
                    held_residual_hz_s=r[best, :, n:].T.tolist(),
                    held_predicted_hz_s=(HELMERT @ predicted[best, :, n:]).T.tolist(),
                    held_jacobian=j.transpose(1, 0, 2).reshape(-1, 2).tolist(),
                    rf_free_jacobian=(rf_free @ j.reshape(2, -1)).reshape(-1, 2).tolist(),
                )
        if measure:
            row.update(
                block=model.group.block,
                lanes=model.group.lanes,
                slots=model.group.slots,
                winning_norads=model.norad[best].tolist(),
                training_runner_up=model.norad[other].tolist(),
                visible_orbits=model.visible_orbits,
                candidate_triples=len(model.norad),
                observed_contrasts_hz_s=(HELMERT @ model.observed).T.tolist(),
                train_predicted_hz_s=(HELMERT @ predicted[best, :, :n]).T.tolist(),
            )
        details.append(row)
    train = float(np.mean([min(PAD, r["train_rms"]) for r in details]))
    test = float(np.mean([min(PAD, r.get("held_rms", PAD)) for r in details]))
    return train, test, details


def group_evidence(group, raw):
    ledger, c, cubic = [], 0.0, 0.0
    for slot, stencils in zip(group.slots, zip(*group.arcs, strict=True), strict=True):
        stencil_ledger = []
        third = []
        centre = (group.block * WINDOWS + slot + 0.5) * WIDTH
        for lane, st in zip(group.lanes, stencils, strict=True):
            samples = []
            for t, y, w in zip(st.time, st.cfo, st.weights, strict=True):
                probe = raw[t, lane]
                legal = [p for p in probe["candidates"] if p["passed_fractional_margin_gate"]]
                best = min(
                    legal, key=lambda p: abs(tracker.wrap(y - p["fractional_tracking_cfo_hz"]))
                )
                if abs(tracker.wrap(y - best["fractional_tracking_cfo_hz"])) > 1e-5:
                    raise ValueError("stencil CFO lacks its original native witness")
                samples.append(
                    [probe["valid_start_counter"], best["candidate_rank"], float(y), float(w)]
                )
            stencil_ledger.append(samples)
            c = max(c, abs(st.weights.sum() * lane[2] / 1e9))
            third.append(float(st.weights @ (st.time - centre) ** 3 / 6))
        cubic = max(cubic, np.ptp(third))
        ledger.append(stencil_ledger)
    return ledger, c, float(cubic)


def geometry(rows, key, rms):
    j = np.asarray([j for r in rows for j in r[key]]).reshape(-1, 2)
    singular = np.linalg.svd(j, compute_uv=False).tolist()
    radius = max(50, rms) / singular[1] if len(singular) == 2 and singular[1] > 1e-9 else None
    return singular, radius


def evaluate(capture, tile):
    if tile.get("width_km", 25) != 25:
        raise ValueError("one 25 km offered square is required")
    groups, raw, info = support(capture)
    center = tile["center"]
    forced, published = None, None
    reason = "insufficient_distinct_rf_stencils"
    if info["train_blocks"] >= 2:
        bank, ids, _ = orbital_bank(capture, center)
        xyz, enu = geodetic_to_ecef_km(*center, 0), ecef_to_enu_matrix(*center)
        models = [m for g in groups if (m := compile_group(g, bank, ids, xyz, enu)) is not None]
        info.update(
            regional_orbits=len(ids),
            modeled_groups=len(models),
            trial_triples=sum(m.evaluated for m in models),
            retained_triples=sum(len(m.norad) for m in models),
        )
        reason = "insufficient_causal_geometry"
        if len({m.group.block for m in models}) >= 2:
            forced, published, reason, measured = spatial_search(center, models, raw)
            info.update(measured)
    return dict(
        status="withheld" if reason else "ok",
        boundary=BOUNDARY,
        reason=reason,
        metrics=info | dict(position_attempted=forced is not None, c_identifiable=False),
        arms=dict(
            c0=dict(latlon=published, forced_latlon=forced),
            fitted_c=dict(
                latlon=None,
                forced_latlon=None,
                status="unavailable",
                reason="fixed_rf_calibration_annihilated_by_temporal_stencils",
            ),
        ),
    )


def spatial_search(center, models, raw):
    cache = {}

    def at(xy):
        key = tuple(xy)
        if key not in cache:
            cache[key] = site_result(models, _offset(center, *key))[:2]
        return cache[key]

    def training(xy):
        return at(xy)[0]

    xy = min(product(np.linspace(-12.5, 12.5, 11), repeat=2), key=training)
    for step in (0.5, 0.1):
        options = [
            tuple(np.clip(np.asarray(xy) + np.multiply(dx, step), -12.5, 12.5))
            for dx in product(range(-2, 3), repeat=2)
        ]
        xy = min(options, key=training)
    forced = list(_offset(center, *xy))
    train, held, rows = site_result(models, forced, measure=True)
    # Include the spatial runner-up among fixed rivals without changing the winner.
    coarse = [k for k in cache if np.linalg.norm(np.subtract(k, xy)) >= 8]
    rivals = [r for r in RIVALS if np.linalg.norm(np.subtract(r, xy)) >= 8]
    rivals += sorted(coarse, key=training)[:4]
    lead = min(at(r)[1] for r in rivals) - held
    qualified, orbits, blocks = [], set(), set()
    check = [r for r in rows if "held_rms" in r]
    for r in sorted(check, key=lambda r: r["held_rms"]):
        ids = set(r["winning_norads"])
        if (
            not ids & orbits
            and r["block"] not in blocks
            and min(r["train_gap"], r["held_gap"]) >= GAP
            and r["held_rms"] <= 130
            and r["sham_rms"] is not None
            and r["held_rms"] <= 0.8 * r["sham_rms"]
        ):
            orbits |= ids
            blocks.add(r["block"])
            qualified.append(r)
    c, cubic = 0.0, 0.0
    for model, row in zip(models, rows, strict=True):
        row["witnesses"], design, remainder = group_evidence(model.group, raw)
        c, cubic = max(c, design), max(cubic, remainder)

    def mean_rms(key):
        return float(np.sqrt(np.mean([r[key] ** 2 for r in check]))) if check else None

    rms = mean_rms("held_rms")
    sham = mean_rms("sham_rms")
    singular, radius = geometry(qualified, "held_jacobian", rms)
    rf_singular, rf_radius = geometry(qualified, "rf_free_jacobian", rms)
    centre_rows = site_result(models, center, measure=True)[2]
    centre_geometry = [r for r in centre_rows if "held_jacobian" in r]
    centre_singular, _ = geometry(centre_geometry, "held_jacobian", rms)
    publish = len(qualified) >= 2 and all(x is not None and x <= 12.5 for x in (radius, rf_radius))
    publish = publish and lead >= 15
    reason = None if publish else "orbit_or_region_unresolved"
    metrics = dict(
        train_cost_hz_s=train,
        held_cost_hz_s=held,
        held_lead_hz_s=lead,
        held_rms_hz_s=rms,
        held_permuted_rms_hz_s=sham,
        held_qualified_triples=len(qualified),
        held_independent_norads=sorted(orbits),
        held_rank_singular_hz_s_km=singular,
        held_rf_proportional_free_singular_hz_s_km=rf_singular,
        centre_conditional_singular_hz_s_km=centre_singular,
        held_radius_km=radius,
        held_rf_proportional_free_radius_km=rf_radius,
        max_calibration_design_hz_s_per_unit=c,
        max_cubic_clock_moment_difference_s2=cubic,
        forced_xy_km=list(xy),
        sites=len(cache),
        groups=rows,
    )
    return forced, forced if publish else None, reason, metrics
