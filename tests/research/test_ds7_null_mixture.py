from types import SimpleNamespace

import numpy as np

from tools.ds7_null_mixture import NullMixtureJoint


def test_null_mixture_gradient_matches_difference_and_dilutes_satellite():
    class Model:
        def __init__(self, document, config):
            pass

        def evaluate(self, x, gradient=False):
            return -float(x @ x), -2 * x

    baseline = SimpleNamespace(
        Stationary=Model,
        profile=lambda y, mask: ([-1.0], None, [{"converged": True}], None),
    )
    documents = [{"tracks": [{"y": np.array([0.0]), "mask": np.array([True])}]}]
    model = NullMixtureJoint(documents, {"null_prior_mass": 0.01}, baseline)
    point = np.array([0.4, -0.3, 0.1])
    _, derivative = model.value_gradient(point)
    numeric = []
    for axis in range(3):
        delta = np.eye(3)[axis] * 1e-5
        numeric.append(
            (model.value_gradient(point + delta)[0] - model.value_gradient(point - delta)[0]) / 2e-5
        )
    np.testing.assert_allclose(derivative, numeric, atol=1e-9)
    null_probability = model.null_responsibilities(point)[0]
    assert 0 < null_probability < 1
    np.testing.assert_allclose(derivative, 2 * point * (1 - null_probability))
