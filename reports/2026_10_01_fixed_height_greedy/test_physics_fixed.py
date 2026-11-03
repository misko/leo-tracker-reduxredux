from __future__ import annotations

import numpy as np
import pytest
from physics_fixed import ReducedStateLayout, build_fixed_height_factor, expand_state
from physics import (
    OrbitBank,
    PhysicsConfig,
    StateLayout,
    TrackObservations,
    build_physics_factor,
    geodetic_ecef_km,
)


def _bank() -> OrbitBank:
    times = np.arange(-10.0, 21.0, 5.0)
    receiver = geodetic_ecef_km(37.85625, -122.484375, 0.0)
    up = receiver / np.linalg.norm(receiver)
    east = np.cross(np.array([0.0, 0.0, 1.0]), up)
    east /= np.linalg.norm(east)
    position = receiver + 1000.0 * up + times[:, None] * 7.0 * east
    velocity = np.broadcast_to(7.0 * east, position.shape).copy()
    return OrbitBank((101,), times, position[None], velocity[None])


def _track() -> TrackObservations:
    return TrackObservations(
        tuple(f"sample-{index}" for index in range(4)),
        np.arange(4.0),
        np.array([10.0, 20.0, 25.0, 40.0]),
        np.zeros(4, dtype=np.int64),
        11.325e9,
    )


def test_flat_surface_matches_frozen_prediction_with_height_column_removed() -> None:
    layout = StateLayout((101,))
    config = PhysicsConfig()
    full = build_physics_factor(_track(), _bank(), layout, config)
    fixed = build_fixed_height_factor(_track(), _bank(), layout, config, lambda _e, _n: 0.03048)
    reduced = np.zeros(ReducedStateLayout(layout).dimension)
    old_state = expand_state(reduced, lambda _e, _n: 0.03048)
    expected = full.factor.candidates[0].predict(old_state)
    actual = fixed.factor.candidates[0].predict(reduced)
    np.testing.assert_allclose(actual.mean, expected.mean)
    np.testing.assert_allclose(actual.jacobian, expected.jacobian[:, [0, 1, 3, 4, 5, 6]])
    assert ReducedStateLayout(layout).satellite_epoch_index(101) == 5


def test_sloped_height_chain_rule_matches_independent_mean_difference() -> None:
    layout = StateLayout((101,))

    def height(east, north):
        return 0.03048 + 0.02 * east - 0.03 * north

    fixed = build_fixed_height_factor(_track(), _bank(), layout, PhysicsConfig(), height)
    state = np.zeros(ReducedStateLayout(layout).dimension)
    prediction = fixed.factor.candidates[0].predict(state)
    step = 2e-4
    for column in (0, 1):
        plus, minus = state.copy(), state.copy()
        plus[column] += step
        minus[column] -= step
        numerical = (
            fixed.factor.candidates[0].predict(plus).mean
            - fixed.factor.candidates[0].predict(minus).mean
        ) / (2 * step)
        np.testing.assert_allclose(prediction.jacobian[:, column], numerical, rtol=3e-4, atol=2e-5)


def test_global_orbit_support_failure_is_preserved_and_explained() -> None:
    layout = StateLayout((101,))
    fixed = build_fixed_height_factor(
        _track(), _bank(), layout, PhysicsConfig(), lambda _e, _n: 0.0
    )
    state = np.zeros(ReducedStateLayout(layout).dimension)
    state[2] = 13.0
    with pytest.raises(ValueError, match="shared four-knot orbit support"):
        fixed.factor.candidates[0].predict(state)
