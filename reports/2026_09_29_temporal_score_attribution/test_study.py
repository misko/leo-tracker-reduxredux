import unittest

import numpy as np
from study import profiled_contribution


class Tests(unittest.TestCase):
    def test_profile_attribution_is_additive(self):
        h = np.array([[4.0, 0.0, 1.0], [0.0, 3.0, 0.5], [1.0, 0.5, 2.0]])
        gradients = np.array([[2.0, -3.0, 7.0], [-1.0, 4.0, -0.5], [0.0, 2.0, 1.0]])
        expected = gradients.sum(axis=0)[:2] - h[:2, 2] / h[2, 2] * gradients.sum(axis=0)[2]
        actual = sum(profiled_contribution(g, h) for g in gradients)
        np.testing.assert_allclose(actual, expected)


if __name__ == "__main__":
    unittest.main()
