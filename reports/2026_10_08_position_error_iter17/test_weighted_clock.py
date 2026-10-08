import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_08_position_error_iter04"))
from test_joint_clock import setup  # noqa: E402
from weighted_clock import WeightedClockObjective, density_weights  # noqa: E402


def test_uniform_weights_reproduce_value_and_gradients():
    base, old = setup()
    model = WeightedClockObjective(
        base,
        old.nodes,
        old.initial_clock.reshape(2, -1) @ old.null.T,
        np.ones(len(base.observations.times_s)),
    )
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    expected = super(WeightedClockObjective, model).evaluate_joint(seed, model.initial_clock)
    actual = model.evaluate_joint(seed, model.initial_clock)
    for a, b in zip(actual[:3], expected[:3], strict=True):
        np.testing.assert_array_equal(a, b)


def test_weighted_physical_and_clock_gradients_match_finite_difference():
    base, old = setup()
    weights = np.linspace(0.3, 2, len(base.observations.times_s))
    model = WeightedClockObjective(
        base, old.nodes, old.initial_clock.reshape(2, -1) @ old.null.T, weights
    )
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    clock = model.initial_clock + 0.1
    _, gradient, clock_gradient, _ = model.evaluate_joint(seed, clock)
    combined = np.r_[seed, clock]
    numerical = []
    for delta in np.eye(len(combined)) * 1e-4:
        plus, minus = combined + delta, combined - delta
        numerical.append(
            (
                model.evaluate_joint(plus[: len(seed)], plus[len(seed) :])[0]
                - model.evaluate_joint(minus[: len(seed)], minus[len(seed) :])[0]
            )
            / 2e-4
        )
    np.testing.assert_allclose(np.r_[gradient, clock_gradient], numerical, atol=2e-4, rtol=2e-4)


def test_density_normalization_and_receiver_separation():
    from types import SimpleNamespace

    obs = SimpleNamespace(
        times_s=np.array([0.0, 1.0, 2.0, 3.0]),
        receiver=np.array([0, 0, 1, 1]),
        channel=np.zeros(4, int),
    )
    weights = density_weights(obs, np.array([1, 1, 1, 0]), 1)
    np.testing.assert_allclose(weights, [2 / 3, 2 / 3, 4 / 3, 4 / 3])
    assert weights.sum() == 4
    with pytest.raises(ValueError):
        density_weights(obs, [1], 1)
