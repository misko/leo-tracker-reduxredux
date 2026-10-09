"""Marginal preservation and sequence differentiation, using synthetic arrays only."""

import importlib.util
import itertools
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.hard60_score import likelihood
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.application.hard60_runner import HARD60_SCORE

spec = importlib.util.spec_from_file_location(
    "persistence109", Path(__file__).with_name("persistence.py")
)
kernel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kernel)


@pytest.mark.parametrize(
    "previous,current",
    [
        ([0.2, 0.3, 0.5], [0.2, 0.3, 0.5]),
        ([0.2, 0.3, 0.5], [0.4, 0.0, 0.6]),
        ([0.4, 0.0, 0.6], [0.2, 0.3, 0.5]),
        ([1.0, 0.0, 0.0], [0.2, 0.3, 0.5]),
        ([0.2, 0.3, 0.5], [1.0, 0.0, 0.0]),
    ],
)
def test_prior_transport(previous, current):
    previous, current = np.array(previous), np.array(current)
    s, r = kernel.transport(previous, current, 0.8)
    transition = np.diag(s) + (1 - s)[:, None] * r[None, :]
    np.testing.assert_allclose(transition.sum(axis=1), 1, atol=1e-14)
    np.testing.assert_allclose(previous @ transition, current, atol=1e-14)
    assert s[0] == 0 and np.all(s[(previous == 0) | (current == 0)] == 0)
    np.testing.assert_array_equal(transition[0], r)
    assert np.all(transition >= 0)


def fixture():
    y = np.array([0.0, 70.0, 120.0])
    p = np.array([[10.0, 180.0, 1200.0], [40.0, 160.0, 900.0], [90.0, 250.0, 800.0]])
    v = np.array([[True, True, False], [False, True, True], [True, True, True]])
    return y, p, v


def test_independent_including_detection_and_wrap():
    y, p, v = fixture()
    actual = kernel.evaluate(y, p, v, HARD60_SCORE, rho=0, reset=np.array([True, False, False]))
    expected = likelihood(y, p, v, HARD60_SCORE)
    assert actual["nll"] == expected.nll
    np.testing.assert_array_equal(actual["prediction_gradient"], expected.prediction_gradient)
    _, pi, _, emission, log_d, _ = kernel.BASE["components"](y, p, v, HARD60_SCORE)
    np.testing.assert_allclose(
        -np.sum(log_d + np.log((pi * emission).sum(axis=1))), expected.nll, atol=1e-13
    )
    wrapped = kernel.evaluate(y, p + ALIAS_HZ, v, HARD60_SCORE, rho=0, reset=np.ones(3, bool))
    np.testing.assert_allclose(wrapped["nll"], expected.nll, atol=1e-12)


def test_bruteforce_and_prediction_gradient():
    y, p, v = fixture()
    rho, reset = 0.6, np.array([True, False, False])
    actual = kernel.evaluate(y, p, v, HARD60_SCORE, rho=rho, reset=reset)
    _, pi, _, emission, log_d, _ = kernel.BASE["components"](y, p, v, HARD60_SCORE)
    transitions = []
    for n in (1, 2):
        s, r = kernel.transport(pi[n - 1], pi[n], rho)
        transitions.append(np.diag(s) + (1 - s)[:, None] * r[None, :])
    total, mass = 0.0, np.zeros((3, 4))
    for states in itertools.product(range(4), repeat=3):
        weight = pi[0, states[0]] * emission[0, states[0]]
        for n in (1, 2):
            weight *= transitions[n - 1][states[n - 1], states[n]] * emission[n, states[n]]
        total += weight
        for n, state in enumerate(states):
            mass[n, state] += weight
    np.testing.assert_allclose(actual["nll"], -np.log(total) - log_d.sum(), atol=1e-12)
    np.testing.assert_allclose(actual["occupancy"], mass / total, atol=1e-14)
    for n, s in itertools.product(range(3), range(3)):
        plus, minus = p.copy(), p.copy()
        plus[n, s] += 0.001
        minus[n, s] -= 0.001
        derivative = (
            kernel.evaluate(y, plus, v, HARD60_SCORE, rho=rho, reset=reset)["nll"]
            - kernel.evaluate(y, minus, v, HARD60_SCORE, rho=rho, reset=reset)["nll"]
        ) / 0.002
        assert derivative == pytest.approx(actual["prediction_gradient"][n, s], abs=1e-10)


def test_all_reset_independent_and_invalid_inputs():
    y, p, v = fixture()
    result = kernel.evaluate(y, p, v, HARD60_SCORE, rho=0.9, reset=np.ones(3, bool))
    np.testing.assert_allclose(result["nll"], likelihood(y, p, v, HARD60_SCORE).nll, atol=1e-13)
    for rho in (-1, 1, np.nan):
        with pytest.raises(ValueError):
            kernel.transport([0.5, 0.5], [0.5, 0.5], rho)
