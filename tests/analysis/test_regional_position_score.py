"""Independent probability and derivative checks for both regional scores."""

import numpy as np
import pytest

from leo.analysis.regional_position_score import (
    ALIAS_HZ,
    PositionObjective,
    coordinates,
    observer,
    predict_orbits,
    singleton_likelihood,
    zero_sum_basis,
)
from leo.contracts.regional_position import (
    POSITION_SCORES,
    PositionObservations,
    PositionOrbitBank,
    RegionalPrior,
)


def synthetic_inputs():
    prior = RegionalPrior()
    site, up = observer(prior, [0, 0])
    east = np.cross([0, 0, 1], up)
    east /= np.linalg.norm(east)
    north = np.cross(up, east)
    nodes = np.arange(-30, 121, 10, dtype=float)
    positions, velocities = [], []
    for i in range(3):
        initial = site + (700 + 40 * i) * up + (i - 1) * 700 * east + 80 * i * north
        speed = (4 - 2 * i) * east + (i + 1) * north + 0.2 * up
        acceleration = -0.002 * up + 0.0002 * i * east
        positions.append(
            initial + nodes[:, None] * speed + 0.5 * nodes[:, None] ** 2 * acceleration
        )
        velocities.append(speed + nodes[:, None] * acceleration)
    bank = PositionOrbitBank(np.arange(100, 103), nodes, positions, velocities)
    times = np.arange(0.37, 80, 1.3)
    n = len(times)
    observations = PositionObservations(
        tuple(f"w{i}" for i in range(n)),
        times,
        np.zeros(n),
        11.2e9 + np.arange(n) % 4 * 200e6,
        np.arange(n) % 2,
        np.arange(n) % 4,
        np.full(n, 0.1),
    )
    prediction = predict_orbits(bank, observations, prior, [3, -5], [0.2, 0.3, 0.4])[0]
    measured = prediction[np.arange(n), np.arange(n) % 3] + 15 * np.sin(times)
    observations = PositionObservations(
        observations.window_ids,
        times,
        measured,
        observations.rf_hz,
        observations.receiver,
        observations.channel,
        observations.margin,
    )
    return observations, bank, prior


@pytest.mark.parametrize("name", ["T1AT", "V16"])
def test_likelihood_matches_direct_probability_and_derivative(name):
    score = POSITION_SCORES[name]
    measured = np.array([20.0, 210.0, 12.0])
    prediction = np.array([[0, 30, 1700], [0, 900, -20], [1, 2, 3]], dtype=float)
    visible = np.ones((3, 3), bool)
    visible[2] = False
    result = singleton_likelihood(measured, prediction, visible, score)
    # Direct singleton finite-set probability, independent of log-domain code.
    q = visible * score.detection_budget / 3
    gaussian = np.exp(-0.5 * ((measured[:, None] - prediction) / score.sigma_hz) ** 2)
    gaussian /= score.sigma_hz * np.sqrt(2 * np.pi)
    p0 = np.exp(-score.clutter_rate) * np.prod(1 - q, axis=1)
    probability = (
        p0 / (1 - p0) * (score.clutter_rate / ALIAS_HZ + np.sum(q / (1 - q) * gaussian, axis=1))
    )
    np.testing.assert_allclose(result.nll, -np.log(probability).sum(), atol=1e-12)
    np.testing.assert_allclose(
        result.responsibilities.sum(axis=1) + result.clutter_probability, 1, atol=1e-14
    )
    assert result.clutter_probability[2] == pytest.approx(1)
    for i, j in np.ndindex(prediction.shape):
        delta = np.zeros_like(prediction)
        delta[i, j] = 0.01
        plus = singleton_likelihood(measured, prediction + delta, visible, score).nll
        minus = singleton_likelihood(measured, prediction - delta, visible, score).nll
        assert (plus - minus) / 0.02 == pytest.approx(result.prediction_gradient[i, j], abs=1e-9)


@pytest.mark.parametrize("name", ["T1AT", "V16"])
def test_full_objective_gradient(name):
    observations, bank, prior = synthetic_inputs()
    objective = PositionObjective(observations, bank, prior, POSITION_SCORES[name])
    vector = np.array([3.1, -5.2, 12, 0.1, -23, -0.15, 10, 0.3, 0.03, -0.04])
    value, gradient, _ = objective.evaluate(vector)
    assert np.isfinite(value)
    for j in range(objective.size):
        delta = np.zeros(objective.size)
        delta[j] = 1e-4
        numerical = (
            objective.evaluate(vector + delta)[0] - objective.evaluate(vector - delta)[0]
        ) / (2 * delta[j])
        assert gradient[j] == pytest.approx(numerical, rel=3e-5, abs=1e-5), j


def test_alias_and_inventory_invariance():
    observations, bank, prior = synthetic_inputs()
    prediction, visible, _, _ = predict_orbits(bank, observations, prior, [0, 0], [0, 0, 0])
    original = singleton_likelihood(
        observations.measured_hz, prediction, visible, POSITION_SCORES["V16"]
    )
    shifted = singleton_likelihood(
        observations.measured_hz + 3 * ALIAS_HZ, prediction, visible, POSITION_SCORES["V16"]
    )
    assert original.nll == pytest.approx(shifted.nll, abs=1e-8)
    assert len(original.clutter_probability) == len(observations.window_ids)
    # A hard window never disappears: it contributes a finite clutter likelihood.
    off = singleton_likelihood(
        [50_000], np.zeros((1, 3)), np.ones((1, 3), bool), POSITION_SCORES["V16"]
    )
    assert off.nll > 0 and off.clutter_probability[0] == pytest.approx(1)


def test_chart_gauge_and_ephemeris_bounds():
    observations, bank, prior = synthetic_inputs()
    np.testing.assert_allclose(coordinates(prior, [0, 0]), [38.5816, -121.4944])
    for count in (1, 2, 20):
        basis = zero_sum_basis(count)
        np.testing.assert_allclose(basis.sum(axis=0), 0, atol=1e-14)
        np.testing.assert_allclose(basis.T @ basis, np.eye(count - 1), atol=1e-14)
    with pytest.raises(ValueError, match="ephemeris support"):
        predict_orbits(bank, observations, prior, [0, 0], [1000, 0, 0])
    # No silent clamp of an unsupported shifted orbit epoch.
    with pytest.raises(ValueError, match="detection budget"):
        singleton_likelihood([0], [[0]], np.ones((1, 1), bool), POSITION_SCORES["V16"])
