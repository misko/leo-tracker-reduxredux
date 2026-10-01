"""Pure numerical RF physics adapter for the single-scan Gaussian-sum prototype."""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, atan2, cos, radians, sin, sqrt

import numpy as np
from numpy.typing import NDArray

from leo.analysis.gaussian_sum_location import (
    Candidate,
    FilterState,
    GaussianComponent,
    ObservationFactor,
    Prediction,
    gaussian_logpdf,
)

FloatArray = NDArray[np.float64]
LIGHT_KM_S = 299_792.458
WGS84_A_KM = 6378.137
WGS84_F = 1.0 / 298.257223563
AUTHALIC_RADIUS_KM = 6371.007180918475


def _finite_array(value: object, ndim: int, name: str) -> FloatArray:
    result = np.asarray(value, dtype=np.float64)
    if result.ndim != ndim or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite {ndim}-dimensional array")
    return result


@dataclass(frozen=True)
class OrbitBank:
    norad_ids: tuple[int, ...]
    times_s: FloatArray
    positions_ecef_km: FloatArray
    velocities_ecef_km_s: FloatArray

    def __post_init__(self) -> None:
        ids = tuple(int(value) for value in self.norad_ids)
        times = _finite_array(self.times_s, 1, "orbit times")
        positions = _finite_array(self.positions_ecef_km, 3, "orbit positions")
        velocities = _finite_array(self.velocities_ecef_km_s, 3, "orbit velocities")
        expected = (len(ids), times.size, 3)
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("NORAD IDs must be non-empty and unique")
        if times.size < 2 or np.any(np.diff(times) <= 0.0):
            raise ValueError("orbit times must be strictly increasing")
        spacing = np.diff(times)
        if not np.allclose(spacing, spacing[0], rtol=1e-12, atol=1e-12):
            raise ValueError("orbit knots must be uniformly spaced")
        if positions.shape != expected or velocities.shape != expected:
            raise ValueError(f"orbit state arrays must have shape {expected}")
        object.__setattr__(self, "norad_ids", ids)
        object.__setattr__(self, "times_s", times)
        object.__setattr__(self, "positions_ecef_km", positions)
        object.__setattr__(self, "velocities_ecef_km_s", velocities)


@dataclass(frozen=True)
class TrackObservations:
    observation_ids: tuple[str, ...]
    times_s: FloatArray
    frequencies_hz: FloatArray
    receiver_indices: NDArray[np.int64]
    rf_hz: float

    def __post_init__(self) -> None:
        ids = tuple(self.observation_ids)
        times = _finite_array(self.times_s, 1, "observation times")
        frequencies = _finite_array(self.frequencies_hz, 1, "frequencies")
        receivers = np.asarray(self.receiver_indices, dtype=np.int64)
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("observation IDs must be non-empty and unique")
        if (
            len(ids) != times.size
            or times.size != frequencies.size
            or receivers.shape != times.shape
        ):
            raise ValueError("track arrays must have equal lengths")
        if times.size < 3 or not np.all(np.isin(receivers, (0, 1))):
            raise ValueError("a track needs at least three samples and receiver indices 0 or 1")
        if not np.isfinite(self.rf_hz) or self.rf_hz <= 0.0:
            raise ValueError("physical RF frequency must be finite and positive")
        object.__setattr__(self, "observation_ids", ids)
        object.__setattr__(self, "times_s", times)
        object.__setattr__(self, "frequencies_hz", frequencies)
        object.__setattr__(self, "receiver_indices", receivers)


@dataclass(frozen=True)
class StateLayout:
    norad_ids: tuple[int, ...]

    @property
    def dimension(self) -> int:
        return 6 + len(self.norad_ids)

    def satellite_epoch_index(self, norad_id: int) -> int:
        try:
            return 6 + self.norad_ids.index(norad_id)
        except ValueError as error:
            raise KeyError(norad_id) from error


@dataclass(frozen=True)
class PhysicsConfig:
    reference_frequency_hz: float = 11_200_000_000.0
    prior_center_lat_deg: float = 37.85625
    prior_center_lon_deg: float = -122.484375
    doppler_sign: float = -1.0
    max_points: int = 8
    horizon_margin_deg: float = 2.0
    support_radius_km: float = 250.0
    height_support_km: float = 1.0
    time_padding_s: float = 10.0
    signal_prior: float = 0.8
    background_prior: float = 0.2
    white_noise_hz: float = 100.0
    correlated_noise_hz: float = 100.0
    correlation_time_s: float = 0.5
    background_slope_hz_s: float = 100.0
    background_curvature_hz_s2: float = 5.0

    def __post_init__(self) -> None:
        if self.reference_frequency_hz <= 0.0:
            raise ValueError("reference frequency must be positive")
        if self.max_points < 3:
            raise ValueError("max_points must be at least three")
        if not np.isclose(self.signal_prior + self.background_prior, 1.0):
            raise ValueError("signal and background priors must sum to one")
        if self.signal_prior < 0.0 or self.background_prior < 0.0:
            raise ValueError("source priors must be non-negative")
        if self.correlation_time_s <= 0.0 or self.support_radius_km <= 0.0:
            raise ValueError("correlation time and support radius must be positive")


@dataclass(frozen=True)
class CandidateUnion:
    norad_ids: tuple[int, ...]
    sampled_support_points: int
    minimum_tested_elevation_deg: float
    flags: tuple[str, ...]


@dataclass(frozen=True)
class PhysicsFactor:
    factor: ObservationFactor
    selected_indices: tuple[int, ...]
    visible_norad_ids: tuple[int, ...]
    flags: tuple[str, ...]


def geodetic_ecef_km(latitude_deg: float, longitude_deg: float, height_km: float) -> FloatArray:
    lat = radians(latitude_deg)
    lon = radians(longitude_deg)
    eccentricity_sq = WGS84_F * (2.0 - WGS84_F)
    prime_vertical = WGS84_A_KM / sqrt(1.0 - eccentricity_sq * sin(lat) ** 2)
    return np.array(
        [
            (prime_vertical + height_km) * cos(lat) * cos(lon),
            (prime_vertical + height_km) * cos(lat) * sin(lon),
            (prime_vertical * (1.0 - eccentricity_sq) + height_km) * sin(lat),
        ]
    )


def enu_state_ecef_km(
    east_km: float,
    north_km: float,
    height_km: float,
    center_lat_deg: float,
    center_lon_deg: float,
) -> FloatArray:
    """Map horizontal EN coordinates along a sphere, then use exact WGS84 height."""
    distance = sqrt(east_km**2 + north_km**2)
    lat1, lon1 = radians(center_lat_deg), radians(center_lon_deg)
    if distance == 0.0:
        lat2, lon2 = lat1, lon1
    else:
        angular = distance / AUTHALIC_RADIUS_KM
        bearing = atan2(east_km, north_km)
        lat2 = asin(sin(lat1) * cos(angular) + cos(lat1) * sin(angular) * cos(bearing))
        lon2 = lon1 + atan2(
            sin(bearing) * sin(angular) * cos(lat1),
            cos(angular) - sin(lat1) * sin(lat2),
        )
    return geodetic_ecef_km(np.degrees(lat2), np.degrees(lon2), height_km)


def hermite_interpolate(
    times_s: object, positions: object, velocities: object, query_s: float
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Hermite position plus four-knot cubic authoritative velocity and derivative."""
    times = _finite_array(times_s, 1, "times")
    position = _finite_array(positions, 2, "positions")
    velocity = _finite_array(velocities, 2, "velocities")
    if position.shape != (times.size, 3) or velocity.shape != position.shape:
        raise ValueError("state arrays must have shape (len(times), 3)")
    if query_s < times[1] or query_s > times[-2]:
        raise ValueError("interpolation query lacks four-knot velocity support")
    index = min(int(np.searchsorted(times, query_s, side="right") - 1), times.size - 2)
    duration = times[index + 1] - times[index]
    u = (query_s - times[index]) / duration
    p0, p1 = position[index], position[index + 1]
    v0, v1 = velocity[index], velocity[index + 1]
    h00 = 2 * u**3 - 3 * u**2 + 1
    h10 = u**3 - 2 * u**2 + u
    h01 = -2 * u**3 + 3 * u**2
    h11 = u**3 - u**2
    interpolated_position = h00 * p0 + h10 * duration * v0 + h01 * p1 + h11 * duration * v1
    # Preserve the propagated ECEF velocity convention rather than deriving it
    # from position.  A direct archive audit found that independent cubic
    # velocity interpolation is materially more accurate.
    left = min(max(index - 1, 0), times.size - 4)
    knot_times = times[left : left + 4]
    knot_velocities = velocity[left : left + 4]
    interpolated_velocity = np.zeros(3)
    acceleration = np.zeros(3)
    for j in range(4):
        others = [k for k in range(4) if k != j]
        denominator = np.prod(knot_times[j] - knot_times[others])
        numerator = np.prod(query_s - knot_times[others])
        basis = numerator / denominator
        derivative = (
            sum(
                np.prod([query_s - knot_times[k] for k in others if k != omitted])
                for omitted in others
            )
            / denominator
        )
        interpolated_velocity += basis * knot_velocities[j]
        acceleration += derivative * knot_velocities[j]
    return interpolated_position, interpolated_velocity, acceleration


def helmert_contrasts(receiver_indices: object) -> FloatArray:
    """Return deterministic orthonormal within-receiver contrasts."""
    receivers = np.asarray(receiver_indices, dtype=np.int64)
    rows: list[FloatArray] = []
    for receiver in (0, 1):
        indices = np.flatnonzero(receivers == receiver)
        for order in range(1, indices.size):
            row = np.zeros(receivers.size)
            row[indices[:order]] = 1.0 / sqrt(order * (order + 1.0))
            row[indices[order]] = -order / sqrt(order * (order + 1.0))
            rows.append(row)
    return np.stack(rows) if rows else np.empty((0, receivers.size))


def _elevation_deg(satellite_ecef: FloatArray, receiver_ecef: FloatArray) -> FloatArray:
    line = satellite_ecef - receiver_ecef
    line /= np.linalg.norm(line, axis=-1, keepdims=True)
    semiminor = WGS84_A_KM * (1.0 - WGS84_F)
    up = receiver_ecef / np.array([WGS84_A_KM**2, WGS84_A_KM**2, semiminor**2])
    up /= np.linalg.norm(up)
    return np.degrees(np.arcsin(np.clip(line @ up, -1.0, 1.0)))


def geometric_candidate_union(bank: OrbitBank, config: PhysicsConfig) -> CandidateUnion:
    """Conservative full-disk/horizon union using analytic angular bounds."""
    receiver = enu_state_ecef_km(
        0.0, 0.0, 0.0, config.prior_center_lat_deg, config.prior_center_lon_deg
    )
    radial_unit = receiver / np.linalg.norm(receiver)
    satellite_radius = np.linalg.norm(bank.positions_ecef_km, axis=2)
    satellite_unit = bank.positions_ecef_km / satellite_radius[:, :, None]
    theta = np.arccos(np.clip(satellite_unit @ radial_unit, -1.0, 1.0))

    # Bound every point in the horizontal disk plus ellipsoid-normal/geocentric
    # separation. The declared prior's five-sigma height support is below 1 km.
    earth_minimum_km = 6355.0 - config.height_support_km
    region_angle = config.support_radius_km / earth_minimum_km + radians(0.5)
    horizon_margin = radians(config.horizon_margin_deg + 0.25)
    # A cubic Hermite segment is a cubic Bezier. Its derivative is a convex
    # combination of these three derivative controls, providing a speed bound.
    duration = bank.times_s[1] - bank.times_s[0]
    displacement = np.diff(bank.positions_ecef_km, axis=1)
    middle_control = (
        3.0 * displacement / duration
        - bank.velocities_ecef_km_s[:, :-1]
        - bank.velocities_ecef_km_s[:, 1:]
    )
    segment_speed = np.maximum.reduce(
        (
            np.linalg.norm(bank.velocities_ecef_km_s[:, :-1], axis=2),
            np.linalg.norm(middle_control, axis=2),
            np.linalg.norm(bank.velocities_ecef_km_s[:, 1:], axis=2),
        )
    )
    segment_displacement_bound = 0.5 * duration * segment_speed
    knot_displacement_bound = np.zeros_like(satellite_radius)
    knot_displacement_bound[:, :-1] = np.maximum(
        knot_displacement_bound[:, :-1], segment_displacement_bound
    )
    knot_displacement_bound[:, 1:] = np.maximum(
        knot_displacement_bound[:, 1:], segment_displacement_bound
    )
    upper_satellite_radius = satellite_radius + knot_displacement_bound
    horizon_central_angle = (
        np.arccos(
            np.clip(
                earth_minimum_km / upper_satellite_radius * np.cos(horizon_margin),
                -1.0,
                1.0,
            )
        )
        + horizon_margin
    )
    motion_ratio = knot_displacement_bound / np.maximum(
        satellite_radius - knot_displacement_bound, 1e-9
    )
    motion_angle = np.arcsin(np.clip(motion_ratio, 0.0, 1.0))
    admitted = theta <= horizon_central_angle + region_angle + motion_angle
    visible = np.any(admitted, axis=1)
    center_elevation = _elevation_deg(bank.positions_ecef_km, receiver)
    minimum = float(center_elevation[visible].min()) if np.any(visible) else 90.0
    ids = tuple(
        identifier for identifier, keep in zip(bank.norad_ids, visible, strict=True) if keep
    )
    return CandidateUnion(
        ids,
        1,
        minimum,
        (
            "response_free_geometric_union",
            f"support_radius_{config.support_radius_km:g}km",
            "analytic_disk_horizon_and_hermite_motion_bounds",
        ),
    )


def _spread_indices(times: FloatArray, maximum: int) -> NDArray[np.int64]:
    order = np.argsort(times, kind="stable")
    if order.size <= maximum:
        return order
    targets = np.linspace(0, order.size - 1, maximum)
    return order[np.rint(targets).astype(np.int64)]


def _noise_covariance(times: FloatArray, config: PhysicsConfig) -> FloatArray:
    lag = np.abs(times[:, None] - times[None, :])
    return config.white_noise_hz**2 * np.eye(times.size) + config.correlated_noise_hz**2 * np.exp(
        -lag / config.correlation_time_s
    )


def build_physics_factor(
    track: TrackObservations,
    bank: OrbitBank,
    layout: StateLayout,
    config: PhysicsConfig,
) -> PhysicsFactor:
    """Build a whole-track contrasted likelihood with local visibility priors."""
    selected = _spread_indices(track.times_s, config.max_points)
    times = track.times_s[selected]
    frequencies = track.frequencies_hz[selected]
    receivers = track.receiver_indices[selected]
    contrasts = helmert_contrasts(receivers)
    if contrasts.shape[0] == 0:
        raise ValueError("selected samples provide no within-receiver contrast")
    observation = contrasts @ frequencies
    raw_covariance = _noise_covariance(times, config)
    signal_covariance = contrasts @ raw_covariance @ contrasts.T
    signal_covariance = (signal_covariance + signal_covariance.T) * 0.5
    centered = times - times.mean()
    background_design = contrasts @ np.column_stack((centered, 0.5 * centered**2))
    background_covariance = (
        signal_covariance
        + background_design
        @ np.diag([config.background_slope_hz_s**2, config.background_curvature_hz_s2**2])
        @ background_design.T
    )
    background_covariance = (background_covariance + background_covariance.T) * 0.5
    background_log_likelihood = gaussian_logpdf(observation, background_covariance)

    bank_index = {identifier: index for index, identifier in enumerate(bank.norad_ids)}
    if any(identifier not in bank_index for identifier in layout.norad_ids):
        raise ValueError("state layout contains a satellite absent from the orbit bank")
    if (
        np.min(times) - config.time_padding_s < bank.times_s[0]
        or np.max(times) + config.time_padding_s > bank.times_s[-1]
    ):
        raise ValueError("track plus time padding lies outside orbit coverage")

    union_count = len(layout.norad_ids)
    if union_count == 0:
        raise ValueError("state layout must contain at least one candidate satellite")
    satellite_indices = np.array([bank_index[value] for value in layout.norad_ids])
    knot_spacing = bank.times_s[1] - bank.times_s[0]
    drift_scale = config.reference_frequency_hz / track.rf_hz
    drift_jacobian = np.stack(
        [contrasts @ (centered * (receivers == receiver)) * drift_scale for receiver in (0, 1)],
        axis=1,
    )
    cache: dict[bytes, tuple[FloatArray, NDArray[np.bool_]]] = {}

    def all_predictions(state: FloatArray) -> tuple[FloatArray, NDArray[np.bool_]]:
        key = state.tobytes()
        if key in cache:
            return cache[key]
        receiver = enu_state_ecef_km(
            state[0], state[1], state[2], config.prior_center_lat_deg, config.prior_center_lon_deg
        )
        query = times[None, :] + state[3] + state[6:, None]
        if np.any(query < bank.times_s[1]) or np.any(query > bank.times_s[-2]):
            raise ValueError("prediction time lacks four-knot orbit support")
        interval = np.floor((query - bank.times_s[0]) / knot_spacing).astype(np.int64)
        interval = np.clip(interval, 0, bank.times_s.size - 2)
        u = (query - bank.times_s[interval]) / knot_spacing
        satellite_grid = satellite_indices[:, None]
        p0 = bank.positions_ecef_km[satellite_grid, interval]
        p1 = bank.positions_ecef_km[satellite_grid, interval + 1]
        v0 = bank.velocities_ecef_km_s[satellite_grid, interval]
        v1 = bank.velocities_ecef_km_s[satellite_grid, interval + 1]
        position = (
            (2 * u**3 - 3 * u**2 + 1)[:, :, None] * p0
            + (u**3 - 2 * u**2 + u)[:, :, None] * knot_spacing * v0
            + (-2 * u**3 + 3 * u**2)[:, :, None] * p1
            + (u**3 - u**2)[:, :, None] * knot_spacing * v1
        )
        left = np.clip(interval - 1, 0, bank.times_s.size - 4)
        velocity = np.zeros_like(position)
        for j in range(4):
            knot_j = left + j
            basis = np.ones_like(query)
            for k in range(4):
                if k != j:
                    basis *= (query - bank.times_s[left + k]) / (
                        bank.times_s[knot_j] - bank.times_s[left + k]
                    )
            velocity += basis[:, :, None] * bank.velocities_ecef_km_s[satellite_grid, knot_j]
        line = position - receiver
        unit = line / np.linalg.norm(line, axis=2, keepdims=True)
        doppler = (
            config.doppler_sign
            * config.reference_frequency_hz
            / LIGHT_KM_S
            * np.sum(velocity * unit, axis=2)
        )
        drift = state[4 + receivers] * drift_scale * centered
        means = (doppler + drift) @ contrasts.T
        semiminor = WGS84_A_KM * (1.0 - WGS84_F)
        up = receiver / np.array([WGS84_A_KM**2, WGS84_A_KM**2, semiminor**2])
        up /= np.linalg.norm(up)
        elevations = np.degrees(np.arcsin(np.clip(unit @ up, -1.0, 1.0)))
        visible = np.all(elevations >= -config.horizon_margin_deg, axis=1)
        cache[key] = means, visible
        return means, visible

    def candidate_prior(row: int):
        return lambda state: (
            config.signal_prior / union_count if all_predictions(state)[1][row] else 0.0
        )

    def background_prior(state: FloatArray) -> float:
        visible_count = int(np.count_nonzero(all_predictions(state)[1]))
        return (
            config.background_prior
            + config.signal_prior * (union_count - visible_count) / union_count
        )

    steps = np.full(layout.dimension, 1e-4)

    def predictor(identifier: int, row: int):
        def predict(state: FloatArray) -> Prediction:
            means, visibility = all_predictions(state)
            jacobian = np.zeros((observation.size, layout.dimension))
            for index in (0, 1, 2, 3):
                plus, minus = state.copy(), state.copy()
                plus[index] += steps[index]
                minus[index] -= steps[index]
                jacobian[:, index] = (
                    all_predictions(plus)[0][row] - all_predictions(minus)[0][row]
                ) / (2.0 * steps[index])
            jacobian[:, 4:6] = drift_jacobian
            jacobian[:, layout.satellite_epoch_index(identifier)] = jacobian[:, 3]
            return Prediction(means[row], jacobian, signal_covariance, eligible=visibility[row])

        return predict

    candidates = tuple(
        Candidate(str(identifier), candidate_prior(row), predictor(identifier, row))
        for row, identifier in enumerate(layout.norad_ids)
    )
    factor = ObservationFactor(
        tuple(track.observation_ids[index] for index in selected),
        observation,
        candidates,
        background_prior,
        background_log_likelihood,
    )
    return PhysicsFactor(
        factor,
        tuple(int(index) for index in selected),
        layout.norad_ids,
        ("local_visibility_prior", "cfo_removed_by_helmert", "assumed_noise_not_calibrated"),
    )


def build_regional_prior(
    layout: StateLayout, config: PhysicsConfig, *, stress: bool = False
) -> FilterState:
    """Construct the declared four-mode regional or stress prior."""
    centers = ((-5.0, -5.0), (-5.0, 5.0), (5.0, -5.0), (5.0, 5.0))
    horizontal_sigma = 5.0
    if stress:
        centers = ((-60.0, -40.0), (-60.0, 40.0), (60.0, -40.0), (60.0, 40.0))
        horizontal_sigma = 15.0
    variance = np.array(
        [
            horizontal_sigma**2,
            horizontal_sigma**2,
            0.1**2,
            1.0**2,
            0.5**2,
            0.5**2,
            *([0.5**2] * len(layout.norad_ids)),
        ]
    )
    components = []
    for east, north in centers:
        mean = np.zeros(layout.dimension)
        mean[:2] = east, north
        components.append(GaussianComponent(0.25, mean, np.diag(variance)))
    return FilterState(tuple(components))
