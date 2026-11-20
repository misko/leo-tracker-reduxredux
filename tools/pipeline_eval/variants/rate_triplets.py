"""Native GLRT triplet tracklets, physical Doppler consensus, and a compact fit."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares
from sgp4.api import SatrecArray

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets

ARMS = ("c0", "fitted_c")
METHOD = "rate_triplets"
PERIOD_HZ = 1 / 4.4e-6
LIGHT_KM_S = 299_792.458
EARTH_KM = 6371.0
MID = 3
GOLDEN_ANGLE = np.pi * (3 - np.sqrt(5))
SHAPE_TIMES = np.linspace(-1, 1, 7)


@dataclass(frozen=True)
class Segment:
    receiver: int
    channel: int
    rf_hz: float
    points: int
    times: np.ndarray
    frequency: np.ndarray
    curvature_hz: float
    noise_hz: float

    @property
    def group(self):
        return self.receiver * 2 + int(self.channel > 4)


def wrap(value):
    return (value + PERIOD_HZ / 2) % PERIOD_HZ - PERIOD_HZ / 2


def peaks(capture):
    lanes = defaultdict(list)
    for probe in capture.probes:
        key = probe["receiver_id"], probe["channel"], probe["actual_rf_hz"]
        time = (
            probe["valid_start_counter"] - capture.first_counter
        ) / capture.sample_rate_hz + capture.probe_ms / 2000
        eligible = sorted(
            (p for p in probe["candidates"] if p["passed_fractional_margin_gate"]),
            key=lambda p: (-p["fractional_margin"], p["candidate_rank"]),
        )
        chosen = []
        for row in eligible:
            f = float(wrap(row["fractional_tracking_cfo_hz"]))
            if all(abs(float(wrap(f - prior))) >= 160 for prior in chosen):
                chosen.append(f)
            if len(chosen) == 3:
                break
        if chosen:
            lanes[key].append((time, np.array(chosen)))
    return lanes


def successive_seeds(times, freqs, used, first, index):
    t0 = times[first]
    f0 = freqs[first][index]
    options = []
    for second in range(first + 1, min(first + 3, len(times))):
        dt = times[second] - t0
        if not 0 < dt <= 1.5:
            break
        for k in np.flatnonzero(~used[second]):
            f1 = f0 + wrap(freqs[second][k] - f0)
            rate = (f1 - f0) / dt
            if abs(rate) > 6500:
                continue
            for third in range(second + 1, min(second + 3, len(times))):
                elapsed = times[third] - t0
                if elapsed > 2.4:
                    break
                prediction = f0 + rate * elapsed
                for peak in np.flatnonzero(~used[third]):
                    residual = wrap(freqs[third][peak] - prediction)
                    if abs(residual) <= 550:
                        options.append(
                            (
                                abs(residual),
                                [
                                    (first, index, f0),
                                    (second, k, f1),
                                    (third, peak, prediction + residual),
                                ],
                            )
                        )
    return [seed for _, seed in sorted(options, key=lambda item: item[0])[:2]]


def extend(times, freqs, used, seed):
    path = seed.copy()
    start = times[path[0][0]]
    idx = np.array([p[0] for p in path])
    t, f = times[idx], np.array([p[2] for p in path])
    for i in range(path[-1][0] + 1, len(times)):
        if times[i] - start > 45 or times[i] - t[-1] > 2.5:
            break
        if used[i].all():
            continue
        tx, fx = t[-7:], f[-7:]
        relative = tx - tx.mean()
        rate = (relative @ fx) / (relative @ relative)
        prediction = fx.mean() + rate * (times[i] - tx.mean())
        residual = wrap(freqs[i] - prediction)
        j = int(np.argmin(np.where(used[i], np.inf, abs(residual))))
        if abs(residual[j]) <= 850:
            value = prediction + residual[j]
            path.append((i, j, value))
            t, f = np.append(t, times[i]), np.append(f, value)
    return path, t, f


def shape(key, times, frequency):
    span = times[-1] - times[0]
    if len(times) < 18 or span < 12:
        return None
    center = (times[0] + times[-1]) / 2
    x = (times - center) / (span / 2)
    design = np.polynomial.legendre.legvander(x, 3)
    coefficient = np.linalg.lstsq(design, frequency, rcond=None)[0]
    noise = float(np.sqrt(np.mean((frequency - design @ coefficient) ** 2)))
    affine = design[:, :2]
    centered = frequency - affine @ np.linalg.lstsq(affine, frequency, rcond=None)[0]
    curvature = float(np.sqrt(np.mean(centered**2)))
    if noise > 250 or curvature < 140:
        return None
    return Segment(
        *key,
        len(times),
        center + SHAPE_TIMES * (span / 2),
        np.polynomial.legendre.legval(SHAPE_TIMES, coefficient),
        curvature,
        noise,
    )


def tracklets(capture):
    result = []
    for key, rows in sorted(peaks(capture).items()):
        rows.sort(key=lambda row: row[0])
        times = np.array([r[0] for r in rows])
        frequency = [r[1] for r in rows]
        used = [np.zeros(len(r), dtype=bool) for r in frequency]
        for i in range(max(0, len(rows) - 17)):
            for j in np.flatnonzero(~used[i]):
                possible = []
                for seed in successive_seeds(times, frequency, used, i, j):
                    path, t, f = extend(times, frequency, used, seed)
                    if candidate := shape(key, t, f):
                        possible.append((candidate, path))
                if possible:
                    best, path = max(possible, key=lambda p: (p[0].points, -p[0].noise_hz))
                    result.append(best)
                    for visit, peak, _ in path:
                        used[visit][peak] = True
    return sorted(result, key=lambda t: -t.curvature_hz / max(75, t.noise_hz))[:28]


@dataclass
class Sky:
    ids: np.ndarray
    rf: np.ndarray
    measured: np.ndarray
    positions: np.ndarray
    velocities: np.ndarray

    def evaluate(self, site, *, detail=False):
        up = ecef_to_enu_matrix(*site)[2]
        receiver = geodetic_to_ecef_km(*site, 0.0)
        mid = self.positions[:, :, MID]
        projected = np.einsum("tsi,i->ts", mid, up) - receiver @ up
        i, j = np.where(projected > 0)
        if not len(i):
            if detail:
                empty = np.empty(0)
                return i, j, empty, empty
            return np.full(len(self.rf), np.inf)
        dx = self.positions[i, j] - receiver
        ranges = np.linalg.norm(dx, axis=2)
        ok = projected[i, j] > np.sin(np.deg2rad(5)) * ranges[:, MID]
        i, j = i[ok], j[ok]
        rate = np.einsum("nti,nti->nt", dx[ok], self.velocities[i, j]) / ranges[ok]
        modeled = -self.rf[i, None] / LIGHT_KM_S * rate
        residual = self.measured[i] - modeled
        offsets = residual.mean(axis=1)
        costs = np.sqrt(np.mean((residual - offsets[:, None]) ** 2, axis=1))
        if detail:
            return i, j, costs, wrap(offsets)
        best = np.full(len(self.rf), np.inf)
        np.minimum.at(best, i, costs)
        return best


def prepare_sky(capture, segments):
    catalog = parse_element_sets(capture.catalog.decode("ascii"))
    selected = [
        i
        for i, epoch in enumerate(catalog.element_epoch_utc_ns())
        if epoch <= capture.cutoff_utc_ns
    ]
    if not selected:
        raise ValueError("catalogue has no elements causal at the hardware clock cutoff")
    t = np.stack([row.times for row in segments])
    utc = capture.anchor_utc_ns + np.rint(t.reshape(-1) * 1e9).astype(np.int64)
    jd, fraction = julian_day_from_utc_ns(utc)
    errors, p, v = SatrecArray([catalog.satellites[i] for i in selected]).sgp4(jd, fraction)
    valid = np.all(errors == 0, axis=1) & np.all(np.linalg.norm(p, axis=2) > EARTH_KM + 120, axis=1)
    p, v = teme_to_ecef(p[valid], v[valid], greenwich_mean_sidereal_time_rad(jd, fraction))
    n = int(valid.sum())

    def layout(raw):
        return np.ascontiguousarray(raw.reshape(n, *t.shape, 3).transpose(1, 0, 2, 3))

    return Sky(
        np.asarray(catalog.satellite_numbers)[np.array(selected)[valid]],
        np.array([row.rf_hz for row in segments]),
        np.stack([row.frequency for row in segments]),
        layout(p),
        layout(v),
    )


def spherical_grid(count=1536):
    index = np.arange(count)
    return np.column_stack(
        (
            np.rad2deg(np.arcsin(2 * (index + 0.5) / count - 1)),
            np.rad2deg((index * GOLDEN_ANGLE + np.pi) % (2 * np.pi) - np.pi),
        )
    )


def offset_site(site, east, north):
    axes = ecef_to_enu_matrix(*site)
    unit = axes[2] + (axes[0] * east + axes[1] * north) / EARTH_KM
    return np.array(
        [
            np.rad2deg(np.arctan2(unit[2], np.hypot(*unit[:2]))),
            np.rad2deg(np.arctan2(unit[1], unit[0])),
        ]
    )


def separation(a, b):
    u, v = (ecef_to_enu_matrix(*p)[2] for p in (a, b))
    return EARTH_KM * 2 * np.arcsin(min(1, np.linalg.norm(u - v) / 2))


def consensus(sky, sites, sigma, keep, gap):
    scored = [
        (float(np.sum(np.exp(-0.5 * (sky.evaluate(point) / sigma) ** 2))), point) for point in sites
    ]
    ordered = sorted(scored, key=lambda item: item[0], reverse=True)
    retained = []
    for score, point in ordered:
        if all(separation(point, other) > gap for _, other in retained):
            retained.append((score, point))
        if len(retained) == keep:
            break
    return retained


def choose_sites(sky, tile):
    def mesh(points, step):
        return (
            offset_site(p, step * e, step * n)
            for p in points
            for e, n in product(range(-2, 3), repeat=2)
        )

    if tile is None:
        coarse = consensus(sky, spherical_grid(), 3000, 12, 650)
        best = []
        for score, point in coarse:
            for step, width in ((100, 1500), (25, 650), (6, 300), (1.5, 180)):
                ((score, point),) = consensus(sky, mesh([point], step), width, 1, 0)
            best.append((score, point))
        best.sort(key=lambda row: row[0], reverse=True)
        other = next((s for s, p in best[1:] if separation(p, best[0][1]) > 250), None)
        return best[0], other
    center, radius = tile["center"], tile["width_km"] / 2
    offsets = np.linspace(-radius, radius, 1 + int(np.ceil(2 * radius / 3)))
    sites = (offset_site(center, e, n) for e, n in product(offsets, repeat=2))
    best = consensus(sky, sites, 300, 4, 6)
    for step in (1.5, 0.35):
        nearby = (
            p
            for p in mesh([p for _, p in best], step)
            if all(abs(v) <= radius for v in local_xy(center, p))
        )
        best = consensus(sky, nearby, 180, 4, step * 2)
    return best[0], None


def local_xy(center, point):
    axes = ecef_to_enu_matrix(*center)
    rho = axes @ ecef_to_enu_matrix(*point)[2]
    return EARTH_KM * rho[:2] / rho[2]


def assignments(sky, segments, site):
    tracks, sats, cost, offset = sky.evaluate(site, detail=True)
    options = []
    for i in range(len(segments)):
        pairs = np.flatnonzero(tracks == i)
        best = pairs[np.argsort(cost[pairs], kind="stable")[:4]]
        options.append(best[cost[best] <= 950])
    selected = {}
    for group in range(4):
        rows = [i for i, t in enumerate(segments) if t.group == group and len(options[i])]
        if not rows:
            continue
        biases = np.concatenate([offset[options[i]] for i in rows])
        weights = np.exp(-0.5 * (cost / 300) ** 2)
        scores = np.zeros(len(biases))
        for i in rows:
            take = options[i]
            delta = wrap(biases[:, None] - offset[take])
            scores += np.max(np.exp(-0.5 * (delta / 5000) ** 2) * weights[take], axis=1)
        bias = biases[np.argmax(scores)]
        for i in rows:
            take = options[i]
            delta = wrap(offset[take] - bias)
            chosen = np.argmin((cost[take] / 300) ** 2 + (delta / 5000) ** 2)
            if abs(delta[chosen]) <= 15000:
                chosen = take[chosen]
                selected[i] = int(sats[chosen]), float(cost[chosen]), float(bias)
    return selected


def fit(sky, segments, selected, site, tile, fitted):
    i = np.array(sorted(selected))
    j = np.array([selected[k][0] for k in i])
    bias = np.array([selected[k][2] for k in i])
    p, v = sky.positions[i, j], sky.velocities[i, j]
    rf = sky.rf[i, None]
    group = np.array([segments[k].group for k in i])
    time = (np.stack([segments[k].times for k in i]) - 150) / 150
    search_center, radius = (site, 10.0) if tile is None else (tile["center"], tile["width_km"] / 2)

    def model(position):
        rx = geodetic_to_ecef_km(*offset_site(search_center, *position), 0.0)
        delta = p - rx
        rate = np.einsum("tki,tki->tk", delta, v) / np.linalg.norm(delta, axis=2)
        return -rf / LIGHT_KM_S * rate

    initial_xy = np.clip(local_xy(search_center, site), -radius, radius)
    observed = sky.measured[i].copy()
    level = (observed - model(initial_xy)).mean(axis=1)
    observed -= PERIOD_HZ * np.rint((level - bias) / PERIOD_HZ)[:, None]
    start_bias = np.array(
        [np.median(bias[group == g]) if np.any(group == g) else 0 for g in range(4)]
    )
    start = np.r_[initial_xy, start_bias / 1000, np.zeros(4), np.zeros(int(fitted))]

    def residual(x, prior=True):
        correction = 1000 * x[2:6][group, None] + 100 * x[6:10][group, None] * time
        if fitted:
            correction = correction + 20_000 * x[10] * (rf / 1e9 - 11.5)
        r = (observed - model(x[:2]) - correction).reshape(-1)
        return np.r_[r, 300 * x[6:]] if prior else r

    limits = np.r_[
        radius, radius, np.repeat(PERIOD_HZ / 1000, 4), np.repeat(8, 4), np.repeat(5, int(fitted))
    ]
    outcome = least_squares(
        residual, start, bounds=(-limits, limits), loss="soft_l1", f_scale=300, max_nfev=48
    )
    r = residual(outcome.x, prior=False)
    return dict(
        forced_latlon=offset_site(search_center, *outcome.x[:2]).tolist(),
        conditional_rms_hz=float(np.sqrt(np.mean(r**2))),
        fit_score=float(outcome.cost),
        fitted_c_hz_per_ghz=float(outcome.x[10] * 20_000) if fitted else 0.0,
        nfev=outcome.nfev,
    )


def run(capture, *, tile=None):
    begin = perf_counter()
    segments = tracklets(capture)
    extracted = perf_counter()
    metrics = dict(
        stage_s={"tracklets": extracted - begin},
        tracks=len(segments),
        native_probes=len(capture.probes),
        track_points=sum(t.points for t in segments),
        track_channels=sorted({t.channel for t in segments}),
    )
    arms = {a: {"latlon": None, "forced_latlon": None} for a in ARMS}

    def result(reason=None):
        return dict(
            status="withheld" if reason else "ok",
            arms=arms,
            metrics=metrics,
            boundary="Native GLRT candidates and causal catalogue to sparse triplet position",
            **({"reason": reason} if reason else {}),
        )

    if len(segments) < 4:
        return result("fewer than four qualifying independent lane segments")
    sky = prepare_sky(capture, segments)
    propagated = perf_counter()
    (vote, site), other = choose_sites(sky, tile)
    searched = perf_counter()
    selected = assignments(sky, segments, site)
    metrics.update(
        shape_latlon=site.tolist(),
        selected_catalogue_size=len(sky.ids),
        shape_vote=vote,
        alternate_shape_vote=other,
        selected_tracks=len(selected),
        selected_orbits=sorted({int(sky.ids[j]) for j, _, _ in selected.values()}),
        selected_channels=sorted({segments[i].channel for i in selected}),
    )
    metrics["stage_s"].update(propagate=propagated - extracted, search=searched - propagated)
    if not selected:
        for arm in arms.values():
            arm["forced_latlon"] = site.tolist()
        return result("no matching catalogue shapes")
    metrics["median_centered_shape_rms_hz"] = float(np.median([c for _, c, _ in selected.values()]))
    credible = (
        len(metrics["selected_orbits"]) >= 4
        and len(metrics["selected_channels"]) >= 2
        and metrics["median_centered_shape_rms_hz"] <= 300
        and (tile is not None or other is None or vote - other >= 1.5)
    )
    for arm in ARMS:
        arms[arm].update(fit(sky, segments, selected, site, tile, arm == "fitted_c"))
        if credible and arms[arm]["conditional_rms_hz"] <= 1200:
            arms[arm]["latlon"] = arms[arm]["forced_latlon"]
            arms[arm]["rf_rms_hz"] = arms[arm]["conditional_rms_hz"]
    metrics["stage_s"]["fit"] = perf_counter() - searched
    return result(
        None
        if any(a["latlon"] is not None for a in arms.values())
        else "the frequency or spatial consistency gates withheld the forced endpoint"
    )
