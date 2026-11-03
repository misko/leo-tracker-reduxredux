import unittest
import numpy as np
from height_model import HeightStationary,baseline


class HeightTests(unittest.TestCase):
    def test_zero_replay_and_vertical_displacement(self):
        config=dict(geographic_prior_center_deg=[37.,-122.],timing_grid_s=[-1,0,1],receiver_height_m=0)
        rec,up=baseline.site(37.,-122.)
        pos=np.broadcast_to(rec+up*550+np.array([100.,20.,30.]),(1,3,4,3)).copy()
        vel=np.broadcast_to(np.array([2.,3.,4.]),pos.shape).copy()
        track=dict(candidate_position_km=pos,candidate_velocity_km_s=vel,mask=np.array([True,False,True,False]))
        original=baseline.Stationary({},config).prediction(track,[0,0,.1])
        zero=HeightStationary({},config).prediction(track,[0,0,.1])
        np.testing.assert_array_equal(original[0],zero[0]);np.testing.assert_array_equal(original[1],zero[1])
        elevated=HeightStationary({},dict(config,receiver_height_m=300)).prediction(track,[0,0,.1])[0]
        relative=pos[:,1]-(rec+.3*up)
        unit=relative/np.linalg.norm(relative,axis=-1)[...,None]
        expected=-baseline.REFERENCE_RF_HZ/baseline.LIGHT_KM_S*np.sum(unit*vel[:,1],axis=-1)
        np.testing.assert_allclose(elevated,expected,atol=1e-9)
        self.assertGreater(float(np.max(abs(elevated-zero[0]))),0)
