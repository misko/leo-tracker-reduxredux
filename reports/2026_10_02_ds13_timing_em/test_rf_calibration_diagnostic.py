import numpy as np
from finite_set_likelihood import prepare_finite_set_likelihood
from rf_calibration_diagnostic import CalibratedLikelihood, rf_features


def test_rf_features_center_on_band_and_separate_receivers():
    rf = np.array([10.71, 10.96, 11.21, 11.46]) * 1e9
    center, common = rf_features(rf, np.array([0, 1, 0, 1]), False)
    assert center == 11.085e9
    np.testing.assert_allclose(common[:, 0], [-.375, -.125, .125, .375])
    _, separate = rf_features(rf, np.array([0, 1, 0, 1]), True)
    np.testing.assert_allclose(separate.sum(axis=1), common[:, 0])
    np.testing.assert_array_equal(separate[[0, 2], 1], 0)


def test_rf_coefficient_gradient_matches_finite_difference():
    features = np.array([[-.375], [-.125], [.125], [.375]])
    prepared = prepare_finite_set_likelihood([200., 100., -100., -200.], np.arange(4))
    likelihood = CalibratedLikelihood(prepared, 0.8, features)
    predicted = np.zeros((4, 1))
    visible = np.ones_like(predicted, dtype=bool)
    result = likelihood.evaluate(predicted, visible, sigma_hz=200., return_gradient=True)
    expected = float((features.T @ result["prediction_gradient"].sum(axis=1))[0])
    values = []
    for delta in [-1e-3, 1e-3]:
        likelihood.coefficients[:] = delta
        result = likelihood.evaluate(predicted, visible, sigma_hz=200.)
        values.append(result["total_log_likelihood"])
    np.testing.assert_allclose((values[1] - values[0]) / .002, expected, rtol=1e-6)
