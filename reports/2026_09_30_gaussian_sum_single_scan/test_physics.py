from __future__ import annotations

import numpy as np
import pytest
from physics import (
    OrbitBank,
    PhysicsConfig,
    StateLayout,
    TrackObservations,
    build_physics_factor,
    build_regional_prior,
    geodetic_ecef_km,
    geometric_candidate_union,
    helmert_contrasts,
    hermite_interpolate,
)

from leo.analysis.gaussian_sum_location import FilterConfig, update_filter


def _bank() -> OrbitBank:
    times = np.arange(-10.0, 21.0, 5.0)
    receiver = geodetic_ecef_km(37.85625, -122.484375, 0.0)
    up = receiver / np.linalg.norm(receiver)
    east = np.cross(np.array([0.0, 0.0, 1.0]), up)
    east /= np.linalg.norm(east)
    position = receiver + 1000.0 * up + times[:, None] * 7.0 * east
    velocity = np.broadcast_to(7.0 * east, position.shape).copy()
    return OrbitBank((101,), times, position[None, :, :], velocity[None, :, :])


def _track() -> TrackObservations:
    times = np.array([0.0, 1.0, 2.0, 3.0])
    return TrackObservations(
        tuple(f"sample-{index}" for index in range(4)),
        times,
        np.array([10.0, 20.0, 25.0, 40.0]),
        np.zeros(4, dtype=np.int64),
        11.325e9,
    )


def test_hermite_position_and_independent_velocity_cubics_are_exact() -> None:
    times = np.arange(-2.0, 3.0)
    positions = np.column_stack((times**3, 2 * times**2, times))
    position_derivative = np.column_stack((3 * times**2, 4 * times, np.ones_like(times)))
    # Authoritative velocity need not equal the position derivative.
    authoritative = np.column_stack((times**3 + 2, times**2 - times, 3 * times + 1))
    query = 0.25
    position, velocity, acceleration = hermite_interpolate(
        times, positions, position_derivative, query
    )
    np.testing.assert_allclose(position, [query**3, 2 * query**2, query], atol=1e-14)
    # Exercise independent authoritative interpolation in a separate call.
    _, velocity, acceleration = hermite_interpolate(times, positions, authoritative, query)
    np.testing.assert_allclose(velocity, [query**3 + 2, query**2 - query, 3 * query + 1])
    np.testing.assert_allclose(acceleration, [3 * query**2, 2 * query - 1, 3])


def test_helmert_is_block_diagonal_and_removes_each_receiver_offset() -> None:
    receivers = np.array([0, 1, 0, 1, 0])
    contrasts = helmert_contrasts(receivers)
    np.testing.assert_allclose(contrasts @ contrasts.T, np.eye(3), atol=1e-15)
    np.testing.assert_allclose(contrasts @ np.array([4.0, -8.0, 4.0, -8.0, 4.0]), 0.0)
    for row in contrasts:
        assert not (np.any(row[receivers == 0]) and np.any(row[receivers == 1]))


def test_factor_covariance_and_geometry_jacobian() -> None:
    config = PhysicsConfig()
    layout = StateLayout((101,))
    built = build_physics_factor(_track(), _bank(), layout, config)
    state = build_regional_prior(layout, config).components[0].mean
    prediction = built.factor.candidates[0].predict(state)
    np.linalg.cholesky(prediction.covariance)
    assert prediction.eligible
    assert built.factor.background_log_likelihood < 0.0

    # Audit one geometry column independently with a larger finite-difference step.
    step = 1e-3
    plus, minus = state.copy(), state.copy()
    plus[0] += step
    minus[0] -= step
    numerical = (
        built.factor.candidates[0].predict(plus).mean
        - built.factor.candidates[0].predict(minus).mean
    ) / (2 * step)
    np.testing.assert_allclose(prediction.jacobian[:, 0], numerical, rtol=2e-4, atol=1e-5)


def test_candidate_prior_routes_visibility_mass_and_shared_state_updates() -> None:
    config = PhysicsConfig()
    layout = StateLayout((101,))
    built = build_physics_factor(_track(), _bank(), layout, config)
    state = build_regional_prior(layout, config)
    mean = state.components[0].mean
    signal_prior = built.factor.candidates[0].prior(mean)
    background_prior = built.factor.background_prior(mean)
    assert signal_prior + background_prior == pytest.approx(1.0)
    assert signal_prior == pytest.approx(0.8)

    first = update_filter(state, built.factor, FilterConfig(max_components=8, max_child_work=20))
    signal = next(
        component for component in first.state.components if component.identity_history[-1] == "101"
    )
    # Position, common time, RX drift, and this satellite's epoch remain one joint covariance.
    active = [0, 1, 2, 3, 4, layout.satellite_epoch_index(101)]
    assert np.any(
        np.abs(
            signal.covariance[np.ix_(active, active)] - np.diag(np.diag(signal.covariance)[active])
        )
        > 0
    )
    second_track = TrackObservations(
        tuple(f"next-{index}" for index in range(4)),
        _track().times_s + 0.5,
        _track().frequencies_hz,
        _track().receiver_indices,
        _track().rf_hz,
    )
    second_factor = build_physics_factor(second_track, _bank(), layout, config).factor
    second = update_filter(
        first.state, second_factor, FilterConfig(max_components=8, max_child_work=20)
    )
    assert all(len(component.identity_history) == 2 for component in second.state.components)


def test_declared_prior_dimensions_and_support_failure() -> None:
    layout = StateLayout((101, 202))
    config = PhysicsConfig()
    prior = build_regional_prior(layout, config)
    assert len(prior.components) == 4
    assert prior.components[0].mean.size == 8
    assert prior.components[0].covariance[6, 6] == pytest.approx(0.25)

    outside = _track()
    outside = TrackObservations(
        outside.observation_ids,
        outside.times_s + 20.0,
        outside.frequencies_hz,
        outside.receiver_indices,
        outside.rf_hz,
    )
    with pytest.raises(ValueError, match="time padding"):
        build_physics_factor(outside, _bank(), StateLayout((101,)), config)


def test_raw_receiver_drift_is_scaled_to_each_tracks_reference_measurements() -> None:
    config = PhysicsConfig()
    layout = StateLayout((101,))
    low = _track()
    high = TrackObservations(
        low.observation_ids,
        low.times_s,
        low.frequencies_hz,
        low.receiver_indices,
        12.0e9,
    )
    low_factor = build_physics_factor(low, _bank(), layout, config).factor
    high_factor = build_physics_factor(high, _bank(), layout, config).factor
    state = build_regional_prior(layout, config).components[0].mean
    low_drift_column = low_factor.candidates[0].predict(state).jacobian[:, 4]
    high_drift_column = high_factor.candidates[0].predict(state).jacobian[:, 4]
    np.testing.assert_allclose(
        high_drift_column / low_drift_column, low.rf_hz / high.rf_hz, rtol=1e-8
    )


def test_candidate_union_uses_motion_bound_to_widen_horizon_radius() -> None:
    config = PhysicsConfig()
    receiver = geodetic_ecef_km(config.prior_center_lat_deg, config.prior_center_lon_deg, 0.0)
    radial = receiver / np.linalg.norm(receiver)
    tangent = np.cross(np.array([0.0, 0.0, 1.0]), radial)
    tangent /= np.linalg.norm(tangent)
    theta = np.radians(30.0)
    direction = np.cos(theta) * radial + np.sin(theta) * tangent
    times = np.arange(-10.0, 11.0, 5.0)
    positions = np.broadcast_to(6878.0 * direction, (times.size, 3)).copy()
    still = OrbitBank((7,), times, positions[None], np.zeros((1, times.size, 3)))
    rapid_radial = np.broadcast_to(40.0 * direction, (1, times.size, 3)).copy()
    moving = OrbitBank((7,), times, positions[None], rapid_radial)

    assert 7 not in geometric_candidate_union(still, config).norad_ids
    assert 7 in geometric_candidate_union(moving, config).norad_ids
