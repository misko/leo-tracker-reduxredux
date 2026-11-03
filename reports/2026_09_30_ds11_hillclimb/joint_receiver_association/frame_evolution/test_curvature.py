import unittest
import numpy as np
from curvature import curvature


class CurvatureTests(unittest.TestCase):
    def test_training_curvature_and_held_isolation(self):
        points=[dict(frame_time_s=float(t),phase_us=float((1200+12*t-.15*t*t)%(1e6/750)),range_delay_us=float(3100+20*t+.18*t*t),training=i%3!=1) for i,t in enumerate(np.linspace(0,10,51))]
        result=curvature(points,1e6/750)
        self.assertTrue(result['qualified'])
        self.assertAlmostEqual(result['phase_curvature_us_per_s2'],-.15,places=8)
        self.assertAlmostEqual(result['range_curvature_us_per_s2'],.18,places=8)
        self.assertLess(result['held_median_absolute_us'],1e-8)
        changed=[dict(p,phase_us=p['phase_us']+(0 if p['training'] else 100)) for p in points]
        other=curvature(changed,1e6/750)
        self.assertEqual(result['phase_curvature_us_per_s2'],other['phase_curvature_us_per_s2'])
        self.assertGreater(other['held_median_absolute_us'],99.)
