"""No recordings: enumeration and finite differences independently check the kernel."""

import importlib.util
import itertools
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.hard60_score import likelihood
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.application.hard60_runner import HARD60_SCORE

spec = importlib.util.spec_from_file_location(
    "persistence108", Path(__file__).with_name("persistence.py")
)
kernel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kernel)


def fixture():
    measured = np.array([0.0, 70.0, 120.0])
    prediction = np.array([[10.0, 180.0, 1200.0], [40.0, 160.0, 900.0], [90.0, 250.0, 800.0]])
    visible = np.array([[True, True, True], [False, True, True], [True, True, True]])
    return measured, prediction, visible, HARD60_SCORE


@pytest.mark.parametrize("width", [100, 125])
def test_independent_exact(width):
    y, p, v, score = fixture()
    score = replace(score, sigma_hz=width)
    actual = kernel.evaluate(y, p, v, score, rho=0, reset=np.array([True, False, False]))
    expected = likelihood(y, p, v, score)
    assert actual["nll"] == expected.nll
    np.testing.assert_array_equal(actual["prediction_gradient"], expected.prediction_gradient)
    # The algebraic recursion also nests without the exact-order return shortcut.
    _, pi, _, emission, log_d, _ = kernel.components(y, p, v, score)
    np.testing.assert_allclose(
        -np.sum(log_d + np.log(np.sum(pi * emission, axis=1))), expected.nll, atol=1e-13, rtol=0
    )


def test_enumeration_gradient_and_reset():
    y, p, v, score = fixture()
    rho = 0.6
    reset = np.array([True, False, False])
    actual = kernel.evaluate(y, p, v, score, rho=rho, reset=reset)
    _, pi, active, emission, log_d, residual = kernel.components(y, p, v, score)
    transitions = [kernel.transition(pi[n], active[n], rho) for n in (1, 2)]
    for n, transition in enumerate(transitions, 1):
        np.testing.assert_allclose(transition.sum(axis=1), 1)
        np.testing.assert_array_equal(transition[0], pi[n])
        for state in np.flatnonzero(~active[n]):
            np.testing.assert_array_equal(transition[state], pi[n])
    total, occupancy = 0.0, np.zeros((3, 4))
    for states in itertools.product(range(4), repeat=3):
        weight = pi[0, states[0]] * emission[0, states[0]]
        for n in (1, 2):
            weight *= transitions[n - 1][states[n - 1], states[n]] * emission[n, states[n]]
        total += weight
        for n, state in enumerate(states):
            occupancy[n, state] += weight
    occupancy /= total
    np.testing.assert_allclose(actual["nll"], -np.log(total) - log_d.sum(), atol=1e-12)
    np.testing.assert_allclose(actual["occupancy"], occupancy, atol=1e-14)
    np.testing.assert_allclose(
        actual["prediction_gradient"], -occupancy[:, 1:] * residual / score.sigma_hz**2
    )
    step = 1e-3
    for n, s in itertools.product(range(3), range(3)):
        plus, minus = p.copy(), p.copy()
        plus[n, s] += step
        minus[n, s] -= step
        derivative = (
            kernel.evaluate(y, plus, v, score, rho=rho, reset=reset)["nll"]
            - kernel.evaluate(y, minus, v, score, rho=rho, reset=reset)["nll"]
        ) / (2 * step)
        assert derivative == pytest.approx(actual["prediction_gradient"][n, s], abs=1e-10)


def test_all_boundaries_independent_and_wrapped():
    y, p, v, score = fixture()
    resets = np.ones(3, bool)
    result = kernel.evaluate(y, p, v, score, rho=0.8, reset=resets)
    independent = likelihood(y, p, v, score)
    np.testing.assert_allclose(result["nll"], independent.nll, atol=1e-13)
    np.testing.assert_allclose(result["prediction_gradient"], independent.prediction_gradient)
    wrapped = kernel.evaluate(y, p + ALIAS_HZ, v, score, rho=0.8, reset=resets)
    np.testing.assert_allclose(wrapped["nll"], result["nll"], atol=1e-12)


def test_clutter_only_window_and_numeric_scaling():
    y, p, v, score = fixture()
    v[1] = False
    reset = np.array([True, False, False])
    result = kernel.evaluate(y, p, v, score, rho=0.999, reset=reset)
    assert result["occupancy"][1, 0] == 1
    single = kernel.evaluate(y[2:], p[2:], v[2:], score, rho=0.999, reset=np.array([True]))
    np.testing.assert_allclose(result["occupancy"][2], single["occupancy"][0])
    long = kernel.evaluate(
        np.tile(y, 1000),
        np.tile(p, (1000, 1)),
        np.tile(v, (1000, 1)),
        score,
        rho=0.9,
        reset=np.r_[True, np.zeros(2999, bool)],
    )
    assert np.isfinite(long["nll"]) and np.isfinite(long["prediction_gradient"]).all()


def test_invalid_parameters_rejected():
    y, p, v, score = fixture()
    for rho in (-1, 1, np.nan):
        with pytest.raises(ValueError):
            kernel.evaluate(y, p, v, score, rho=rho, reset=np.ones(3, bool))
    with pytest.raises(ValueError):
        kernel.evaluate(y, p, v, score, rho=0.5, reset=np.zeros(3, bool))
