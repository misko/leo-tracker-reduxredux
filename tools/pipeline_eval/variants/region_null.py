"""Contextual region evidence from causal Doppler and a matched track-time null."""

from collections import defaultdict
from dataclasses import dataclass
from math import sqrt

import numpy as np

from . import robust_em as lean

METHOD = "native_region_time_null"
BOUNDARY = "Complete native factors with independent satellite nomination and a track-time null"
COUNT = 19
MIN_ORBITS = 4
MARGIN = 1.0
SIGMA = sqrt(lean.WHITE_HZ**2 + lean.CORRELATED_HZ**2)
PAD_S = 180
SEED = 31206


@dataclass(frozen=True)
class Arc:
    rf: float
    midpoint: float
    relative_times: np.ndarray
    centered_hz: np.ndarray


def arcs(document):
    buckets = {}
    for track in document["tracks"]:
        t, hz = np.asarray(track["times"]), np.asarray(track["values"])
        if len(t) < 8 or not 24 <= np.ptp(t) <= 120:
            continue
        rf = track["rf_hz"]
        middle = float((t[0] + t[-1]) / 2)
        key = rf, int(middle // 30)
        if key not in buckets or np.ptp(t) > buckets[key][0]:
            choice = np.rint(np.linspace(0, len(t) - 1, 8)).astype(int)
            selected = hz[choice]
            buckets[key] = (
                np.ptp(t),
                Arc(rf, middle, t[choice] - middle, selected - selected.mean()),
            )
    bands = defaultdict(list)
    for _, value in sorted(buckets.values(), key=lambda v: (v[1].rf, -v[0], v[1].midpoint)):
        bands[value.rf].append(value)
    groups = [v for _, v in sorted(bands.items()) if len(v) >= 2]
    return [group[i] for i in range(5) for group in groups if i < len(group)][:24]


def schedules(selected):
    by_rf = defaultdict(list)
    for index, row in enumerate(selected):
        by_rf[row.rf].append(index)
    observed = tuple(range(len(selected)))
    plans = [observed]
    seen = {observed}
    rng = np.random.default_rng(SEED)
    for _ in range(256):
        plan = list(observed)
        for group in by_rf.values():
            for i, target in zip(group, rng.permutation(group), strict=True):
                plan[i] = int(target)
        outcome = tuple(plan)
        if outcome not in seen:
            plans.append(outcome)
            seen.add(outcome)
        if len(plans) == COUNT + 1:
            break
    return plans


def nodes(half):
    normals = np.array(((1, 0), (-1, 0), (0, 1), (0, -1)))
    return np.array(
        [
            (half / 12.5) * radius * (u + lateral * np.array((-u[1], u[0])))
            for shells in ((2, 7.5, 11), (14, 22, 31))
            for u in normals
            for radius in shells
            for lateral in (-0.5, 0, 0.5)
        ]
    )


def nominate(row, target, tile, sites):
    p, v, a = lean.grid._interpolated_states(tile, row.relative_times + target + PAD_S)
    pv, pa = np.sum(p * v, axis=-1), np.sum(p * a, axis=-1)
    speed2, radius2 = np.sum(v * v, axis=-1), np.sum(p * p, axis=-1)
    rate = row.rf / lean.grid.LIGHT_SPEED_KM_S
    winners, merits = [], []
    for start in range(0, len(sites), 8):
        current = sites[start : start + 8]
        up = current / np.linalg.norm(current, axis=1, keepdims=True)
        dist = np.sqrt(
            radius2
            + np.sum(current * current, axis=-1)[:, None, None]
            - 2 * np.einsum("gc,stc->gst", current, p)
        )
        radial = (pv - np.einsum("gc,stc->gst", current, v)) / dist
        velocity = -rate * radial
        accel = (
            -rate * ((pa - np.einsum("gc,stc->gst", current, a)) + speed2 - radial * radial) / dist
        )
        visible = (
            (np.einsum("gc,stc->gst", up, p) - np.sum(up * current, axis=1)[:, None, None])
            >= -0.035 * dist
        ).all(axis=-1)
        residual = (row.centered_hz - velocity + velocity.mean(axis=-1, keepdims=True)) / SIGMA
        phase_shape = (accel - accel.mean(axis=-1, keepdims=True)) / SIGMA
        prior = 1 / lean.PHASE_SD_S**2
        phase = np.clip(
            np.sum(residual * phase_shape, axis=-1)
            / (np.sum(phase_shape * phase_shape, axis=-1) + prior),
            -lean.PHASE_BOUND_S,
            lean.PHASE_BOUND_S,
        )
        cost = (
            np.sum((residual - phase[..., None] * phase_shape) ** 2, axis=-1)
            + prior * phase * phase
        ) / len(row.relative_times)
        cost[~visible] = np.inf
        chosen = np.argmin(cost, axis=1)
        minimal = cost[np.arange(len(chosen)), chosen]
        winners.extend(chosen)
        merits.extend(np.where(minimal <= 9, 1 / (1 + minimal), 0))
    return np.asarray(winners), np.asarray(merits)


def summarize(observed, counts, null, xy):
    inside, exterior = (
        indexes[np.argmax(observed[indexes])] for indexes in np.array_split(np.arange(len(xy)), 2)
    )
    maximum = max(observed[inside], observed[exterior])
    rank = (1 + sum(n >= maximum for n in null)) / (1 + len(null))
    delta = float(observed[inside] - observed[exterior])
    direction = "inside" if delta >= MARGIN else "outside" if delta <= -MARGIN else "ambiguous"
    best = inside if delta >= 0 else exterior
    state = direction if rank <= 0.05 and counts[best] >= MIN_ORBITS else "null_not_separated"
    return dict(
        state=state,
        null_rank=rank,
        max_null=float(max(null)),
        inside_minus_exterior=delta,
        inside=dict(
            xy_km=xy[inside].tolist(), score=float(observed[inside]), orbits=int(counts[inside])
        ),
        exterior=dict(
            xy_km=xy[exterior].tolist(),
            score=float(observed[exterior]),
            orbits=int(counts[exterior]),
        ),
        null_maxima=list(map(float, null)),
    )


def infer(document, offer, catalogue):
    selected = arcs(document)
    plans = schedules(selected)
    if len(selected) < MIN_ORBITS or len(plans) != COUNT + 1:
        return dict(state="insufficient", arcs=len(selected), permutations=len(plans) - 1)
    expanded = dict(
        document,
        anchor_utc_ns=document["anchor_utc_ns"] - PAD_S * 10**9,
        duration_s=document["duration_s"] + 2 * PAD_S,
    )
    sky = lean.grid.prepare_sky(expanded, catalogue)
    center = tuple(offer["center"])
    tile = lean.grid.make_tile(sky, center)
    n = len(tile.positions_km)
    if n == 0:
        return dict(
            state="insufficient", arcs=len(selected), permutations=0, reason="empty_causal_sky"
        )
    region = lean.Region(offer["id"], center, tile.ecef_center_km, tile.enu_frame)
    xy = nodes(offer["width_km"] / 2)
    sites = np.array([region.site(point)[0] for point in xy])
    scores = np.zeros((len(plans), len(xy), n))
    grid_id = np.arange(len(xy))
    for i, row in enumerate(selected):
        used = {p[i] for p in plans}
        table = {j: nominate(row, selected[j].midpoint, tile, sites) for j in used}
        for k, plan in enumerate(plans):
            winner, merit = table[plan[i]]
            np.maximum.at(scores[k], (grid_id, winner), merit)
    summed = scores.sum(axis=-1)
    metrics = summarize(summed[0], np.sum(scores[0] > 0, axis=-1), summed[1:].max(axis=1), xy)
    metrics.update(
        arcs=len(selected),
        permutations=COUNT,
        spatial_nodes=len(xy),
        padded_orbits=n,
        feature_nodes=8,
        same_gate_for_both_arms=True,
    )
    return metrics


def apply(initial, decision):
    result = dict(initial, boundary=BOUNDARY)
    if initial["status"] == "ok" and decision["state"] != "inside":
        result.update(
            status="withheld",
            reason=f"regional_time_null_{decision['state']}",
            arms={
                a: dict(point, latlon=None, region_id=None) for a, point in initial["arms"].items()
            },
        )
    return result
