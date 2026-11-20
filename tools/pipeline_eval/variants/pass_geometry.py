"""Use closest-approach geometry to propose sites and coherent CFO to rank orbit labels."""

from dataclasses import dataclass
from itertools import product
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from sgp4.api import SatrecArray

from leo.sky.frames import (
    WGS84_ECCENTRICITY_SQUARED,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets
from tools.pipeline_eval.variants import rate_triplets as rate

METHOD = "pass_geometry"
BOUNDARY = "Native GLRT triplets and causal TLE to closest-approach proposals and paired positions"
SPEED_KM_S = 7.45
ARC_RAD = np.deg2rad(25)
ELEVATION_SINE = np.sin(np.deg2rad(5))


@dataclass(frozen=True)
class Pass:
    segment: int
    time_s: float
    slope_hz_s: float
    residual_hz: float


def fit_pass(segment, index):
    times = segment.times - segment.times[rate.MID]
    observed = segment.frequency - segment.frequency.mean()
    amplitude = SPEED_KM_S * segment.rf_hz / rate.LIGHT_KM_S
    bounds = ([times[0] - 55, 40], [times[-1] + 55, 240])

    def residual(parameters):
        relative = times - parameters[0]
        model = -amplitude * relative / np.hypot(relative, parameters[1])
        return observed - (model - model.mean())

    fits = [
        least_squares(residual, [offset, 85.0], bounds=bounds, max_nfev=32)
        for offset in (0, 28 if observed[0] + observed[-1] > 0 else -28)
    ]
    best = min(fits, key=lambda x: x.cost)
    error = float(np.sqrt(np.mean(best.fun**2)))
    slope = float(amplitude / best.x[1])
    if error <= 270 and 950 <= slope <= 6500:
        return Pass(index, float(segment.times[rate.MID] + best.x[0]), slope, error)
    return None


def stable_passes(segments):
    local = [p for i, s in enumerate(segments) if (p := fit_pass(s, i)) is not None]
    out = []
    for entry in sorted(local, key=lambda p: p.residual_hz):
        if all(abs(entry.time_s - other.time_s) >= 8 for other in out):
            out.append(entry)
        if len(out) == 8:
            break
    return out


def pass_states(capture, orbits, passes):
    catalog = parse_element_sets(capture.catalog.decode("ascii"))
    selected = {
        number: sat
        for number, sat, epoch in zip(
            catalog.satellite_numbers,
            catalog.satellites,
            catalog.element_epoch_utc_ns(),
            strict=True,
        )
        if epoch <= capture.cutoff_utc_ns
    }
    satellite = SatrecArray([selected[n] for n in orbits])
    times = np.array([p.time_s for p in passes])[:, None] + [-0.75, 0.0, 0.75]
    utc = capture.anchor_utc_ns + np.rint(times.reshape(-1) * 1e9).astype(np.int64)
    jd, fraction = julian_day_from_utc_ns(utc)
    errors, position, velocity = satellite.sgp4(jd, fraction)
    p, v = teme_to_ecef(position, velocity, greenwich_mean_sidereal_time_rad(jd, fraction))
    p = p.reshape(len(orbits), len(passes), 3, 3)
    v = v.reshape(p.shape)
    good = np.all(errors.reshape(len(orbits), len(passes), 3) == 0, axis=2)
    return p[:, :, 1], v[:, :, 1], (v[:, :, 2] - v[:, :, 0]) / 1.5, good


def intersect_pass(p, v, a, target_acceleration, side, *, earth_km=rate.EARTH_KM):
    """Solve range acceleration on the circle where radial velocity is zero."""
    speed = np.linalg.norm(v, axis=1)
    normal = v / speed[:, None]
    plane_projection = np.sum(p * normal, axis=1)
    center = plane_projection[:, None] * normal
    circle = np.sqrt(np.maximum(0.0, earth_km**2 - plane_projection**2))
    near = p - center
    first = near / np.linalg.norm(near, axis=1)[:, None]
    second = side * np.cross(normal, first)

    def point(theta):
        return center + circle[:, None] * (
            np.cos(theta)[:, None] * first + np.sin(theta)[:, None] * second
        )

    def acceleration(theta):
        displacement = p - point(theta)
        return (speed**2 + np.sum(displacement * a, axis=1)) / np.linalg.norm(displacement, axis=1)

    low = np.zeros(len(p))
    high = np.full(len(p), ARC_RAD)
    feasible = (abs(plane_projection) < earth_km) & (
        (acceleration(low) >= target_acceleration) & (acceleration(high) <= target_acceleration)
    )
    for _ in range(18):
        midpoint = (high + low) / 2
        inside = acceleration(midpoint) >= target_acceleration
        low = np.where(inside, midpoint, low)
        high = np.where(inside, high, midpoint)
    site = point((low + high) / 2)
    delta = p - site
    above = np.sum(delta * site, axis=1) > ELEVATION_SINE * earth_km * np.linalg.norm(delta, axis=1)
    return site, feasible & above


def unit_to_coordinates(xyz):
    latitude = np.arctan2(
        xyz[..., 2], (1 - WGS84_ECCENTRICITY_SQUARED) * np.hypot(xyz[..., 0], xyz[..., 1])
    )
    longitude = np.arctan2(xyz[..., 1], xyz[..., 0])
    return np.rad2deg(np.stack((latitude, longitude), axis=-1))


def coordinates_to_unit(points):
    position = geodetic_to_ecef_km(points[:, 0], points[:, 1], 0.0).T
    return position / np.linalg.norm(position, axis=1)[:, None]


def geometric_proposals(capture, segments, sky, passes):
    p, v, a, valid = pass_states(capture, sky.ids, passes)
    groups = []
    for k, entry in enumerate(passes):
        i = entry.segment
        rf = segments[i].rf_hz
        target = entry.slope_hz_s * rate.LIGHT_KM_S / rf
        pieces = []
        for side in (-1, 1):
            orbit = np.flatnonzero(valid[:, k])
            xyz, feasible = intersect_pass(p[orbit, k], v[orbit, k], a[orbit, k], target, side)
            orbital = orbit[feasible]
            locations = unit_to_coordinates(xyz[feasible])
            fixed = geodetic_to_ecef_km(locations[:, 0], locations[:, 1], 0.0).T
            offset = sky.positions[i, orbital] - fixed[:, None, :]
            velocity = np.sum(sky.velocities[i, orbital] * offset, axis=-1)
            expected = -rf / rate.LIGHT_KM_S * velocity / np.linalg.norm(offset, axis=-1)
            residual = sky.measured[i] - expected
            shape_rms = np.std(residual, axis=1)
            good = shape_rms <= 1050
            pieces.append((locations[good], shape_rms[good]))
        location = np.concatenate([locations for locations, _ in pieces])
        residual = np.concatenate([rms for _, rms in pieces])
        if len(location):
            groups.append((coordinates_to_unit(location), residual))
    return groups


def seed_cells(groups):
    xyz = coordinates_to_unit(rate.spherical_grid())
    lookup = cKDTree(xyz)
    votes = np.zeros(len(xyz))
    totals = np.zeros_like(xyz)
    for positions, errors in groups:
        distance, ids = lookup.query(positions)
        weight = np.exp(-0.5 * (errors / 550) ** 2 - 0.5 * (distance * rate.EARTH_KM / 180) ** 2)
        best = np.zeros(len(xyz))
        selected = np.full(len(xyz), -1, dtype=int)
        for i in np.argsort(weight, kind="stable"):
            selected[ids[i]] = i
            best[ids[i]] = weight[i]
        valid = selected >= 0
        votes += best
        totals[valid] += positions[selected[valid]] * best[valid, None]
    representatives = []
    for j in np.argsort(-votes, kind="stable"):
        if votes[j] <= 0:
            break
        site = unit_to_coordinates(totals[j])
        if all(rate.separation(site, prior) >= 450 for prior in representatives):
            representatives.append(site)
        if len(representatives) == 10:
            break
    return representatives


def coherent(sky, segments, site):
    track, orbit, shape_rms, offset = sky.evaluate(site, detail=True)
    choices = []
    for i in range(len(segments)):
        peers = np.flatnonzero((track == i) & (shape_rms <= 700))
        choices.append(peers[np.argsort(shape_rms[peers], kind="stable")[:6]])
    selected, weight = {}, {}
    shape_weight = np.exp(-0.5 * (shape_rms / 230) ** 2)
    for group in range(4):
        members = [i for i, s in enumerate(segments) if s.group == group and len(choices[i])]
        if not members:
            continue
        centers = offset[np.concatenate([choices[i] for i in members])]
        score = np.zeros(len(centers))
        for i in members:
            options = choices[i]
            difference = rate.wrap(centers[:, None] - offset[options])
            score += np.max(np.exp(-0.5 * (difference / 1800) ** 2) * shape_weight[options], axis=1)
        center = centers[np.argmax(score)]
        for i in members:
            options = choices[i]
            difference = rate.wrap(offset[options] - center)
            merit = np.exp(-0.5 * (difference / 1800) ** 2) * shape_weight[options]
            j = int(np.argmax(merit))
            if abs(difference[j]) <= 3500:
                label = int(orbit[options[j]])
                selected[i] = label, float(shape_rms[options[j]]), float(center)
                weight[label] = max(weight.get(label, 0.0), float(merit[j]))
    return sum(weight.values()) + 0.2 * len(selected), selected


def mesh(site, step):
    return (rate.offset_site(site, step * x, step * y) for x, y in product(range(-2, 3), repeat=2))


def search(sky, segments, tile, seeds):
    def rank(sites):
        return sorted(
            ((coherent(sky, segments, site), site) for site in sites),
            key=lambda row: row[0][0],
            reverse=True,
        )

    if tile is None:
        refined = []
        for seed in seeds:
            for step, width in ((60, 1800), (15, 550), (3.5, 230)):
                ((_, seed),) = rate.consensus(sky, mesh(seed, step), width, 1, 0)
            refined.append(seed)
        candidates = rank(refined)
        winner = candidates[0][1]
        alternative = next(
            (r[0][0] for r in candidates[1:] if rate.separation(r[1], winner) > 250), None
        )
        return candidates[0], alternative
    center, radius = tile["center"], tile["width_km"] / 2
    offsets = np.linspace(-radius, radius, 1 + int(np.ceil(radius * 2 / 3)))
    winners = rank(rate.offset_site(center, x, y) for x, y in product(offsets, repeat=2))[:3]
    for step in (1, 0.3):
        sites = (
            site
            for _, p in winners
            for site in mesh(p, step)
            if np.max(abs(rate.local_xy(center, site))) <= radius + 1e-8
        )
        winners = rank(sites)[:3]
    return winners[0], None


def run(capture, *, tile=None):
    start = perf_counter()
    segments = rate.tracklets(capture)
    passed = stable_passes(segments)
    metrics = dict(
        tracks=len(segments),
        native_probes=len(capture.probes),
        estimated_passes=len(passed),
        stage_s={"tracklets_and_pass_fits": perf_counter() - start},
    )
    arms = {a: {"latlon": None, "forced_latlon": None} for a in rate.ARMS}

    def result(reason=None):
        return dict(
            status="withheld" if reason else "ok",
            arms=arms,
            metrics=metrics,
            boundary=BOUNDARY,
            **({"reason": reason} if reason else {}),
        )

    if len(segments) < 4:
        return result("fewer than four qualifying native tracklets")
    start = perf_counter()
    sky = rate.prepare_sky(capture, segments)
    metrics["causal_orbits"] = len(sky.ids)
    metrics["stage_s"]["orbit_propagation"] = perf_counter() - start
    start = perf_counter()
    seeds = []
    if tile is None:
        groups = geometric_proposals(capture, segments, sky, passed) if passed else []
        metrics.update(proposing_passes=len(groups), geometric_sites=sum(len(g[0]) for g in groups))
        if len(groups) < 2:
            return result("fewer than two separated pass times made feasible orbit intersections")
        seeds = seed_cells(groups)
        metrics["refined_basins"] = len(seeds)
    metrics["stage_s"]["geometry"] = perf_counter() - start
    start = perf_counter()
    ((support, selected), site), other = search(sky, segments, tile, seeds)
    metrics["stage_s"]["search"] = perf_counter() - start
    labels = sorted({int(sky.ids[j]) for j, _, _ in selected.values()})
    channels = sorted({segments[i].channel for i in selected})
    metrics.update(
        shape_latlon=site.tolist(),
        selected_tracks=len(selected),
        selected_orbits=labels,
        selected_channels=channels,
        coherent_score=support,
        alternate_coherent_score=other,
    )
    if not selected:
        for arm in arms.values():
            arm["forced_latlon"] = site.tolist()
        return result("no coherent orbital labels")
    rms = float(np.median([e for _, e, _ in selected.values()]))
    metrics["median_centered_shape_rms_hz"] = rms
    credible = (
        len(labels) >= 4
        and len(channels) >= 2
        and rms <= 300
        and (tile is not None or other is None or support - other >= 1.5)
    )
    start = perf_counter()
    for arm in rate.ARMS:
        fit = rate.fit(sky, segments, selected, site, tile, arm == "fitted_c")
        arms[arm].update(fit)
        if credible and fit["conditional_rms_hz"] <= 1200:
            arms[arm]["latlon"] = fit["forced_latlon"]
            arms[arm]["rf_rms_hz"] = fit["conditional_rms_hz"]
    metrics["stage_s"]["fit"] = perf_counter() - start
    return result(
        None
        if any(r["latlon"] is not None for r in arms.values())
        else "joint frequency or spatial consistency withheld the forced fit"
    )
