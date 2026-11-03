import numpy as np
import pytest
from time_shift_model import TimeShiftObjective, gaussian_prior, interpolate_states


def test_gaussian_prior():
    value, gradient = gaussian_prior(np.array([-3.0, 0.0, 1.0]), 1)
    assert value == 5
    np.testing.assert_array_equal(gradient, [-3, 0, 1])
    with pytest.raises(ValueError):
        gaussian_prior(np.zeros(2), 0)


def test_each_satellite_has_one_shared_shift():
    nodes = np.arange(-4, 10, 0.25)
    positions = np.broadcast_to(nodes[None, :, None], (2, len(nodes), 3)).copy()
    velocities = np.ones_like(positions)
    times = np.array([0.1, 0.7, 1.3])
    shifts = np.array([-3, 3])
    position, velocity, position_rate, acceleration = interpolate_states(
        nodes, positions, velocities, times, shifts
    )
    np.testing.assert_allclose(position[:, :, 0], times[:, None] + shifts)
    np.testing.assert_allclose(velocity, 1)
    np.testing.assert_allclose(position_rate, 1)
    np.testing.assert_allclose(acceleration, 0)


def test_queries_outside_grid_fail():
    nodes = np.arange(4.0)
    states = np.zeros((1, 4, 3))
    with pytest.raises(ValueError):
        interpolate_states(nodes, states, states, np.array([0.0]), np.array([-1.0]))


def test_ten_second_bounds_and_prior():
    nodes = np.arange(-11, 311.001, 0.25)
    positions = np.broadcast_to(nodes[None, :, None], (2, len(nodes), 3)).copy()
    times = np.array([0.0, 300.0])
    shifts = np.array([-10.0, 10.0])
    position, _, _, _ = interpolate_states(nodes, positions, positions, times, shifts)
    np.testing.assert_allclose(position[:, :, 0], times[:, None] + shifts)
    value, gradient = gaussian_prior(shifts, 10 / 3)
    assert value == pytest.approx(9)
    np.testing.assert_allclose(gradient, [-0.9, 0.9])


def test_full_objective_gradient():
    nodes = np.arange(-4, 10, 0.25)
    positions = np.zeros((2, len(nodes), 3))
    velocities = np.zeros_like(positions)
    for satellite in range(2):
        positions[satellite, :, 0] = 7000
        positions[satellite, :, 1] = 1000 + satellite * 2000 + 7 * nodes + 0.005 * nodes**2
        velocities[satellite, :, 1] = 7 + 0.01 * nodes
    times = np.array([0.1, 0.6, 1.1, 1.6])
    states = {"nodes": nodes, "position": positions, "velocity": velocities}
    point = np.array([1.0, 2.0, 0.037, -0.051])

    def site(coordinates):
        return np.array([coordinates[0], coordinates[1], 0.0]), np.array([1.0, 0.0, 0.0])

    position, velocity, _, _ = interpolate_states(nodes, positions, velocities, times, point[2:])
    delta = position[:, 0] - site(point[:2])[0]
    prediction = (
        -11.2e9
        / 299792.458
        * np.sum(delta / np.linalg.norm(delta, axis=1)[:, None] * velocity[:, 0], axis=1)
    )
    data = {
        "times": times,
        "rf": np.full(4, 11.2e9),
        "measured": prediction + 50,
        "group": np.arange(4),
    }
    objective = TimeShiftObjective(data, states, np.zeros(4), site)
    _, analytic = objective.evaluate(point)
    for index in range(4):
        plus, minus = point.copy(), point.copy()
        plus[index] += 1e-5
        minus[index] -= 1e-5
        numeric = (objective.evaluate(plus)[0] - objective.evaluate(minus)[0]) / 2e-5
        assert analytic[index] == pytest.approx(numeric, rel=1e-4, abs=1e-5)
