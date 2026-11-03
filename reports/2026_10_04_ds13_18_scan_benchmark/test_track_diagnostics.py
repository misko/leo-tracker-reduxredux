import unittest
import numpy as np
from track_diagnostics import residual_statistics


class ResidualTests(unittest.TestCase):
    def test_linear_term_removed_without_curvature(self):
        t=np.arange(100.)
        noise=np.sin(t*2*np.pi/5)
        s=residual_statistics(t,30+2*t+noise,np.ones(100))
        self.assertAlmostEqual(s['pooled_slope_hz_s'],2.,places=2)
        self.assertLess(s['linear_rms_hz'],1.)
        self.assertLess(s['curvature_ratio'],1.01)

    def test_quadratic_structure_and_centering(self):
        t=np.arange(100.)
        s=residual_statistics(t,.1*(t-50)**2+np.sin(t),np.ones(100))
        self.assertGreater(s['curvature_ratio'],20.)
        self.assertAlmostEqual(s['quadratic_coefficient_hz_s2'],.1,places=3)

    def test_short_degenerate_track_is_not_scored(self):
        self.assertIsNone(residual_statistics([1,1,1],[1,2,3],[1,1,1]))
