import numpy as np
from ds9_leakage_probe import fit_predict


def test_linear_recovery_does_not_fit_evaluation_values():
    rng = np.random.default_rng(83)
    design = rng.normal(size=(8, 30, 3)) + 1j * rng.normal(size=(8, 30, 3))
    truth = np.array([0.2j, 1, -0.3 + 0.1j])
    values = design @ truth
    prediction, coefficients = fit_predict(design, values, np.arange(4), np.arange(4, 8))
    np.testing.assert_allclose(prediction, values[4:], atol=1e-12)
    values[4:] = 1000
    changed, second = fit_predict(design, values, np.arange(4), np.arange(4, 8))
    np.testing.assert_array_equal(changed, prediction)
    np.testing.assert_array_equal(second, coefficients)
