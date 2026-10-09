"""Actual normalized mixture checks at both predeclared frequency widths."""

from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.hard60_score import likelihood
from leo.analysis.regional_position_score import ALIAS_HZ, singleton_likelihood
from leo.application.hard60_runner import HARD60_SCORE


@pytest.mark.parametrize("width", [125.0, 100.0])
def test_normalized_mixture_matches_oracle_and_density(width):
    score = replace(HARD60_SCORE, sigma_hz=width)
    count = int(score.detection_budget) + 3
    prediction = np.tile(np.linspace(-300, 400, count), (3, 1))
    measured = np.array([0.0, 67.0, -91.0])
    visible = np.ones(prediction.shape, bool)
    visible[1, 0] = False
    actual = likelihood(measured, prediction, visible, score)
    oracle = singleton_likelihood(measured, prediction, visible, score)
    for key in ("nll", "responsibilities", "clutter_probability", "prediction_gradient"):
        np.testing.assert_allclose(getattr(actual, key), getattr(oracle, key), atol=1e-12)
    q = score.detection_budget / count
    signal = np.exp(-0.5 * (actual.residual_hz / width) ** 2) * visible
    signal *= q / (1 - q) / (width * np.sqrt(2 * np.pi))
    clutter = score.clutter_rate / ALIAS_HZ
    total = clutter + signal.sum(axis=1)
    log_p0 = -score.clutter_rate + visible.sum(axis=1) * np.log1p(-q)
    expected = -np.sum(log_p0 - np.log(-np.expm1(log_p0)) + np.log(total))
    assert actual.nll == pytest.approx(expected, abs=1e-12)
    np.testing.assert_allclose(
        actual.responsibilities.sum(axis=1) + actual.clutter_probability, 1.0
    )


@pytest.mark.parametrize("width", [125.0, 100.0])
def test_wrapping_and_prediction_gradient(width):
    score = replace(HARD60_SCORE, sigma_hz=width)
    count = int(score.detection_budget) + 3
    prediction = np.tile(np.linspace(-250, 350, count), (2, 1))
    measured = np.array([17.0, -36.0])
    visible = np.ones(prediction.shape, bool)
    original = likelihood(measured, prediction, visible, score)
    wrapped = likelihood(measured + ALIAS_HZ, prediction - 2 * ALIAS_HZ, visible, score)
    np.testing.assert_allclose(original.responsibilities, wrapped.responsibilities, atol=1e-12)
    assert original.nll == pytest.approx(wrapped.nll, abs=1e-10)
    direction = np.linspace(-0.8, 1.2, prediction.size).reshape(prediction.shape)
    h = 0.001
    derivative = (
        likelihood(measured, prediction + h * direction, visible, score).nll
        - likelihood(measured, prediction - h * direction, visible, score).nll
    ) / (2 * h)
    assert derivative == pytest.approx(
        np.sum(original.prediction_gradient * direction), rel=1e-6, abs=1e-8
    )
