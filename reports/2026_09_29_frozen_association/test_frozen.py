import importlib.util
import unittest
from pathlib import Path

import numpy as np

from frozen_model import FrozenAssociation

path = Path(__file__).resolve().parents[1] / '2026_09_29_unassociated_trend/trend_mixture.py'
spec = importlib.util.spec_from_file_location('test_trend', path)
trend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trend)


class Engine:
    def __init__(self, doc, config):
        pass

    def prediction(self, track, x):
        t = np.arange(5.)
        return np.array([40*t + x[0]*t + x[1]*t*t + x[2]*t**3, -30*t + 2*x[0]*t - x[1]*t*t + x[2]*t**3]), np.array([True, True])


class FrozenTest(unittest.TestCase):
    def setUp(self):
        track = dict(mask=np.array([True, True, True, True, False]), times_s=np.arange(5.), y=np.array([0,42,79,125,166.]))
        self.original = trend.TrendMixturePosition([dict(tracks=[track])], {}, Engine, .2)
        self.donor = np.array([.1,.2,.3])
        self.frozen = FrozenAssociation(self.original, self.donor)

    def test_tangent_and_lower_bound(self):
        a, b = self.original.evaluate(self.donor), self.frozen.evaluate(self.donor)
        self.assertAlmostEqual(a['score'], b['score'], places=10)
        np.testing.assert_allclose(a['gradient'], b['gradient'], atol=1e-9)
        for x in ([2,1,0],[-2,-1,.5],[0,0,0]):
            self.assertLessEqual(self.frozen.evaluate(x)['score'], self.original.evaluate(x)['score'] + 1e-10)

    def test_gradient(self):
        x = np.array([2.,1.,.1])
        actual = self.frozen.evaluate(x)['gradient']
        for i in range(3):
            d = np.zeros(3); d[i] = 1e-5
            numerical = (self.frozen.evaluate(x+d, gradient=False)['score']-self.frozen.evaluate(x-d, gradient=False)['score'])/2e-5
            self.assertAlmostEqual(actual[i], numerical, places=6)


if __name__ == '__main__':
    unittest.main()
