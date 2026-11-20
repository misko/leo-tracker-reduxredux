"""Position from the shape of anonymous CFO tracks and a supplied TLE snapshot."""

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import product

import numpy as np
from sgp4.api import Satrec, SatrecArray

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
from leo.sky.propagation import MINIMUM_PLAUSIBLE_ALTITUDE_KM, parse_element_sets

HALF_WIDTH_KM = 12.5
COARSE_STEPS = 7
MAX_CANDIDATES = 12
SAMPLES_PER_TRACK = 12
MIN_SUPPORT = 4
SHAPE_SD_HZ = 180.0
PHASE_SD_S = 2.0
PHASE_LIMIT_S = 8.0
COARSE_ORBIT_STEP_S = 20.0
FINE_ORBIT_STEP_S = 5.0
MAX_TLE_AGE_NS = 48 * 3600 * 10**9
LIGHT_SPEED_KM_S = 299792.458
_POLAR_RADIUS_KM = WGS84_SEMI_MAJOR_AXIS_KM * (1.0 - WGS84_FLATTENING)


@dataclass(frozen=True)
class SkyContext:
    """Site-independent, prefiltered coarse satellite states for one observation."""

    anchor_utc_ns: int
    duration_s: float
    satellites: tuple[Satrec, ...]
    positions_km: np.ndarray
    stats: dict[str, int]


@dataclass(frozen=True)
class Tile:
    """Regional position frame and fine ECEF state table for horizon candidates."""

    ecef_center_km: np.ndarray
    enu_frame: np.ndarray
    duration_s: float
    knots_s: np.ndarray
    positions_km: np.ndarray
    velocities_km_s: np.ndarray
    stats: dict[str, int]


@dataclass(frozen=True)
class _TrackArc:
    observed_hz: np.ndarray
    positions_km: np.ndarray
    velocities_km_s: np.ndarray
    accelerations_km_s2: np.ndarray
    rf_hz: float


def _field(record, name):
    return record[name] if isinstance(record, Mapping) else getattr(record, name)


def _knots(duration_s, step):
    start = -PHASE_LIMIT_S
    intervals = int(np.ceil((duration_s + 2 * PHASE_LIMIT_S) / step))
    return start + step * np.arange(intervals + 1)


def _valid_states(satellites, anchor, knots):
    if not satellites:
        empty = np.empty((0, len(knots), 3))
        return (), empty, empty.copy()
    julian, fraction = julian_day_from_utc_ns(anchor + np.rint(knots * 1e9).astype(np.int64))
    error, position, velocity = SatrecArray(satellites).sgp4(julian, fraction)
    minimum_radius = _POLAR_RADIUS_KM + MINIMUM_PLAUSIBLE_ALTITUDE_KM
    valid = (error == 0).all(axis=1)
    valid &= np.isfinite(position).all(axis=(1, 2)) & np.isfinite(velocity).all(axis=(1, 2))
    valid &= (np.linalg.norm(position, axis=-1) >= minimum_radius).all(axis=1)
    position, velocity = teme_to_ecef(
        position[valid], velocity[valid], greenwich_mean_sidereal_time_rad(julian, fraction)
    )
    return tuple(sat for sat, ok in zip(satellites, valid, strict=True) if ok), position, velocity


def prepare_sky(observation, tle_text):
    """Build a causal, location-independent context from TLE text or UTF-8 bytes."""
    anchor = int(_field(observation, "anchor_utc_ns"))
    cutoff = int(_field(observation, "cutoff_utc_ns"))
    snapshot = int(_field(observation, "catalog_timestamp_ns"))
    duration = float(_field(observation, "duration_s"))
    if snapshot > cutoff:
        raise ValueError("catalog timestamp is after the observation cutoff")
    if not np.isfinite(duration) or duration <= 0.0:
        raise ValueError("observation duration must be finite and positive")
    text = tle_text.decode("utf-8") if isinstance(tle_text, bytes) else tle_text
    catalogue = parse_element_sets(text)
    by_id = {}
    for sat, epoch in zip(catalogue.satellites, catalogue.element_epoch_utc_ns(), strict=True):
        if cutoff - MAX_TLE_AGE_NS <= epoch <= snapshot:
            previous = by_id.get(sat.satnum)
            if previous is None or epoch > previous[0]:
                by_id[sat.satnum] = (epoch, sat)
    causal = tuple(by_id[number][1] for number in sorted(by_id))
    knots = _knots(duration, COARSE_ORBIT_STEP_S)
    satellites, position, _ = _valid_states(causal, anchor, knots)
    stats = dict(
        catalog_entries=len(catalogue), causal_satellites=len(causal),
        coarse_satellites=len(satellites), coarse_knots=len(knots),
        coarse_state_evaluations=len(causal) * len(knots),
    )
    return SkyContext(anchor, duration, satellites, position, stats)


def make_tile(context, center_latlon):
    """Screen the supplied catalogue and build a 25 km WGS84 sea-level tile."""
    latitude, longitude = np.asarray(center_latlon, dtype=float)
    if not np.isfinite([latitude, longitude]).all() or abs(latitude) > 90:
        raise ValueError("tile center must have a finite longitude and latitude in [-90, 90]")
    origin = geodetic_to_ecef_km(latitude, longitude, 0.0)
    frame = ecef_to_enu_matrix(latitude, longitude)
    delta = context.positions_km - origin
    # Leave a horizon margin for gaps between coarse knots and offsets inside the tile.
    near_horizon = ((delta @ frame[2]) >= -0.08 * np.linalg.norm(delta, axis=-1)).any(axis=1)
    selected = tuple(
        sat for sat, keep in zip(context.satellites, near_horizon, strict=True) if keep
    )
    knots = _knots(context.duration_s, FINE_ORBIT_STEP_S)
    satellites, position, velocity = _valid_states(selected, context.anchor_utc_ns, knots)
    stats = dict(
        regional_satellites=len(selected), fine_satellites=len(satellites),
        fine_knots=len(knots), fine_state_evaluations=len(selected) * len(knots),
    )
    return Tile(origin, frame, context.duration_s, knots, position, velocity, stats)


def _sites(tile, xy):
    """Retract east/north tangent offsets onto WGS84 without a longitude singularity."""
    tangent = tile.ecef_center_km + xy @ tile.enu_frame[:2]
    x, y, z = tangent.T
    radial = np.hypot(x, y)
    e2 = WGS84_ECCENTRICITY_SQUARED
    a, b = WGS84_SEMI_MAJOR_AXIS_KM, _POLAR_RADIUS_KM
    theta = np.arctan2(a * z, b * radial)
    latitude = np.arctan2(z + e2 / (1.0 - e2) * b * np.sin(theta)**3,
                         radial - e2 * a * np.cos(theta)**3)
    longitude = np.arctan2(y, x)
    normal = np.column_stack((np.cos(latitude) * np.cos(longitude),
                              np.cos(latitude) * np.sin(longitude), np.sin(latitude)))
    lat_deg = np.rad2deg(latitude)
    lon_deg = (np.rad2deg(longitude) + 180.0) % 360.0 - 180.0
    ecef = geodetic_to_ecef_km(lat_deg, lon_deg, 0.0).T
    return ecef, normal, np.column_stack((lat_deg, lon_deg))


def _interpolated_states(tile, times):
    # Cubic Hermite interpolation keeps the position and Doppler derivatives consistent.
    step = FINE_ORBIT_STEP_S
    fractional = (times - tile.knots_s[0]) / step
    i = fractional.astype(int)
    u = (fractional - i)[None, :, None]
    p0, p1 = tile.positions_km[:, i], tile.positions_km[:, i + 1]
    v0, v1 = tile.velocities_km_s[:, i], tile.velocities_km_s[:, i + 1]
    movement = p1 - p0 - step * v0
    velocity_change = step * (v1 - v0)
    quadratic = 3 * movement - velocity_change
    cubic = velocity_change - 2 * movement
    position = p0 + u * (step * v0 + u * (quadratic + u * cubic))
    velocity = v0 + u * (2 * quadratic + 3 * u * cubic) / step
    acceleration = (2 * quadratic + 6 * u * cubic) / step**2
    return position, velocity, acceleration


def _centered(values):
    return values - values.mean(axis=-1, keepdims=True)


def _orbit_shape(arc, sites):
    delta = arc.positions_km[None, :, :, :] - sites[:, None, None, :]
    distance = np.linalg.norm(delta, axis=-1)
    ray = delta / distance[..., None]
    velocity = arc.velocities_km_s
    radial_velocity = np.einsum("...i,...i->...", ray, velocity)
    speed_squared = np.einsum("...i,...i->...", velocity, velocity)
    radial_accel = np.einsum("...i,...i->...", ray, arc.accelerations_km_s2)
    radial_accel += (speed_squared - radial_velocity**2) / distance
    scale = arc.rf_hz / LIGHT_SPEED_KM_S
    return -scale * radial_velocity, -scale * radial_accel, ray, distance


def _shape_loss(observed, modeled, derivative):
    # Profile an additive per-track CFO and a regularized per-candidate time shift.
    residual = observed - _centered(modeled)
    rate = _centered(derivative)
    residual_power = np.mean(residual**2, axis=-1)
    rate_power = np.mean(rate**2, axis=-1)
    cross = np.mean(residual * rate, axis=-1)
    phase = np.clip(cross / (rate_power + (SHAPE_SD_HZ / PHASE_SD_S)**2),
                    -PHASE_LIMIT_S, PHASE_LIMIT_S)
    power = np.maximum(residual_power - phase * (2 * cross - phase * rate_power), 0.0)
    return power / SHAPE_SD_HZ**2 + (phase / PHASE_SD_S)**2, power


def _track_arc(tile, track):
    times = np.asarray(_field(track, "times"), dtype=float)
    observed = np.asarray(_field(track, "values"), dtype=float)
    rf = float(_field(track, "rf_hz"))
    if (times.ndim != 1 or times.shape != observed.shape or len(times) < 4
            or not np.isfinite(times).all() or not np.isfinite(observed).all()
            or not np.isfinite(rf) or rf <= 0.0 or not (np.diff(times) > 0.0).all()
            or times[0] < -1e-6 or times[-1] > tile.duration_s + 1e-6):
        return None
    samples = min(len(times), SAMPLES_PER_TRACK)
    sampled = np.rint(np.linspace(0, len(times) - 1, samples)).astype(int)
    position, velocity, acceleration = _interpolated_states(tile, times[sampled])
    delta = position - tile.ecef_center_km
    # Keep horizon alternatives that could become visible anywhere inside this tile.
    visible = ((delta @ tile.enu_frame[2]) >= -0.02 * np.linalg.norm(delta, axis=-1)).all(axis=1)
    if not visible.any():
        return None
    observed = _centered(observed[sampled] - observed[sampled[0]])
    arc = _TrackArc(observed, position[visible], velocity[visible], acceleration[visible], rf)
    if len(arc.positions_km) <= MAX_CANDIDATES:
        return arc
    center, derivative, ray, distance = _orbit_shape(arc, tile.ecef_center_km[None, :])
    radial_velocity = -center[0] * LIGHT_SPEED_KM_S / rf
    velocity_on_sky = arc.velocities_km_s - radial_velocity[..., None] * ray[0]
    doppler_gradient = (rf / LIGHT_SPEED_KM_S) * (velocity_on_sky @ tile.enu_frame[:2].T)
    doppler_gradient /= distance[0, :, :, None]
    sentinels = np.array(list(product((-HALF_WIDTH_KM, 0.0, HALF_WIDTH_KM), repeat=2)))
    models = center + np.einsum("ksi,pi->pks", doppler_gradient, sentinels)
    loss, _ = _shape_loss(observed, models, derivative)
    keep = np.argsort(loss.min(axis=0), kind="stable")[:MAX_CANDIDATES]
    return _TrackArc(observed, arc.positions_km[keep], arc.velocities_km_s[keep],
                     arc.accelerations_km_s2[keep], rf)


def _evaluate(tile, arcs, n_tracks, points):
    sites, up, _ = _sites(tile, points)
    score = np.zeros(len(points))
    support = np.zeros(len(points), dtype=int)
    rss = np.zeros(len(points))
    index = np.arange(len(points))
    for arc in arcs:
        model, derivative, ray, _ = _orbit_shape(arc, sites)
        loss, mean_square = _shape_loss(arc.observed_hz, model, derivative)
        visible = (np.einsum("pksi,pi->pks", ray, up) >= 0.0).all(axis=-1)
        loss = np.where(visible, loss, np.inf)
        choice = np.argmin(loss, axis=1)
        selected = loss[index, choice]
        score += 1.0 / (1.0 + selected / 4.0)
        supported = selected <= 9.0
        support += supported
        rss += np.where(supported, mean_square[index, choice], 0.0)
    rms = np.sqrt(np.divide(rss, support, out=np.full(len(points), np.nan), where=support > 0))
    return score / max(n_tracks, 1), support, rms


def _metrics(scored, index):
    score, support, rms = scored
    return dict(score=float(score[index]), n_tracks=int(support[index]),
                rms_hz=float(rms[index]) if support[index] else None)


def _arcs(tile, tracks):
    tracks = tuple(tracks)
    arcs = [arc for track in tracks if (arc := _track_arc(tile, track)) is not None]
    return arcs, len(tracks)


def score_at(tile, tracks, xy):
    """Score fixed coordinates on verbatim tracks, counting missing tracks as zero."""
    point = np.asarray(xy, dtype=float)
    if point.shape != (2,) or not np.isfinite(point).all() or np.max(np.abs(point)) > HALF_WIDTH_KM:
        raise ValueError("xy must be two finite east/north coordinates inside this tile")
    arcs, count = _arcs(tile, tracks)
    if not count:
        return dict(score=None, n_tracks=0, rms_hz=None)
    return _metrics(_evaluate(tile, arcs, count, point[None, :]), 0)


def _best(points, scored):
    score, support, _ = scored
    eligible = np.flatnonzero(support >= MIN_SUPPORT)
    if len(eligible) == 0:
        return None
    return min(eligible, key=lambda i: (-score[i], points[i] @ points[i], *points[i]))


def fit_grid(tile, tracks):
    """Fit a 7 by 7 grid and two bounded subdivisions of the strongest cell."""
    arcs, count = _arcs(tile, tracks)
    if len(arcs) < MIN_SUPPORT:
        return None
    axis = np.linspace(-HALF_WIDTH_KM, HALF_WIDTH_KM, COARSE_STEPS)
    points = np.array(list(product(axis, repeat=2)))
    scored = _evaluate(tile, arcs, count, points)
    winner = _best(points, scored)
    if winner is None or np.ptp(scored[0]) <= 1e-12:
        return None
    point, metrics = points[winner], _metrics(scored, winner)
    for divisor in (4, 16):
        shifts = np.arange(-2, 3) * (axis[1] - axis[0]) / divisor
        offsets = np.array(list(product(shifts, repeat=2)))
        local = np.unique(np.clip(point + offsets, -HALF_WIDTH_KM, HALF_WIDTH_KM), axis=0)
        # The incumbent has already been scored, including when clipping duplicates it.
        local = local[np.any(local != point, axis=1)]
        local_scores = _evaluate(tile, arcs, count, local)
        winner = _best(local, local_scores)
        if winner is not None and local_scores[0][winner] > metrics["score"]:
            point, metrics = local[winner], _metrics(local_scores, winner)
    _, _, latlon = _sites(tile, point[None, :])
    return dict(xy=point.tolist(), latlon=latlon[0].tolist(), **metrics)
