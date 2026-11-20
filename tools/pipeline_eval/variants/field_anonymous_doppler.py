"""Blind position from anonymous measured beacon arcs sharing one CFO drift."""

from dataclasses import dataclass
from itertools import product
from time import perf_counter, process_time

import numpy as np
from scipy.spatial import cKDTree
from sgp4.api import SatrecArray

from leo.sky.frames import (
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets

RF_HZ = 11_325_000_000
LIGHT_KM_S = 299_792.458
SAMPLES = 12
EARLY = 8
BIN_HZ = 2e6 / 28000
DRIFTS_HZ_S = np.array([0.0, -2.0, 2.0, -6.0, 6.0, -20.0, 20.0])
LOSS_CAP = 900.0**2
SUPPORT_LIMIT = 450.0**2
END_MARGIN_KM = 1.0
TILE_KM = 12.5
BOUNDARY = "Measured anonymous beacon Doppler and causal TLE to held position decision"


@dataclass(frozen=True)
class Arc:
    times: np.ndarray
    frequency: np.ndarray
    p: np.ndarray
    v: np.ndarray
    ids: np.ndarray
    sky: cKDTree
    horizon: float


def eligible_catalogue(observation, text):
    snapshot = observation["catalog_timestamp_ns"]
    cutoff = observation["cutoff_utc_ns"]
    if not snapshot <= cutoff <= observation["anchor_utc_ns"]:
        raise ValueError("field observation lacks a causal catalogue clock")
    parsed = parse_element_sets(text)
    by_id = {}
    for sat, epoch in zip(parsed.satellites, parsed.element_epoch_utc_ns(), strict=True):
        if snapshot - 48 * 3600 * 10**9 <= epoch <= snapshot:
            old = by_id.get(sat.satnum)
            if old is None or old[0] < epoch:
                by_id[sat.satnum] = (epoch, sat)
    return tuple(by_id[i][1] for i in sorted(by_id))


def prepare(observation, catalogue, *, shifted=False):
    sats = eligible_catalogue(observation, catalogue)
    if not sats:
        raise ValueError("no available causal orbits")
    orbit = SatrecArray(sats)
    ids = np.array([s.satnum for s in sats])
    duration = observation["duration_s"]
    arcs = []
    for record in observation["arcs"]:
        t, f = (np.asarray(record[k], dtype=float) for k in ("times", "values"))
        if (
            t.shape != (SAMPLES,)
            or f.shape != t.shape
            or not np.isfinite([t, f]).all()
            or np.any(np.diff(t) <= 0)
            or t[0] < 0
            or t[-1] > duration
        ):
            raise ValueError("invalid anonymous Doppler arc")
        if shifted:
            shift = duration / 4
            # Move the whole pass, preserving precise within-pass differences.
            t = t + (shift if t[-1] + shift <= duration else -shift)
            if t[0] < 0 or t[-1] > duration:
                raise ValueError("arc too long for the time control")
        jd, frac = julian_day_from_utc_ns(
            observation["anchor_utc_ns"] + np.rint(t * 1e9).astype(np.int64)
        )
        error, p, v = orbit.sgp4(jd, frac)
        radius = np.linalg.norm(p[:, EARLY // 2], axis=1)
        valid = (
            (error == 0).all(axis=1)
            & np.isfinite(p).all(axis=(1, 2))
            & np.isfinite(v).all(axis=(1, 2))
            & (radius >= 6500)
            & (radius <= 7350)
        )
        p, v = teme_to_ecef(p[valid], v[valid], greenwich_mean_sidereal_time_rad(jd, frac))
        r = radius[valid]
        sky = cKDTree(p[:, EARLY // 2] / r[:, None])
        horizon = np.sqrt(2 - 2 * 6330 / r.max(initial=6500))
        arcs.append(Arc(t, f, p, v, ids[valid], sky, horizon))
    return arcs, len(sats)


def differences(observed, modeled, times, drift):
    """Remove the early unknown arc level and forecast late with a common drift."""
    residual = observed - modeled - drift * (times - np.mean(times[:EARLY]))
    return residual - residual[..., :EARLY].mean(axis=-1, keepdims=True)


def score_arc(arc, xyz, up, drifts):
    count = len(xyz)
    template = (len(drifts), count)
    early, late = np.full(template, np.inf), np.full(template, np.inf)
    ids = np.full(template, -1)
    matches = arc.sky.query_ball_point(up, arc.horizon, return_sorted=True)
    lengths = list(map(len, matches))
    if not sum(lengths):
        return early, late, ids
    site = np.repeat(np.arange(count), lengths)
    sat = np.concatenate(matches).astype(int, copy=False)
    los = arc.p[sat] - xyz[site, None]
    vis = np.einsum("tsi,ti->ts", los, up[site]) >= 0
    keep = vis[:, :EARLY].all(axis=1)
    site, sat, los, vis = site[keep], sat[keep], los[keep], vis[keep]
    if not len(site):
        return early, late, ids
    estimated = (
        -RF_HZ
        / LIGHT_KM_S
        * np.einsum("tsi,tsi->ts", los, arc.v[sat])
        / np.linalg.norm(los, axis=-1)
    )
    indices = np.arange(len(site))
    for i, drift in enumerate(drifts):
        delta = differences(arc.frequency, estimated, arc.times, drift)
        cost = np.mean(delta[:, :EARLY] ** 2, axis=1)
        np.minimum.at(early[i], site, cost)
        best = cost == early[i, site]
        chosen = np.full(count, len(site))
        np.minimum.at(chosen, site[best], indices[best])
        valid = chosen != len(site)
        picked = chosen[valid]
        losses = np.mean(delta[picked, EARLY:] ** 2, axis=1)
        late[i, valid] = np.where(vis[picked, EARLY:].all(axis=1), losses, np.inf)
        ids[i, valid] = arc.ids[sat[picked]]
    return early, late, ids


def geometry(points):
    xyz = geodetic_to_ecef_km(points[:, 0], points[:, 1], 0.0).T
    lat, lon = np.deg2rad(points).T
    up = np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))
    return xyz, up


def evaluate(arcs, points, labels, drifts):
    rows = []
    for start in range(0, len(points), 48):
        stop = start + 48
        group = points[start:stop]
        xyz, up = geometry(group)
        trains, held, ids = map(
            np.stack,
            zip(
                *(score_arc(arc, xyz, up, drifts) for arc in arcs),
                strict=True,
            ),
        )
        # Profile one common drift after integrating the losses of the individual arcs.
        loss = np.minimum(trains, LOSS_CAP).mean(axis=0)
        for j, i in enumerate(np.argmin(loss, axis=0)):
            if loss[i, j] == LOSS_CAP:
                continue
            a, b = trains[:, i, j], held[:, i, j]
            keep = (a <= SUPPORT_LIMIT) & (b <= SUPPORT_LIMIT)
            rows.append(
                dict(
                    point=group[j],
                    label=labels[start + j],
                    xyz=xyz[j],
                    index=start + j,
                    early=float(loss[i, j]),
                    held=float(np.minimum(b, LOSS_CAP).mean()),
                    supported=np.flatnonzero(keep),
                    ids=ids[:, i, j][keep].tolist(),
                    held_supported_rms_hz=float(np.sqrt(b[keep].mean())) if keep.any() else None,
                    drift=float(drifts[i]),
                )
            )
    return rows


def world_lattice():
    """Fixed approximately equal spacing and no station-conditioned prior."""
    out = []
    for lat in np.arange(-85.0, 86.0, 10.0):
        n = max(3, round(36 * np.cos(np.deg2rad(lat))))
        out.extend((lat, -180 + 360 * j / n) for j in range(n))
    return np.array(out)


def offset(center, xy):
    east, north = xy.T / 6371.0
    lat, lon = np.deg2rad(center)
    d = np.hypot(east, north)
    angle = np.arctan2(east, north)
    lat2 = np.arcsin(np.sin(lat) * np.cos(d) + np.cos(lat) * np.sin(d) * np.cos(angle))
    lon2 = lon + np.arctan2(
        np.sin(angle) * np.sin(d) * np.cos(lat), np.cos(d) - np.sin(lat) * np.sin(lat2)
    )
    return np.column_stack((np.rad2deg(lat2), (np.rad2deg(lon2) + 180) % 360 - 180))


def distance(a, b):
    return np.linalg.norm(a["xyz"] - b["xyz"])


def global_search(arcs):
    points = world_lattice()
    rows = evaluate(arcs, points, [None] * len(points), DRIFTS_HZ_S)
    branches = []
    for row in sorted(rows, key=lambda row: row["early"]):
        if all(distance(row, picked) >= 900 for picked in branches):
            branches.append(row)
        if len(branches) == 8:
            break
    xy = np.array(list(product(range(-2, 3), repeat=2)))
    candidates = list(rows)
    for branch in branches:
        for step in (275, 95, 30, 10, 2.5):
            points = offset(branch["point"], xy * step)
            nearby = evaluate(arcs, points, [None] * len(xy), DRIFTS_HZ_S)
            candidates.extend(nearby)
            branch = min(nearby + [branch], key=lambda row: row["early"])
    return candidates, None


def offered_search(arcs, regions):
    rows = []
    edge = np.array([-12.5, -10, -5, 0, 5, 10, 12.5])
    square = np.array(list(product(edge, repeat=2)))
    stencil = np.array(list(product([-1.0, 0.0, 1.0], repeat=2)))
    for i, center in enumerate(regions):
        trial_xy = square
        best = None
        for step in (2.0, 0.5, None):
            nearby = evaluate(arcs, offset(center, trial_xy), [i] * len(trial_xy), DRIFTS_HZ_S)
            for item in nearby:
                item["xy"] = trial_xy[item["index"]]
                item["edge_km"] = float(TILE_KM - np.max(abs(item["xy"])))
            rows.extend(nearby)
            best = min(
                nearby if best is None else nearby + [best],
                key=lambda row: row["early"],
                default=None,
            )
            if step is None or best is None:
                break
            trial_xy = best["xy"] + step * stencil
            trial_xy = trial_xy[(abs(trial_xy) <= TILE_KM).all(axis=1)]
    return rows, regions


def summarize(rows, arcs, regions, null=None):
    metrics = dict(c_gauge="per-arc carrier level", tested_points=len(rows), usable_arcs=len(arcs))
    reason, latlon = "no_eligible_geometry", None
    if rows:
        best = min(rows, key=lambda row: row["early"])
        latlon = best["point"].tolist()
        rivals = [row for row in rows if distance(row, best) >= 5]
        rival = min(rivals, key=lambda row: row["held"], default=None)
        other = (
            [row for row in rows if row["label"] != best["label"]]
            if regions
            else [row for row in rows if distance(row, best) >= 25]
        )
        regional = min(other, key=lambda row: row["held"], default=None)
        spatial = None if rival is None else rival["held"] - best["held"]
        broad = None if regional is None else regional["held"] - best["held"]
        null_lead = None if null is None else null - best["held"]
        windows = sorted((arcs[i].times[0], arcs[i].times[-1]) for i in best["supported"])
        separated = any(hi + 5 <= windows[-1][0] for _, hi in windows)
        metrics.update(
            early_capped_rms_hz=float(np.sqrt(best["early"])),
            held_capped_rms_hz=float(np.sqrt(best["held"])),
            supported_held_rms_hz=best["held_supported_rms_hz"],
            held_ids=best["ids"],
            shared_drift_hz_per_s=best["drift"],
            best_region=best["label"],
            spatial_margin_hz2=spatial,
            region_margin_hz2=broad,
            null_margin_hz2=null_lead,
            spatial_rival_latlon=None if rival is None else rival["point"].tolist(),
            regional_rival_latlon=None if regional is None else regional["point"].tolist(),
            separated_pass_windows=separated,
            edge_km=best.get("edge_km"),
        )
        if len(set(best["ids"])) < 3 or not separated:
            reason = "insufficient_independent_held_arcs"
        elif spatial is None or spatial <= BIN_HZ**2:
            reason = "weak_held_spatial_margin"
        elif broad is None or broad <= BIN_HZ**2:
            reason = "weak_held_region_margin"
        elif regions and (best.get("edge_km", 0) < END_MARGIN_KM):
            reason = "offered_tile_edge"
        elif null_lead is None or null_lead <= BIN_HZ**2:
            reason = "weak_held_time_control_margin"
        else:
            reason = None
    arm = dict(
        latlon=latlon if reason is None else None,
        forced_latlon=latlon,
        rf_rms_hz=metrics.get("held_capped_rms_hz"),
    )
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        boundary=BOUNDARY,
        metrics=metrics,
        arms=dict(c0=arm, fitted_c=dict(arm)),
    )


def solve(observation, catalogue, *, regions=None):
    start, cpu = perf_counter(), process_time()
    if regions is not None and (len(regions) != 4 or np.asarray(regions).shape != (4, 2)):
        raise ValueError("regional search takes four ordered latitude-longitude centers")
    normal, count = prepare(observation, catalogue)
    control, _ = prepare(observation, catalogue, shifted=True)
    ready = perf_counter()
    if normal and regions is None:
        positive, labels = global_search(normal)
        negative, _ = global_search(control)
    elif normal:
        positive, labels = offered_search(normal, regions)
        negative, _ = offered_search(control, regions)
    else:
        positive, negative, labels = [], [], regions
    null = min(negative, key=lambda row: row["early"], default=None)
    result = summarize(positive, normal, labels, None if null is None else null["held"])
    result["metrics"].update(
        orbit_count=count,
        solve_wall_s=perf_counter() - start,
        solve_cpu_s=process_time() - cpu,
        orbit_preparation_wall_s=ready - start,
        time_control_capped_rms_hz=None if null is None else float(np.sqrt(null["held"])),
        time_control_forced_latlon=None if null is None else null["point"].tolist(),
    )
    return result
