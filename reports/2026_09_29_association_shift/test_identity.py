import unittest

import numpy as np

from study import decompose


class IdentityTest(unittest.TestCase):
    def test_identity_and_dominant_component_switch(self):
        a = np.array([-8.0, -1.0, -20.0])
        b = np.array([-8.0, -20.0, -1.0])
        out = decompose(a, b)
        self.assertAlmostEqual(out['delta'], 0)
        self.assertGreater(out['posterior_kl'], 10)
        self.assertTrue(out['satellite_map_changed'])

    def test_no_change_and_common_offset(self):
        a = np.array([-1000., -1001., -2000.])
        out = decompose(a, a + 3)
        self.assertAlmostEqual(out['delta'], 3)
        self.assertAlmostEqual(out['frozen_gain'], 3)
        self.assertAlmostEqual(out['posterior_kl'], 0)
        self.assertAlmostEqual(out['total_variation'], 0)

    def test_random_identity(self):
        rng = np.random.default_rng(1)
        for _ in range(100):
            out = decompose(rng.normal(size=8)*100, rng.normal(size=8)*100)
            self.assertLess(out['identity_error'], 1e-8)


if __name__ == '__main__':
    unittest.main()
