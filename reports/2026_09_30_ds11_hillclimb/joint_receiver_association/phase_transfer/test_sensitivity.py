import unittest
import numpy as np
from sensitivity import coefficients


class SensitivityTests(unittest.TestCase):
    def test_curvature_projection_rejects_clock_offset_and_slope(self):
        t=np.array([0.,.7,1.,1.4,2.3,3.1,4.])
        mask=np.array([True,True,False,True,True,False,True])
        weights=coefficients(t,mask)
        self.assertAlmostEqual(float(weights@(3000+70*t[mask]+.17*t[mask]**2)),.17,places=9)
        self.assertAlmostEqual(float(weights@np.ones(mask.sum())),0.,places=12)
        self.assertAlmostEqual(float(weights@t[mask]),0.,places=12)
