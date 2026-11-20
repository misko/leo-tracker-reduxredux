"""Truth-free receiver from prepared anonymous beacon-frequency arcs and causal TLEs."""

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

LIGHT_KM_S = 299_792.458
SIGMA_HZ = 1500.0
TRAIN = 6
SAMPLE_COUNT = 9
BOUNDARY = "Prepared anonymous measured beacon frequency tracks plus causal TLE to position"


@dataclass(frozen=True)
class Arc:
    frequency: np.ndarray
    rf_hz: float
    position: np.ndarray
    velocity: np.ndarray
    numbers: np.ndarray
    sky: cKDTree


def _arc(catalogue, orbits, anchor, track):
    times, values = (np.asarray(track[k], dtype=float) for k in ("times", "values"))
    if times.shape != values.shape or not np.isfinite(times).all() or not np.isfinite(values).all():
        raise ValueError("track times and beacon frequencies must be finite and aligned")
    if len(times) < SAMPLE_COUNT or np.any(np.diff(times) <= 0):
        return None
    use = np.rint(np.linspace(0, len(times) - 1, SAMPLE_COUNT)).astype(int)
    jd, fraction = julian_day_from_utc_ns(anchor + np.rint(times[use] * 1e9).astype("i8"))
    errors, position, velocity = orbits.sgp4(jd, fraction)
    good = (errors == 0).all(axis=1) & np.isfinite(position).all(axis=(1, 2))
    radius = np.linalg.norm(position[:, TRAIN // 2], axis=1)
    good &= (radius > 6500) & (radius < 7350)
    p, v = teme_to_ecef(
        position[good], velocity[good], greenwich_mean_sidereal_time_rad(jd, fraction)
    )
    sky = cKDTree(p[:, TRAIN // 2] / radius[good, None])
    return Arc(values[use], float(track["rf_hz"]), p, v, np.asarray(catalogue)[good], sky)


def prepare(observation, catalogue):
    parsed = parse_element_sets(catalogue)
    orbits, numbers = [], []
    for satellite, number, epoch in zip(
        parsed.satellites,
        parsed.satellite_numbers,
        parsed.element_epoch_utc_ns(),
        strict=True,
    ):
        if epoch <= observation["cutoff_utc_ns"]:
            orbits.append(satellite)
            numbers.append(number)
    if not orbits:
        raise ValueError("no causal orbital elements at the acquisition cutoff")
    provider = SatrecArray(orbits)
    arcs = []
    for track in observation["tracks"]:
        arc = _arc(numbers, provider, observation["anchor_utc_ns"], track)
        if arc is not None:
            arcs.append(arc)
    return arcs, len(orbits)


def profile_cfo(observed, projected):
    """Train an additive per-arc offset and preserve the untouched validation residual."""
    delta = observed - projected
    offset = delta[..., :TRAIN].mean(axis=-1, keepdims=True)
    residual = delta - offset
    return (
        np.mean(residual[..., :TRAIN] ** 2, axis=-1),
        np.mean(residual[..., TRAIN:] ** 2, axis=-1),
    )


def _xyz(locations):
    xyz = np.stack([geodetic_to_ecef_km(lat, lon, 0) for lat, lon in locations])
    return xyz, xyz / np.linalg.norm(xyz, axis=-1, keepdims=True)


def _arc_scores(arc, xyz, up):
    # A conservative Earth radius gives a larger shortlist than the horizon.
    # The projected ray supplies the final gate.
    extent = np.linalg.norm(arc.position[:, TRAIN // 2], axis=1).max(initial=6370)
    horizon = 2 * np.sin(0.5 * np.arccos(6350 / extent))
    candidates = arc.sky.query_ball_point(up, horizon, return_sorted=False)
    counts = np.fromiter(map(len, candidates), dtype=int, count=len(candidates))
    n = len(counts)
    train, held, ids = np.full(n, np.inf), np.full(n, np.inf), np.full(n, -1)
    if not counts.any():
        return train, held, ids
    site = np.repeat(np.arange(n), counts)
    sat = np.concatenate(candidates).astype(int, copy=False)
    delta = arc.position[sat] - xyz[site, None]
    distance = np.linalg.norm(delta, axis=-1)
    visible = np.einsum("nsi,ni->ns", delta, up[site]) > 0
    projected = (
        -arc.rf_hz * np.einsum("nsi,nsi->ns", delta, arc.velocity[sat]) / (LIGHT_KM_S * distance)
    )
    training, validation = profile_cfo(arc.frequency, projected)
    training[~visible[:, :TRAIN].all(axis=-1)] = np.inf
    validation[~visible[:, TRAIN:].all(axis=-1)] = np.inf
    validation[~np.isfinite(training)] = np.inf
    offset = 0
    for index, count in enumerate(counts):
        if count:
            selected = offset + np.argmin(training[offset : offset + count])
            train[index], held[index], ids[index] = (
                training[selected],
                validation[selected],
                arc.numbers[sat[selected]],
            )
            offset += count
    return train, held, ids


def evaluate(arcs, locations):
    """Assign each training arc independently and summarize its held evidence."""
    xyz, up = _xyz(locations)
    trained, validated, supported, residual = [], [], [], []
    for start in range(0, len(locations), 128):
        stop = start + 128
        train, held, ids = zip(
            *(_arc_scores(a, xyz[start:stop], up[start:stop]) for a in arcs), strict=True
        )
        train, held, ids = map(np.stack, (train, held, ids))
        good = (train <= SIGMA_HZ**2) & (held <= SIGMA_HZ**2)
        trained.extend(np.mean(1 / (1 + train / SIGMA_HZ**2), axis=0))
        validated.extend(np.mean(1 / (1 + held / SIGMA_HZ**2), axis=0))
        supported.extend(len(set(ids[good[:, i], i])) for i in range(ids.shape[1]))
        residual.extend(
            float(np.sqrt(np.mean(held[good[:, i], i]))) if good[:, i].any() else None
            for i in range(ids.shape[1])
        )
    return np.asarray(trained), np.asarray(validated), supported, residual


def _around(center, size):
    lat, lon = center
    offsets = np.arange(-2, 3) * size
    return np.array(
        [
            (
                np.clip(lat + dy, -89.999, 89.999),
                (lon + dx / max(0.03, np.cos(np.deg2rad(lat))) + 180) % 360 - 180,
            )
            for dy in offsets
            for dx in offsets
        ]
    )


def _best_sites(points, values, distance):
    xyz, _ = _xyz(points)
    selected = []
    for i in np.argsort(-values, kind="stable"):
        if all(np.linalg.norm(xyz[i] - xyz[j]) >= distance for j in selected):
            selected.append(i)
        if len(selected) >= 8:
            break
    return selected


def search(arcs, tile):
    if tile is None:
        i = np.arange(3600)
        initial = np.column_stack(
            (
                np.rad2deg(np.arcsin(1 - (2 * i + 1) / len(i))),
                (i * 137.50776405003785 + 180) % 360 - 180,
            )
        )
        steps, separation = (0.85, 0.25, 0.075, 0.0225), 250

        def inside(points):
            return points

    else:
        center, _ = _xyz([tile])
        steps, separation = (0.025, 0.008, 0.0025), 6

        def inside(points):
            xyz, _ = _xyz(points)
            return points[np.linalg.norm(xyz - center, axis=1) <= 12.5]

        initial = inside(_around(tile, 0.055))
    train, validation, supports, rms = evaluate(arcs, initial)
    count = len(initial)
    finalists = []
    for index in _best_sites(initial, train, separation):
        point = initial[index]
        best = (float(train[index]), float(validation[index]), supports[index], rms[index])
        finalists.append((point, best))
        for step in steps:
            local = inside(_around(point, step))
            score, held, sats, hz = evaluate(arcs, local)
            count += len(local)
            index = int(np.argmax(score))
            if score[index] > best[0]:
                point = local[index]
                best = float(score[index]), float(held[index]), sats[index], hz[index]
        finalists.append((point, best))
    point, result = max(finalists, key=lambda p: p[1][0])
    points = np.asarray([p[0] for p in finalists])
    xyz, _ = _xyz(points)
    x, _ = _xyz([point])
    alt = [
        p[1][1]
        for p, d in zip(finalists, np.linalg.norm(xyz - x, axis=1), strict=True)
        if d > separation
    ]
    lead = float(result[1] - max(alt)) if alt else None
    return point.tolist(), dict(
        training_score=result[0],
        validation_score=result[1],
        validated_orbits=result[2],
        conditional_validation_rms_hz=result[3],
        validation_lead=lead,
        evaluated_locations=count,
    )


def solve(observation, catalogue, *, tile=None):
    start = perf_counter()
    arcs, sat_count = prepare(observation, catalogue) if observation["tracks"] else ([], 0)
    metrics = dict(
        tracks=len(observation["tracks"]),
        fitted_tracks=len(arcs),
        causal_orbits=sat_count,
        calibration_constant_cancels=True,
    )
    point = None
    published = False
    if len(arcs) >= 3:
        point, validation = search(arcs, tile)
        metrics.update(validation)
        lead = metrics["validation_lead"]
        published = (
            metrics["validated_orbits"] >= 3
            and metrics["validation_score"] >= 0.35
            and lead is not None
            and lead >= 0.08
        )
    metrics["solver_wall_s"] = perf_counter() - start
    arm = dict(
        latlon=point if published else None,
        forced_latlon=point,
        rf_rms_hz=metrics.get("conditional_validation_rms_hz"),
    )
    return dict(
        status="ok" if published else "withheld",
        boundary=BOUNDARY,
        metrics=metrics,
        reason="held observations support a distinct site"
        if published
        else "insufficient held orbit support or distinct-site lead",
        arms={"c0": arm, "fitted_c": dict(arm)},
    )
