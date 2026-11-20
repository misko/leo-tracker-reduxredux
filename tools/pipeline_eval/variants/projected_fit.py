"""Robust, continuous position fit to time-varying anonymous-track Doppler.

The observation and causal TLE catalogue are the input boundary. Each fixed-RF
track has an unknown constant CFO (including any whole-track alias). Removing
its mean also removes c times RF, so c is unidentifiable. The two reported arms
therefore share the same fit and projected shape residual.
"""

import json
import math
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from time import perf_counter

import numpy as np

from leo.sky.frames import (
    WGS84_ECCENTRICITY_SQUARED,
    WGS84_FLATTENING,
    WGS84_SEMI_MAJOR_AXIS_KM,
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import SamplingGrid

BOUNDARY = "portable anonymous tracks and causal TLE catalogue to position decision"
HALF_WIDTH_KM = 12.5
LIGHT_KM_S = 299_792.458
PHASE_SIGMA_S = 2.0
SHAPE_SIGMA_HZ = 180.0
ORBIT_KNOT_S = 10
TLE_AGE_NS = 48 * 3_600 * 10**9
TRACK_LIMIT = 64
SAMPLE_LIMIT = 24
MIN_SPLIT_ORBITS = 3
MIN_POOLED_ORBITS = 5
MIN_SCORE = 0.25
MIN_LEAD = 0.025
MIN_EDGE_CLEARANCE_KM = 1.0
MAX_SPLIT_DISTANCE_KM = 5.0
MAX_POOLED_DISPLACEMENT_KM = 4.0
MAX_INFORMATION_RADIUS_KM = 5.0
WGS84_POLAR_KM = WGS84_SEMI_MAJOR_AXIS_KM * (1.0 - WGS84_FLATTENING)
_SEEDS = ((0.0, 0.0), *product((-6.25, 6.25), repeat=2))


@dataclass(frozen=True)
class Track:
    seconds: np.ndarray
    cfo_hz: np.ndarray
    rf_hz: float


@dataclass(frozen=True)
class OrbitBank:
    numbers: np.ndarray
    knot_numbers: np.ndarray
    positions_km: np.ndarray
    velocities_km_s: np.ndarray
    propagated_states: int

    def sample(self, track, visible):
        scaled = track.seconds / ORBIT_KNOT_S
        knot = scaled.astype(np.int64)
        left = np.searchsorted(self.knot_numbers, knot)
        right = np.searchsorted(self.knot_numbers, knot + 1)
        candidates = np.flatnonzero(visible[:, left].all(axis=1) & visible[:, right].all(axis=1))
        index = candidates[:, None]
        p0, p1 = self.positions_km[index, left], self.positions_km[index, right]
        v0, v1 = self.velocities_km_s[index, left], self.velocities_km_s[index, right]
        u = (scaled - knot)[None, :, None]
        step = ORBIT_KNOT_S
        distance = p1 - p0 - step * v0
        speed = step * (v1 - v0)
        quadratic, cubic = 3 * distance - speed, speed - 2 * distance
        position = p0 + u * (step * v0 + u * (quadratic + u * cubic))
        velocity = v0 + u * (2 * quadratic + 3 * u * cubic) / step
        acceleration = (2 * quadratic + 6 * u * cubic) / step**2
        return Arc(track, self.numbers[candidates], position, velocity, acceleration)


@dataclass(frozen=True)
class Arc:
    track: Track
    orbits: np.ndarray
    positions_km: np.ndarray
    velocities_km_s: np.ndarray
    accelerations_km_s2: np.ndarray


@dataclass(frozen=True)
class Region:
    name: str
    center: tuple[float, float]
    origin: np.ndarray
    frame: np.ndarray

    def site(self, xy):
        tangent = self.origin + xy @ self.frame[:2]
        x, y, z = tangent
        radial = np.hypot(x, y)
        a, b, e2 = WGS84_SEMI_MAJOR_AXIS_KM, WGS84_POLAR_KM, WGS84_ECCENTRICITY_SQUARED
        theta = np.arctan2(a * z, b * radial)
        latitude = np.arctan2(
            z + e2 / (1.0 - e2) * b * np.sin(theta) ** 3,
            radial - e2 * a * np.cos(theta) ** 3,
        )
        latlon = np.rad2deg([latitude, np.arctan2(y, x)])
        return geodetic_to_ecef_km(*latlon, 0.0), latlon.tolist()


@dataclass(frozen=True)
class Factors:
    """Per-candidate quadratic loss after eliminating the constant and phase shift."""

    base: np.ndarray
    gradient: np.ndarray
    hessian: np.ndarray
    orbits: np.ndarray
    phase_intercept: np.ndarray
    phase_gradient: np.ndarray

    def evaluate(self, xy, rows):
        base, gradient, hessian = self.base[rows], self.gradient[rows], self.hessian[rows]
        slope = gradient + hessian @ xy
        costs = np.maximum(base + (slope + gradient) @ xy, 0.0)
        column = costs.argmin(axis=1)
        index = (np.arange(len(column)), column)
        loss = costs[index]
        quality = 1.0 / (1.0 + loss)
        phase = self.phase_intercept[rows][index] + self.phase_gradient[rows][index] @ xy
        return Match(loss, quality, self.orbits[rows][index], slope[index], hessian[index], phase)


@dataclass(frozen=True)
class Match:
    loss: np.ndarray
    quality: np.ndarray
    orbit: np.ndarray
    gradient: np.ndarray
    hessian: np.ndarray
    phase_s: np.ndarray

    @property
    def score(self):
        return float(self.quality.mean())

    def independent(self):
        by_orbit = {}
        for index in np.argsort(-self.quality, kind="stable"):
            if self.orbit[index] >= 0 and self.loss[index] <= 9.0:
                by_orbit.setdefault(self.orbit[index], index)
        return np.fromiter(by_orbit.values(), dtype=int)


def _regions(records):
    regions = {}
    for record in records:
        name = record["id"]
        lat, lon = map(float, record["center"])
        if not isinstance(name, str) or not -90 <= lat <= 90 or not math.isfinite(lon):
            raise ValueError("invalid region")
        center = (lat, (lon + 180.0) % 360.0 - 180.0)
        if name in regions and regions[name].center != center:
            raise ValueError("region ID has multiple centers")
        regions[name] = Region(
            name,
            center,
            geodetic_to_ecef_km(*center, 0.0),
            ecef_to_enu_matrix(*center),
        )
    return sorted(regions.values(), key=lambda region: (region.center, region.name))


def _tracks(observation):
    duration = float(observation["duration_s"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid observation duration")
    records = {}
    for record in observation["tracks"]:
        try:
            times = np.asarray(record["times"], dtype=float)
            values = np.asarray(record["values"], dtype=float)
            rf = float(record["rf_hz"])
            if times.ndim != 1 or times.shape != values.shape or len(times) < 4:
                continue
            order = np.argsort(times, kind="stable")
            times, values = times[order], values[order]
            if (
                not 0 <= times[0] < times[-1] <= duration
                or not np.all(np.diff(times) > 0)
                or not np.isfinite(values).all()
                or not math.isfinite(rf)
                or rf <= 0
            ):
                continue
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        values = values - values[0]
        key = (-float(np.ptp(times)), tuple(times), rf, tuple(values))
        sample = np.rint(np.linspace(0, len(times) - 1, min(len(times), SAMPLE_LIMIT))).astype(int)
        records[key] = Track(times[sample], values[sample], rf)
    retained = [records[key] for key in sorted(records)[:TRACK_LIMIT]]
    return sorted(retained, key=lambda track: float(np.mean(track.seconds[[0, -1]])))


def _orbits(observation, tle_text, tracks):
    anchor = int(observation["anchor_utc_ns"])
    cutoff = int(observation["cutoff_utc_ns"])
    snapshot = int(observation["catalog_timestamp_ns"])
    if anchor <= 0 or not 0 < snapshot <= cutoff:
        raise ValueError("invalid or noncausal observation time metadata")
    catalogue = parse_element_sets(tle_text)
    latest = {}
    for index, (number, epoch) in enumerate(
        zip(catalogue.satellite_numbers, catalogue.element_epoch_utc_ns(), strict=True)
    ):
        if cutoff - TLE_AGE_NS <= epoch <= snapshot and (
            number not in latest or epoch > latest[number][0]
        ):
            latest[number] = (epoch, index)
    numbers = np.asarray(sorted(latest), dtype=int)
    indices = [latest[number][1] for number in numbers]
    left = np.floor(np.concatenate([track.seconds for track in tracks]) / ORBIT_KNOT_S)
    knots = np.unique(np.r_[0, 1, 2, left, left + 1]).astype(np.int64)
    utc_ns = tuple(anchor + int(knot) * ORBIT_KNOT_S * 10**9 for knot in knots)
    jd, fraction = julian_day_from_utc_ns(utc_ns)
    orbit = propagate_grid(catalogue, SamplingGrid(utc_ns, 0, ORBIT_KNOT_S), indices)
    position, velocity = orbit.position_teme_km, orbit.velocity_teme_km_s
    valid = (
        (orbit.error_code == 0).all(axis=1)
        & np.isfinite(position).all(axis=(1, 2))
        & np.isfinite(velocity).all(axis=(1, 2))
        & (np.linalg.norm(position, axis=-1) >= WGS84_POLAR_KM + MINIMUM_PLAUSIBLE_ALTITUDE_KM).all(
            axis=1
        )
    )
    position, velocity = teme_to_ecef(
        position[valid],
        velocity[valid],
        greenwich_mean_sidereal_time_rad(jd, fraction),
    )
    return OrbitBank(numbers[valid], knots, position, velocity, len(indices) * len(knots))


def _arcs(bank, region, tracks):
    delta = bank.positions_km - region.origin
    # The horizon slack covers the tile and motion between nearby knots.
    visible = delta @ region.frame[2] >= -0.10 * np.linalg.norm(delta, axis=-1)
    return [bank.sample(track, visible) for track in tracks]


def _center(values):
    return values - values.mean(axis=1, keepdims=True)


def _linearize(arcs, region, xy):
    station, _ = region.site(xy)
    shape = (len(arcs), max(1, max(len(arc.orbits) for arc in arcs)))
    base = np.full(shape, np.inf)
    gradient, hessian = np.zeros((*shape, 2)), np.zeros((*shape, 2, 2))
    orbits = np.full(shape, -1, dtype=int)
    phase_intercept, phase_gradient = np.zeros(shape), np.zeros((*shape, 2))
    for index, arc in enumerate(arcs):
        delta = arc.positions_km - station
        visible = (delta @ region.frame[2] >= 0.0).all(axis=1)
        if not visible.any():
            continue
        good = (index, np.flatnonzero(visible))
        delta = delta[visible]
        distance = np.linalg.norm(delta, axis=-1)
        ray = delta / distance[..., None]
        velocity, acceleration = arc.velocities_km_s[visible], arc.accelerations_km_s2[visible]
        radial_speed = np.einsum("...i,...i->...", velocity, ray)
        transverse = velocity - radial_speed[..., None] * ray
        radial_acceleration = (
            np.einsum("...i,...i->...", acceleration, ray)
            + np.einsum("...i,...i->...", transverse, transverse) / distance
        )
        scale = arc.track.rf_hz / (LIGHT_KM_S * SHAPE_SIGMA_HZ)
        design = _center(scale * (transverse @ region.frame[:2].T) / distance[..., None])
        phase = _center(-scale * radial_acceleration)
        residual = _center(arc.track.cfo_hz / SHAPE_SIGMA_HZ + scale * radial_speed) + design @ xy
        sample_count = len(arc.track.seconds)
        phase_energy = np.mean(phase**2, axis=1) + 1.0 / PHASE_SIGMA_S**2
        phase_cross = np.mean(phase * residual, axis=1)
        phase_design = np.mean(phase[..., None] * design, axis=1)
        # The Schur complement profiles a Gaussian-regularized phase shift.
        base[good] = np.mean(residual**2, axis=1) - phase_cross**2 / phase_energy
        phase_intercept[good] = phase_cross / phase_energy
        phase_gradient[good] = -phase_design / phase_energy[:, None]
        gradient[good] = (
            -np.mean(design * residual[..., None], axis=1)
            + phase_design * phase_intercept[good][:, None]
        )
        hessian[good] = (
            design.transpose(0, 2, 1) @ design / sample_count
            + phase_design[..., None] * phase_gradient[good][:, None, :]
        )
        orbits[good] = arc.orbits[visible]
    return Factors(base, gradient, hessian, orbits, phase_intercept, phase_gradient)


def _bounded_step(xy, gradient, normal):
    new = xy - np.linalg.solve(normal, gradient)
    if np.max(np.abs(new)) <= HALF_WIDTH_KM:
        return new - xy
    steps = []
    for fixed in range(2):
        free = 1 - fixed
        for edge in (-HALF_WIDTH_KM, HALF_WIDTH_KM):
            step = np.zeros(2)
            step[fixed] = edge - xy[fixed]
            move = -(gradient[free] + normal[free, fixed] * step[fixed]) / normal[free, free]
            step[free] = np.clip(xy[free] + move, -HALF_WIDTH_KM, HALF_WIDTH_KM) - xy[free]
            steps.append(step)
    return min(steps, key=lambda step: float(step @ (gradient + 0.5 * normal @ step)))


def _fit(factors, rows, seeds):
    best_point, best_match = None, None
    for seed in seeds:
        xy = np.asarray(seed, dtype=float)
        match = factors.evaluate(xy, rows)
        for _ in range(12):
            weight = match.quality**2
            gradient = weight @ match.gradient
            normal = np.einsum("t,tij->ij", weight, match.hessian) + np.eye(2) * 1e-10
            step = _bounded_step(xy, gradient, normal)
            if np.linalg.norm(step) <= 1e-3:
                break
            for _ in range(6):
                probe = np.clip(xy + step, -HALF_WIDTH_KM, HALF_WIDTH_KM)
                tested = factors.evaluate(probe, rows)
                if tested.score > match.score:
                    xy, match = probe, tested
                    break
                step *= 0.5
            else:
                break
        if best_match is None or match.score > best_match.score:
            best_point, best_match = xy, match
    return best_point, best_match


def _decision(regions, tracks, bank):
    early = np.arange(len(tracks) // 2)
    late = np.arange(len(early), len(tracks))
    pooled = np.arange(len(tracks))
    nominees = []
    pair_counts = 0
    for region in regions:
        arcs = _arcs(bank, region, tracks)
        factors = _linearize(arcs, region, np.zeros(2))
        if not np.any(factors.orbits >= 0):
            continue
        pair_counts += int(np.count_nonzero(factors.orbits >= 0))
        first, _ = _fit(factors, early, _SEEDS)
        second, _ = _fit(factors, late, _SEEDS)
        held_late, held_early = factors.evaluate(first, late), factors.evaluate(second, early)
        score = (held_late.score + held_early.score) / 2.0
        held_orbits = min(len(held_late.independent()), len(held_early.independent()))
        nominees.append((score, region, first, second, held_orbits))
    diagnostics = dict(tiles=len(regions), candidate_pairs=pair_counts)
    if not nominees:
        return None, None, None, "no_visible_candidates", diagnostics
    nominees.sort(key=lambda nominee: -nominee[0])
    score, region, first, second, held_orbits = nominees[0]
    arcs = _arcs(bank, region, tracks)
    factors = _linearize(arcs, region, np.zeros(2))
    xy, _ = _fit(factors, pooled, (*_SEEDS, first, second))
    for _ in range(2):
        factors = _linearize(arcs, region, xy)
        xy, _ = _fit(factors, pooled, (xy,))
    match = _linearize(arcs, region, xy).evaluate(xy, pooled)
    independent = match.independent()
    minimum = np.linalg.eigvalsh(match.hessian[independent].sum(axis=0))[0]
    radius = float(np.sqrt(5.991 / minimum)) if minimum > 1e-12 else None
    rf_rms = None
    support = (match.orbit >= 0) & (match.loss <= 9.0)
    if support.any():
        residual = match.loss[support] - (match.phase_s[support] / PHASE_SIGMA_S) ** 2
        rf_rms = float(SHAPE_SIGMA_HZ * np.sqrt(np.maximum(residual, 0.0).mean()))
    lead = float(score - nominees[1][0]) if len(nominees) > 1 else None
    split = float(np.linalg.norm(first - second))
    displacement = max(float(np.linalg.norm(xy - split_xy)) for split_xy in (first, second))
    clearance = float(HALF_WIDTH_KM - np.max(np.abs(xy)))
    diagnostics.update(
        cross_score=score,
        region_lead=lead,
        held_orbits=held_orbits,
        pooled_orbits=len(independent),
        information_radius_km=radius,
        split_distance_km=split,
        pooled_displacement_km=displacement,
        edge_clearance_km=clearance,
    )
    reason = None
    if len(independent) < MIN_POOLED_ORBITS or held_orbits < MIN_SPLIT_ORBITS or score < MIN_SCORE:
        reason = "weak_held_track_evidence"
    elif lead is not None and lead <= MIN_LEAD:
        reason = "ambiguous_region"
    elif clearance <= MIN_EDGE_CLEARANCE_KM:
        reason = "position_at_tile_boundary"
    elif split > MAX_SPLIT_DISTANCE_KM or displacement > MAX_POOLED_DISPLACEMENT_KM:
        reason = "inconsistent_disjoint_fits"
    elif radius is None or radius > MAX_INFORMATION_RADIUS_KM:
        reason = "weak_projected_geometry"
    return region.name, region.site(xy)[1], rf_rms, reason, diagnostics


def run(case: dict, work_dir: Path) -> dict:
    """Run one inference using only the public case fields."""
    started = perf_counter()
    base = dict(boundary=BOUNDARY, metrics={"calibration_invariant": True})
    empty_arms = {"c0": {"latlon": None}, "fitted_c": {"latlon": None}}
    try:
        paths = [case.get("observation_path"), case.get("catalog_path")]
        if any(not path or not Path(path).is_file() for path in paths):
            return dict(
                base,
                status="unavailable",
                arms=empty_arms,
                reason="portable observation and causal catalogue are required",
            )
        observation = json.loads(Path(paths[0]).read_text())
        tracks = _tracks(observation)
        regions = _regions(case["regions"])
        metrics = base["metrics"]
        metrics.update(tracks=len(tracks), samples=sum(len(track.seconds) for track in tracks))
        if len(tracks) < 2 * MIN_SPLIT_ORBITS or not regions:
            return dict(
                base,
                status="withheld",
                arms=empty_arms,
                reason="insufficient_independent_tracks_or_offers",
            )
        bank = _orbits(observation, Path(paths[1]).read_text(), tracks)
        metrics.update(propagated_states=bank.propagated_states)
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as error:
        return dict(base, status="unavailable", arms=empty_arms, reason=str(error))
    name, point, rf_rms, reason, diagnostics = _decision(regions, tracks, bank)
    metrics.update(diagnostics, candidate_s=perf_counter() - started)
    arm = dict(latlon=point if reason is None else None)
    if reason is not None and point is not None:
        arm["forced_latlon"] = point
    if reason is None:
        arm["region_id"] = name
    if rf_rms is not None:
        arm["rf_rms_hz"] = rf_rms
    result = dict(
        base, status="ok" if reason is None else "withheld", arms={"c0": arm, "fitted_c": dict(arm)}
    )
    if reason is not None:
        result["reason"] = reason
    return result
