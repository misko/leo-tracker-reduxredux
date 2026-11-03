import unittest
import numpy as np
from orbit_model import patch_helpers


class PatchTests(unittest.TestCase):
    def test_slots_preserve_original_and_observations(self):
        p=np.zeros((2,2,3,3));v=p.copy();y=np.array([1.,2.,3.])
        doc=dict(session_id='s',tracks=[dict(track_id='t',candidate_position_km=p,candidate_velocity_km_s=v,y=y)])
        patch=dict(session_id='s',timing_grid_s=[0,1],tracks=[dict(index=0,track_id='t',slots_key='s',position_key='p',velocity_key='v')])
        out=patch_helpers.apply_arrays(doc,patch,dict(s=np.array([1]),p=np.ones((1,2,3,3)),v=np.ones((1,2,3,3))*2),[0,1])
        self.assertFalse(p.any());self.assertFalse(v.any())
        np.testing.assert_array_equal(out['tracks'][0]['candidate_position_km'][0],p[0])
        self.assertIs(out['tracks'][0]['y'],y)
        self.assertEqual(out['tracks'][0]['candidate_position_km'][1,0,0,0],1.)
