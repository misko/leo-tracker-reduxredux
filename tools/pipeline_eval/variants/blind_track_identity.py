"""Name anonymous CFO arcs by predicting them with other arcs' receiver clock."""

from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter

import numpy as np

from leo.sky.frames import geodetic_to_ecef_km

from . import fixed_orbit_position as fixed
from . import peak_paths as native
from .track_link import Tracker

METHOD = "blind_track_identity"
BOUNDARY = "Anonymous native GLRT through bounded orbit hypotheses and standalone Doppler position"
PHASES = (-18, -12, -6, 0, 6, 12, 18)
DRIFTS = np.array([-80.0, -40.0, 0.0, 40.0, 80.0])
KEEP = 8
TAIL_SCALE = 480.0


@dataclass(frozen=True)
class Candidates:
    key: tuple
    t: np.ndarray
    observed: np.ndarray
    cut: int
    norads: np.ndarray
    phases: np.ndarray
    residual: np.ndarray
    level: np.ndarray
    drift: np.ndarray
    head_cost: np.ndarray

    @property
    def group(self):
        return 2 * self.key[0] + int(self.key[1] > 4)


def observations(capture, shuffle):
    lanes, counts = native.read_peaks(capture, shuffle)
    tracker = Tracker()
    records = sorted(
        (float(lane.t[j]), i, j)
        for i, lane in enumerate(lanes)
        for j in np.flatnonzero(fixed.training(lane.t))
    )
    for t, i, j in records:
        lane = lanes[i]
        distinct = []
        for f in lane.y[j, lane.marks[j] > 0.05]:
            if all(abs(fixed.fold(f - saved)) >= 160 for saved in distinct):
                distinct.append(float(f))
        tracker.ingest(t, lane.key, distinct)
    doc, _ = tracker.document()
    return lanes, doc["tracks"], counts


def shape_cost(residual):
    return np.log1p((residual / TAIL_SCALE) ** 2).mean(axis=-1)


def propose(bank, ids, arc):
    t = arc["times"]
    y = native.fold(arc["values"])
    rf = arc["rf_hz"]
    cut = np.searchsorted(t, t[0] + 0.62 * (t[-1] - t[0]))
    if cut < 9 or len(t) - cut < 5:
        return None
    sample = np.linspace(0, cut - 1, min(cut, 20)).astype(int)
    tt = t[sample]
    ref = float(tt.mean())
    x = tt - ref
    f = np.array(
        [native.orbit_geometry(bank, tt, p, bank.ecef_center_km, rf, horizon=True) for p in PHASES]
    )
    valid = np.isfinite(f).all(axis=-1)
    raw = native.fold(y[sample] - f)
    residual = raw[..., :1] + native.fold(raw - raw[..., :1])
    drift = np.clip(np.sum(residual * x, axis=-1) / (x @ x), -100, 100)
    level = native.fold(residual.mean(axis=-1) + drift * (bank.duration_s / 2 - ref))
    loss = shape_cost(residual - residual.mean(axis=-1)[..., None] - drift[..., None] * x)
    loss = np.where(valid, loss + (0.05 * (drift / 75) ** 2), np.inf)
    order = np.argsort(loss.min(axis=0), kind="stable")[:KEEP]
    order = order[loss[:, order].min(axis=0) < 2.35]
    if not len(order):
        return None
    ph, orbit, rest = [], [], []
    for j in order:
        for i in np.argsort(loss[:, j], kind="stable")[:3]:
            if loss[i, j] <= min(2.35, loss[:, j].min() + 0.9):
                ph.append(i)
                orbit.append(j)
                sub = native.slice_orbit(bank, slice(j, j + 1))
                modeled = native.orbit_geometry(
                    sub, t, PHASES[i], bank.ecef_center_km, rf, horizon=True
                )[0]
                rest.append(native.fold(y - modeled))
    return Candidates(
        (arc["receiver"], arc["channel"], rf),
        t,
        y,
        cut,
        np.asarray(ids)[orbit],
        np.asarray(PHASES)[ph],
        np.asarray(rest),
        level[ph, orbit],
        drift[ph, orbit],
        loss[ph, orbit],
    )


def clocks(arcs, duration):
    """Evaluate common receiver offsets and drifts with an arc factored out later."""
    n = 152
    level = np.tile(np.arange(n) * fixed.PERIOD_HZ / n, len(DRIFTS))
    rate = np.repeat(DRIFTS, n)
    vote, picked = [], []
    for arc in arcs:
        t = np.mean(arc.t[: arc.cut]) - duration / 2
        residual = fixed.fold(
            arc.level[None, :] - level[:, None] + t * (arc.drift[None, :] - rate[:, None])
        )
        support = np.exp(-arc.head_cost[None, :] / 0.8 - 0.5 * (residual / 1700) ** 2)
        i = support.argmax(axis=1)
        vote.append(support[np.arange(len(level)), i])
        picked.append(i)
    return level, rate, np.array(vote), np.array(picked)


def refine_clock(peers, duration, offset, rate):
    """Refine the grid seed on peer heads with capped per-arc influence."""
    times = np.concatenate([arc.t[: arc.cut] - duration / 2 for arc, _ in peers])
    error = np.concatenate([arc.residual[j, : arc.cut] for arc, j in peers])
    influence = np.concatenate([np.full(arc.cut, 1 / arc.cut) for arc, _ in peers])
    design = np.column_stack((np.ones(len(times)), times))
    for _ in range(3):
        residual = fixed.fold(error - offset - times * rate)
        w = np.sqrt(influence) / np.hypot(850.0, residual)
        step = np.linalg.lstsq(design * w[:, None], residual * w, rcond=None)[0]
        offset = float(fixed.fold(offset + np.clip(step[0], -2000, 2000)))
        rate = float(np.clip(rate + step[1], -100, 100))
    return offset, rate


def identify(arcs, duration, *, common):
    eligible = []
    for group in range(4):
        local = [arc for arc in arcs if arc.group == group]
        if not local or (common and len(local) < 3):
            continue
        if common:
            level, rate, vote, choices = clocks(local, duration)
        for j, arc in enumerate(local):
            d = arc.t[arc.cut :] - duration / 2
            if common:
                # The target and its alternative labels are absent from the clock likelihood.
                peers = np.arange(len(local)) != j
                candidates = np.argsort(-vote[peers].sum(axis=0), kind="stable")[:25]
                for k in candidates:
                    support = [
                        (local[i], choices[i, k])
                        for i in np.flatnonzero(peers & (vote[:, k] >= 0.2))
                    ]
                    if len({a.norads[choice] for a, choice in support}) >= 2:
                        break
                else:
                    continue
                offset, drift = refine_clock(support, duration, level[k], rate[k])
                residual = fixed.fold(arc.residual[:, arc.cut :] - offset - drift * d)
            else:
                residual = fixed.fold(
                    arc.residual[:, arc.cut :] - arc.level[:, None] - arc.drift[:, None] * d
                )
            rms = np.sqrt(np.mean(residual**2, axis=1))
            score = shape_cost(residual) + 0.45 * arc.head_cost
            score = np.where(np.isfinite(score), score, np.inf)
            winner = int(np.argmin(score))
            rival = score[arc.norads != arc.norads[winner]].min(initial=np.inf)
            if rms[winner] <= 2000 and score[winner] <= 2.8 and rival - score[winner] >= 0.18:
                eligible.append(
                    (
                        arc,
                        winner,
                        float(score[winner]),
                        None if not np.isfinite(rival) else float(rival),
                    )
                )
    by_orbit = defaultdict(list)
    for row in sorted(eligible, key=lambda r: r[2]):
        arc, j, _, _ = row
        previous = by_orbit[int(arc.norads[j])]
        if not previous or abs(arc.phases[j] - previous[0][0].phases[previous[0][1]]) <= 6:
            previous.append(row)
    return [row for family in by_orbit.values() for row in family]


def held_score(catalogue, lanes, offer, selected, fit_result, arm):
    f = fit_result["arms"][arm]
    pos = f["forced_latlon"]
    if pos is None:
        return dict(held_points=0, held_orbits=0, held_blocks=0, held_rms_hz=None)
    norads = fit_result["metrics"]["orbit_order"]
    tile, ordering = fixed.orbit_table(catalogue, set(norads), offer["center"])
    xyz = geodetic_to_ecef_km(*pos, 0)
    options = []
    for lane in lanes:
        families = {int(a.norads[j]) for a, j, _, _ in selected if a.key == lane.key} & set(norads)
        if not families:
            continue
        query = lane.subset(fixed.held(lane.t))
        times = query.t
        group = lane.group
        clock = f["group_offset_hz"][group] + f["group_drift_hz_s"][group] * (
            times - tile.duration_s / 2
        )
        clock += f["c_hz_per_ghz"] * (lane.key[2] / 1e9 - 11.5)
        for orbit in sorted(families):
            ff, _, _, horizon = fixed.geometry(
                tile,
                xyz,
                times,
                np.full(len(times), lane.key[2]),
                np.full(len(times), ordering[orbit]),
                np.full(len(times), f["phase_s"][norads.index(orbit)]),
            )
            pred = np.where(horizon >= -0.03, ff + clock, np.nan)
            value, chosen = native.decode(query, pred[None], fixed=True)
            ix = np.flatnonzero(chosen[0] >= 0)
            if len(ix) >= 5:
                options.append(
                    (
                        float(value[0]),
                        orbit,
                        {(lane.key[0], int(v)) for v in query.visit[ix]},
                        times[ix],
                        fixed.fold(query.y[ix, chosen[0, ix]] - pred[ix]),
                    )
                )
    occupied, orbits, blocks, residuals = set(), set(), set(), []
    for _, orbit, hits, t, residual in sorted(options, key=lambda item: -item[0]):
        if not occupied & hits:
            occupied |= hits
            orbits.add(orbit)
            blocks.update(int(u // 15) for u in t)
            residuals.extend(residual)
    return dict(
        held_points=len(residuals),
        held_orbits=len(orbits),
        held_blocks=len(blocks),
        held_rms_hz=fixed.rmshz(np.asarray(residuals)),
    )


def solve(capture, *, tile, mode="clock", shuffle=False):
    if mode not in ("clock", "local"):
        raise ValueError("unknown anonymous identity control")
    start = perf_counter()
    lanes, tracks, counts = observations(capture, shuffle)
    parsed = perf_counter()
    bank, ids, _ = native.orbital_bank(capture, tile["center"])
    catalogue = fixed.Catalogue(
        capture.catalog,
        capture.anchor_utc_ns,
        capture.cutoff_utc_ns,
        capture.catalog_timestamp_ns,
        capture.duration_s,
    )
    arcs = [candidate for t in tracks if (candidate := propose(bank, ids, t)) is not None]
    proposals = perf_counter()
    selected = identify(arcs, capture.duration_s, common=(mode == "clock"))
    occupied = set()
    factors = []
    for a, j, _, _ in sorted(selected, key=lambda item: item[2]):
        for t, y in zip(a.t, a.observed, strict=True):
            key = a.key[0], float(t)
            if key not in occupied:
                occupied.add(key)
                factors.append(
                    fixed.Factor(float(t), a.key[2], float(y), int(a.norads[j]), a.group)
                )
    named = perf_counter()
    result, _ = fixed.solve(factors, catalogue, tile)
    checked = perf_counter()
    reason = result["reason"]
    if reason == "fixed_identity_diagnostic":
        reason = None
        for arm, f in result["arms"].items():
            f.update(held_score(catalogue, lanes, tile, selected, result, arm))
            xy = bank.enu_frame[:2] @ (
                geodetic_to_ecef_km(*f["forced_latlon"], 0) - bank.ecef_center_km
            )
            if f["held_points"] < 25 or f["held_orbits"] < 3 or f["held_blocks"] < 2:
                reason = reason or "insufficient_held_raw_peaks"
            elif (
                f["local_radius_km"] > 6
                or np.max(abs(xy)) >= float(tile.get("width_km", 25)) / 2 - 0.75
            ):
                reason = reason or "weak_geometry_or_tile_edge"
    if reason is None:
        for f in result["arms"].values():
            f["latlon"] = f["forced_latlon"]
    result.update(status="withheld" if reason else "ok", reason=reason, boundary=BOUNDARY)
    result["metrics"].update(
        counts,
        anonymous_arcs=len(tracks),
        proposed_arcs=len(arcs),
        regional_orbits=len(ids),
        proposed_orbit_phases=sum(len(a.norads) for a in arcs),
        selected_arcs=len(selected),
        selected_orbits=len({int(a.norads[j]) for a, j, _, _ in selected}),
        link_s=parsed - start,
        proposal_s=proposals - parsed,
        identity_s=named - proposals,
        standalone_s=checked - named,
        validation_s=perf_counter() - checked,
    )
    trace = [
        dict(
            receiver=a.key[0],
            channel=a.key[1],
            rf_hz=a.key[2],
            time_min_s=float(a.t[0]),
            time_max_s=float(a.t[-1]),
            norad=int(a.norads[j]),
            phase_s=int(a.phases[j]),
            peaks=len(a.t),
            internal_tail_cost=cost,
            nearest_rival_cost=runner,
        )
        for a, j, cost, runner in selected
    ]
    return result, trace
