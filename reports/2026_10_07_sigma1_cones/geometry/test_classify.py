import unittest
import numpy as np
from classify import labels

class GeometryTests(unittest.TestCase):
    def test_zenith_is_front_for_both_receivers(self):
        for rx in (0,1):
            got=labels([0,0,1],rx);self.assertFalse(got['opposite_east_west']);self.assertFalse(got['behind_nominal_boresight']);self.assertAlmostEqual(got['nominal_boresight_angle_deg'],20.)
    def test_high_east_is_opposite_rx0_but_front_facing(self):
        got=labels([np.cos(np.radians(80)),0,np.sin(np.radians(80))],0)
        self.assertTrue(got['opposite_east_west']);self.assertFalse(got['behind_nominal_boresight']);self.assertAlmostEqual(got['nominal_boresight_angle_deg'],30.)
    def test_low_east_is_behind_rx0(self):
        got=labels([np.cos(np.radians(10)),0,np.sin(np.radians(10))],0)
        self.assertTrue(got['opposite_east_west']);self.assertTrue(got['behind_nominal_boresight'])

if __name__=='__main__':unittest.main()
