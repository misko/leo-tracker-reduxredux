import unittest
import numpy as np
from mark import geometry_flags,mark_arrays

def frame(az,el):
    az,el=np.radians([az,el]);return np.array([[-np.sin(el)*np.sin(az),-np.sin(el)*np.cos(az),np.cos(el)],[np.cos(az),-np.sin(az),0],[np.cos(el)*np.sin(az),np.cos(el)*np.cos(az),np.sin(el)]])

class MarkTests(unittest.TestCase):
    def test_below_horizon_is_independent_and_broadcast_for_both_receivers(self):
        unit=np.array([[[np.sqrt(.99),0,-.1]],[[1.,0,0]]]);frames=np.array([frame(270,70),frame(90,70)]);theta=np.array([np.radians(40),np.radians(30),np.log(.3),0,0]);f=geometry_flags(unit,theta,frames)
        np.testing.assert_array_equal(f['below_horizon'],[[[True,True]],[[False,False]]])
        self.assertFalse(f['behind_nominal_boresight'][0,0,1])
    def test_hemisphere_front_and_cone_are_distinct(self):
        unit=np.array([[[np.cos(np.radians(80)),0,np.sin(np.radians(80))]]]);frames=np.array([frame(270,70),frame(90,70)]);theta=np.array([np.radians(40),np.radians(30),np.log(.3),0,0]);f=geometry_flags(unit,theta,frames)
        self.assertTrue(f['opposite_east_west'][0,0,0]);self.assertFalse(f['behind_nominal_boresight'][0,0,0]);self.assertFalse(f['outside_empirical_ellipse'][0,0,0]);self.assertTrue(f['nearer_other_receiver_axis'][0,0,0])
    def test_weighted_marks_use_responsibilities_not_window_counts(self):
        unit=np.array([[[1.,0,0]],[[0,0,1.]]]);frames=np.array([frame(270,70),frame(90,70)]);theta=np.array([np.radians(40),np.radians(30),np.log(.3),0,0]);rows=mark_arrays(unit,[123],[0,0],[[.2],[.8]],theta,frames,'test-receive-time')
        self.assertAlmostEqual(rows[0]['signal_mass'],1.);self.assertAlmostEqual(rows[0]['opposite_east_west_fraction'],.2);self.assertAlmostEqual(rows[0]['behind_nominal_boresight_fraction'],.2);self.assertIsNone(rows[1]['opposite_east_west_fraction'])

if __name__=='__main__':unittest.main()
