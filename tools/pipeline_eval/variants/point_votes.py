"""Cold localization from anonymous pairs of native CFO and frame-epoch peaks."""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter

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

LIGHT_KM_S = 299792.458
ALIAS_HZ = 1 / 4.4e-6
FRAME_HZ = 750
BIAS = np.arange(-256.0, 257.0, 16.0)
EARTH_POINTS = 3600
BOUNDARY = "Authenticated GLRT CFO and epoch pairs plus causal TLE to location decision"


@dataclass(frozen=True)
class Pair:
    t0: float
    t1: float
    rf_hz: float
    cfo_slope: float
    code_slope: float
    strength: float
    interval: int


@dataclass(frozen=True)
class OrbitPair:
    pair: Pair
    pos0: np.ndarray
    pos1: np.ndarray
    vel0: np.ndarray
    vel1: np.ndarray
    tree: cKDTree


def wrapped(value, period):
    return (value + period / 2) % period - period / 2


def _peaks(probe):
    peaks = []
    for point in sorted(probe["candidates"], key=lambda point: -point["fractional_margin"]):
        margin = point["fractional_margin"]
        if not point["passed_fractional_margin_gate"] or margin < 0.1:
            continue
        frequency = point["fractional_tracking_cfo_hz"]
        epoch = point["integer_epoch_sample"] + point["fractional_epoch_offset_samples"]
        if all(
            abs(wrapped(p[0] - frequency, ALIAS_HZ)) > 120 or abs(p[1] - epoch) > 6 for p in peaks
        ):
            peaks.append((frequency, epoch, margin))
        if len(peaks) >= 3:
            break
    return peaks


def pair_votes(capture):
    """Use the complete valid probe stream before capping spatial voting work."""
    groups = defaultdict(list)
    selected_peaks = 0
    for probe in capture.probes:
        peaks = _peaks(probe)
        if peaks:
            key = probe["receiver_id"], probe["channel"], probe["actual_rf_hz"]
            groups[key].append((probe["valid_start_counter"], peaks))
            selected_peaks += len(peaks)
    rate = capture.sample_rate_hz
    half_probe = capture.probe_ms / 2000
    frame_samples = rate / FRAME_HZ
    voted = defaultdict(list)
    pair_count = 0
    for (_, _, rf_hz), group in groups.items():
        group.sort(key=lambda row: row[0])
        counters = [counter for counter, _ in group]
        for right, (counter, peaks) in enumerate(group):
            near = bisect_left(counters, counter - 1.5 * rate, 0, right)
            for left in (near - 1, near):
                if not 0 <= left < right:
                    continue
                lag = counter - counters[left]
                dt = lag / rate
                if not 0.9 <= dt <= 2.4:
                    continue
                t1 = (counter - capture.first_counter) / rate + half_probe
                midpoint = t1 - dt / 2
                interval = int(midpoint / 2)
                for f1, e1, m1 in peaks:
                    for f0, e0, m0 in group[left][1]:
                        cfo_slope = wrapped(f1 - f0, ALIAS_HZ) / dt
                        code_slope = wrapped(lag + e1 - e0, frame_samples) / dt
                        if -6500 <= cfo_slope <= -500 and abs(code_slope) <= 350:
                            voted[interval].append(
                                Pair(
                                    t1 - dt, t1, rf_hz, cfo_slope, code_slope, min(m0, m1), interval
                                )
                            )
                            pair_count += 1
    pairs = [
        max(voted[k], key=lambda p: (p.strength, abs(p.cfo_slope), p.t1 - p.t0))
        for k in sorted(voted)
    ]
    return pairs, dict(
        probe_rows=len(capture.probes),
        retained_input_peaks=selected_peaks,
        eligible_pairs=pair_count,
        selected_pairs=len(pairs),
    )


def orbit_pairs(capture, pairs):
    catalogue = parse_element_sets(capture.catalog.decode("ascii"))
    satrecs = [
        sat
        for name, sat in zip(catalogue.names, catalogue.satellites, strict=True)
        if name.startswith("STARLINK")
    ]
    knots = sorted({t for p in pairs for t in (p.t0, p.t1)})
    indices = {t: i for i, t in enumerate(knots)}
    times_ns = capture.anchor_utc_ns + np.rint(np.asarray(knots) * 1e9).astype(np.int64)
    jd, fraction = julian_day_from_utc_ns(times_ns)
    angles = greenwich_mean_sidereal_time_rad(jd, fraction)
    errors, positions, velocities = SatrecArray(satrecs).sgp4(jd, fraction)
    orbits = []
    for pair in pairs:
        a, b = indices[pair.t0], indices[pair.t1]
        rows = (errors[:, a] == 0) & (errors[:, b] == 0)
        p0, v0 = teme_to_ecef(positions[rows, a], velocities[rows, a], angles[a])
        p1, v1 = teme_to_ecef(positions[rows, b], velocities[rows, b], angles[b])
        radius = np.linalg.norm(p0, axis=1)
        valid = (radius >= 6500) & (radius <= 7350) & np.isfinite(p1).all(axis=1)
        p0, p1, v0, v1, radius = (a[valid] for a in (p0, p1, v0, v1, radius))
        orbits.append(OrbitPair(pair, p0, p1, v0, v1, cKDTree(p0 / radius[:, None])))
    return orbits, dict(
        catalogue_satellites=len(satrecs), sgp4_evaluations=len(satrecs) * len(knots)
    )


def _euclidean(points):
    xyz = np.stack([geodetic_to_ecef_km(lat, lon, 0) for lat, lon in points])
    unit = xyz / np.linalg.norm(xyz, axis=1)[:, None]
    return xyz, unit


def vote_matrix(orbits, points, sample_rate):
    """Average each point's best satellite support per independent pair and clock bias."""
    xyz, unit = _euclidean(points)
    scored = np.zeros((len(points), len(BIAS)))
    one = np.zeros_like(scored)
    chord = 2 * np.sin(np.deg2rad(10))
    for orbit in orbits:
        choices = orbit.tree.query_ball_point(unit, chord, return_sorted=False)
        sizes = np.fromiter(map(len, choices), dtype=int, count=len(points))
        if not np.any(sizes):
            continue
        site = np.repeat(np.arange(len(points)), sizes)
        sat = np.concatenate(choices).astype(int, copy=False)
        d0, d1 = orbit.pos0[sat] - xyz[site], orbit.pos1[sat] - xyz[site]
        range0, range1 = np.linalg.norm(d0, axis=1), np.linalg.norm(d1, axis=1)
        radial = unit[site]
        above = ((d0 * radial).sum(axis=1) > range0 * 0.25) & (
            (d1 * radial).sum(axis=1) > range1 * 0.25
        )
        dt = orbit.pair.t1 - orbit.pair.t0
        rate0 = np.einsum("ij,ij->i", d0, orbit.vel0[sat]) / range0
        rate1 = np.einsum("ij,ij->i", d1, orbit.vel1[sat]) / range1
        cfo = (rate0 - rate1) * orbit.pair.rf_hz / (dt * LIGHT_KM_S)
        cfo_error = (cfo - orbit.pair.cfo_slope) / 450.0
        keep = above & (abs(cfo_error) < 3)
        if not np.any(keep):
            continue
        code = (range1[keep] - range0[keep]) * sample_rate / (dt * LIGHT_KM_S)
        needed_bias = orbit.pair.code_slope - code
        core = cfo_error[keep, None] ** 2 + ((needed_bias[:, None] - BIAS) / 18.0) ** 2
        one.fill(0)
        np.maximum.at(one, site[keep], np.exp(-0.5 * core))
        scored += one
    return scored / max(1, len(orbits))


def earth_mesh(size=EARTH_POINTS):
    i = np.arange(size)
    z = 1 - (2 * i + 1) / size
    return np.column_stack((np.rad2deg(np.arcsin(z)), wrapped(i * 137.50776405003785, 360)))


def _around(center, step):
    lat, lon = center
    offsets = np.arange(-2, 3) * step
    return np.array(
        [
            (
                np.clip(lat + a, -89.999, 89.999),
                wrapped(lon + b / max(0.03, np.cos(np.deg2rad(lat))), 360),
            )
            for a in offsets
            for b in offsets
        ]
    )


def _spaced(points, scores, count, separation_km):
    xyz, _ = _euclidean(points)
    selected = []
    for index in np.argsort(-scores, kind="stable"):
        if all(np.linalg.norm(xyz[old] - xyz[index]) > separation_km for old in selected):
            selected.append(index)
        if len(selected) >= count:
            break
    return selected


def _search(train, held, rate, tile):
    if tile is None:
        initial = earth_mesh()
        steps = (0.85, 0.25, 0.075, 0.0225)

        def domain(points):
            return points
    else:
        center = np.array(tile)
        center_xyz, _ = _euclidean([center])
        initial = _around(center, 0.055)
        steps = (0.025, 0.008, 0.0025)

        def domain(points):
            xyz, _ = _euclidean(points)
            return points[np.linalg.norm(xyz - center_xyz, axis=1) <= 12.5]

        initial = domain(initial)
    initial_fit = vote_matrix(train, initial, rate)
    evaluated = len(initial)
    indices = _spaced(initial, initial_fit.max(axis=1), 8, 275 if tile is None else 5)
    minima = []
    for index in indices:
        point = initial[index]
        best = initial_fit[index]
        for step in steps:
            centers = domain(_around(point, step))
            fit = vote_matrix(train, centers, rate)
            evaluated += len(centers)
            index = np.argmax(fit.max(axis=1))
            if fit[index].max() > best.max():
                point, best = centers[index], fit[index]
        minima.append((point, int(best.argmax()), float(best.max())))
    minima.sort(key=lambda row: -row[2])
    positions = np.stack([v[0] for v in minima])
    holdout = vote_matrix(held, positions, rate)
    held_scores = holdout[np.arange(len(minima)), [v[1] for v in minima]]
    return positions[0], dict(
        support_training=minima[0][2],
        evaluated_locations=evaluated,
        sample_clock_slope=float(BIAS[minima[0][1]]),
        finalist_locations=positions.tolist(),
        finalist_validation=held_scores.tolist(),
        **validation_metrics(positions, held_scores, supplied=tile is not None),
    )


def validation_metrics(positions, held_scores, *, supplied):
    xyz, _ = _euclidean(positions)
    far = np.linalg.norm(xyz - xyz[0], axis=1) > (6 if supplied else 250)
    scores = np.asarray(held_scores)
    alternate = float(scores[far].max()) if np.any(far) else None
    return dict(
        support_validation=float(scores[0]),
        held_alternative=alternate,
        held_lead=float(scores[0] - alternate) if alternate is not None else None,
        spatially_separated_finalists=int(far.sum()),
    )


def decision(metrics):
    lead = metrics["held_lead"]
    if lead is None:
        return False, "no spatially separated validation alternative"
    if metrics["support_validation"] < 0.20 or lead < 0.07:
        return False, "insufficient held-out lead or support"
    return True, "held-out pairs confirm the location"


def solve(capture, *, tile=None):
    start = perf_counter()
    pairs, metrics = pair_votes(capture)
    train_count = sum(p.interval % 4 != 3 for p in pairs)
    held_count = len(pairs) - train_count
    metrics.update(
        training_pairs=train_count,
        validation_pairs=held_count,
        policy_mode="no_site" if tile is None else "supplied_tile",
        c_cancels_exactly=True,
    )
    point = None
    passed = False
    reason = "insufficient independent pairs"
    if train_count >= 16 and held_count >= 6:
        orbits, orbit_metrics = orbit_pairs(capture, pairs)
        metrics.update(orbit_metrics)
        train = [p for p in orbits if p.pair.interval % 4 != 3]
        held = [p for p in orbits if p.pair.interval % 4 == 3]
        point, votes = _search(train, held, capture.sample_rate_hz, tile)
        metrics.update(votes)
        passed, reason = decision(votes)
    metrics["algorithm_wall_s"] = perf_counter() - start
    point = None if point is None else point.tolist()
    arm = dict(latlon=point if passed else None, forced_latlon=point, rf_rms_hz=None)
    return dict(
        status="ok" if passed else "withheld",
        reason=reason,
        boundary=BOUNDARY,
        metrics=metrics,
        arms={"c0": arm, "fitted_c": dict(arm)},
    )
