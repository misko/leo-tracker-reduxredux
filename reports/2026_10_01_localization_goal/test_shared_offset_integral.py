"""Probability identities and challenging narrow/distant offset modes."""
import unittest

import numpy as np

from shared_offset_integral import integrate


class IntegralTests(unittest.TestCase):
    def test_normalization_and_single_group_identity(self):
        groups = [dict(period_hz=250000., residuals_hz=[100., -120000.])]
        null = integrate(groups*3, 50., 11., 40., 0., 16)
        self.assertLess(abs(null['shared']), 1e-8)
        self.assertLess(abs(null['independent']), 1e-8)
        one = integrate(groups, 50., 11., 40., .94, 16)
        self.assertAlmostEqual(one['shared'], one['independent'], places=12)

    def test_shared_offset_rewards_coherent_residuals(self):
        consistent = [dict(period_hz=250000., residuals_hz=[100.])]*8
        inconsistent = [dict(period_hz=250000., residuals_hz=[v]) for v in [100., -100.]*4]
        a = integrate(consistent, 80., 11., 20., .94, 16)
        b = integrate(inconsistent, 80., 11., 20., .94, 16)
        self.assertAlmostEqual(a['independent'], b['independent'], places=8)
        self.assertGreater(a['shared'], b['shared'])

    def test_narrow_distant_mode_refinement(self):
        groups = [dict(period_hz=250000., residuals_hz=[x, -85000.]) for x in [1000., 1001., 999.]*5]
        low = integrate(groups, 500., 11., 10., .98, 16)
        high = integrate(groups, 500., 11., 10., .98, 32)
        self.assertLess(abs(low['shared']-high['shared']), 1e-5)
        self.assertLess(abs(high['prior_mass']-1), 1e-8)
        self.assertTrue(np.isfinite(high['shared']))


if __name__ == '__main__':
    unittest.main()
