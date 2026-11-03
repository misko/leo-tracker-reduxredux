import unittest

import numpy as np
from model import bounds, chain, projected_gradient, unpack


class BracketTests(unittest.TestCase):
    def test_chain_gradient(self):
        z = np.array([1.0, 2.0, 0.3, 0.1, -0.1])
        g = chain(2 * unpack(z))
        for i in range(len(z)):
            a = z.copy()
            b = z.copy()
            a[i] += 1e-6
            b[i] -= 1e-6
            self.assertAlmostEqual(
                g[i], (sum(unpack(a) ** 2) - sum(unpack(b) ** 2)) / 2e-6, places=7
            )

    def test_bank_bounds_and_gauge(self):
        lim = bounds([-0.1, -0.2], [0.1, 0.2])
        for b in lim[2]:
            for e in [np.array([-0.1, -0.2]), np.array([0.1, 0.2])]:
                self.assertTrue(np.all(abs(unpack(np.r_[0, 0, b, e])[2:]) <= 5))
        np.testing.assert_allclose(unpack([0, 0, 0.1, 0.1, 0.1]), unpack([0, 0, 0.2, 0, 0]))

    def test_projected_gradient(self):
        self.assertEqual(projected_gradient([0, 1], [3, -4], [(0, 1), (0, 1)]), 0)
        self.assertEqual(projected_gradient([0, 1], [-3, 4], [(0, 1), (0, 1)]), 4)


if __name__ == "__main__":
    unittest.main()
