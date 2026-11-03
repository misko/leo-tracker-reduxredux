import unittest

import numpy as np
from study import correction, error


class ConventionTests(unittest.TestCase):
    def test_normalization_identity(self):
        raw = np.array([100.0, 200.0, 300.0])
        actual = 11e9
        nominal = 11.0003125e9
        old = raw * 11.2e9 / actual
        np.testing.assert_allclose(old + correction(old, actual, nominal), raw * 11.2e9 / nominal)
        np.testing.assert_array_equal(correction(old, actual, actual), np.zeros(3))

    def test_stationary_offset_removal(self):
        mask = np.array([True, False, True, False])
        y = np.array([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(error(y, mask), error(y + 1000, mask))


if __name__ == "__main__":
    unittest.main()
