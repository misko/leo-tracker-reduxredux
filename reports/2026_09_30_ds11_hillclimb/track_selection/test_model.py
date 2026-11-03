import unittest
import numpy as np
from model import arrays, standardize, design, objective, log_probability

class ModelTests(unittest.TestCase):
    def test_receiver_window_weight_and_training_standardization(self):
        row = dict(window='a', rx=0, rf_hz=11e9, exact=.5, control=.1, retained=True)
        rows = [row, dict(row, exact=.7), dict(row, window='b', rx=1, retained=False)]
        features, y, weights = arrays(rows, True)
        np.testing.assert_array_equal(weights, [.5, .5, 1])
        mean, scale = standardize(features, weights)
        np.testing.assert_allclose(np.average(design(features, mean, scale)[:,1:], axis=0, weights=weights), 0, atol=1e-14)
        held = features.copy(); held[:,2] += 100
        self.assertGreater(design(held, mean, scale)[0,3], 100)

    def test_gradient_and_extreme_log_probabilities(self):
        x = np.array([[1, -.3], [1, 2], [1, -.8]])
        y = np.array([0, 1, 1]); weights = np.array([.5, .5, 1.])
        beta = np.array([.2, -.7]); _, gradient = objective(beta, x, y, weights)
        fd = []
        for d in np.eye(2)*1e-5:
            fd.append((objective(beta+d,x,y,weights)[0]-objective(beta-d,x,y,weights)[0])/2e-5)
        np.testing.assert_allclose(gradient, fd, atol=1e-8)
        self.assertTrue(np.isfinite(log_probability(np.array([1e4,1e4]),x,y)).all())
