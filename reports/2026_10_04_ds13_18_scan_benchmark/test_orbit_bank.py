import unittest
from orbit_bank import observer_ecef


class ObserverTests(unittest.TestCase):
    def test_equator_axis_units(self):
        self.assertEqual(observer_ecef(0, 0), [6378.137, 0., 0.])
        self.assertAlmostEqual(observer_ecef(0, 90)[1], 6378.137)

    def test_polar_radius_and_altitude(self):
        self.assertAlmostEqual(observer_ecef(90, 0)[2], 6356.752314245179)
        self.assertAlmostEqual(observer_ecef(90, 0, .1)[2], 6356.852314245179)


if __name__ == '__main__':
    unittest.main()
