from types import SimpleNamespace

import numpy as np
from smooth_likelihood import evaluate, taper

from leo.analysis.hard60_score import likelihood

SCORE = SimpleNamespace(sigma_hz=150, detection_budget=1.2, clutter_rate=0.3)


def fixture():
    rng = np.random.default_rng(20261009)
    measured = rng.normal(0, 300, 8)
    prediction = rng.normal(0, 300, (8, 6))
    elevation = rng.uniform(0.05, 0.95, prediction.shape)
    return measured, prediction, elevation


def test_binary_taper_matches_existing_likelihood_and_frequency_gradient():
    measured, prediction, elevation = fixture()
    visible = elevation > 0.5
    got = evaluate(measured, prediction, np.where(visible, 2.0, -2.0), SCORE)
    expected = likelihood(measured, prediction, visible, SCORE)
    np.testing.assert_allclose(got["nll"], expected.nll, rtol=0, atol=1e-10)
    np.testing.assert_allclose(
        got["prediction_gradient"], expected.prediction_gradient, rtol=0, atol=1e-12
    )
    assert np.all(got["elevation_gradient"] == 0)


def test_joint_frequency_and_visibility_derivatives_match_finite_difference():
    measured, prediction, elevation = fixture()
    got = evaluate(measured, prediction, elevation, SCORE)
    for index in np.ndindex(prediction.shape):
        for value, key, step in (
            (prediction, "prediction_gradient", 0.001),
            (elevation, "elevation_gradient", 1e-5),
        ):
            original = value[index]
            value[index] = original + step
            plus = evaluate(measured, prediction, elevation, SCORE)["nll"]
            value[index] = original - step
            minus = evaluate(measured, prediction, elevation, SCORE)["nll"]
            value[index] = original
            np.testing.assert_allclose(
                (plus - minus) / (2 * step), got[key][index], rtol=1e-5, atol=1e-7
            )


def test_horizon_has_zero_detection_and_continuous_first_derivative():
    x = np.array([-2.0, -1e-8, 0.0, 1e-8, 1.0 - 1e-8, 1.0, 1.0 + 1e-8, 2.0])
    weight, derivative = taper(x)
    assert np.all(weight[:3] == 0) and np.all(weight[5:] == 1)
    assert np.max(abs(derivative)) < 1e-6
    measured, prediction, _ = fixture()
    for boundary in (0.0, 1.0):
        values = [
            evaluate(measured, prediction, np.full(prediction.shape, boundary + d), SCORE)["nll"]
            for d in (-1e-8, 0.0, 1e-8)
        ]
        assert max(values) - min(values) < 1e-10
