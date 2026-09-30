import unittest
from summarize import distance,percentile

class MetricTests(unittest.TestCase):
    def test_distance_identity_and_known_equator_arc(self):
        self.assertEqual(distance((0,0),(0,0)),0)
        self.assertAlmostEqual(distance((0,1),(0,0)),111195.0802335,places=5)
    def test_p90_linear_interpolation(self):
        self.assertEqual(percentile([0,100],.9),90)
