import unittest
import numpy as np
from fixed_model import restrict


class FixedIdentityTests(unittest.TestCase):
    def test_restriction_preserves_observations_and_normalizer(self):
        states=np.arange(24.).reshape(2,1,4,3);y=np.arange(4.)
        doc=dict(tracks=[dict(track_id='t',candidate_position_km=states,candidate_velocity_km_s=states.copy(),y=y,catalogue_size=100)])
        out,mapping=restrict(doc,{'t':dict(candidate_norad=[11,22])},{'t':22})
        np.testing.assert_array_equal(out['tracks'][0]['candidate_position_km'],states[1:2])
        self.assertIs(out['tracks'][0]['y'],y)
        self.assertEqual(out['tracks'][0]['catalogue_size'],100)
        self.assertEqual(mapping['t']['candidate_norad'],[22])
        out['tracks'][0]['candidate_position_km'][:]=0
        self.assertEqual(states[1,0,0,0],12.)

    def test_missing_or_unavailable_label_is_explicit(self):
        doc=dict(tracks=[dict(track_id='t')])
        with self.assertRaises(ValueError):restrict(doc,{}, {})
        with self.assertRaises(ValueError):restrict(doc,{'t':dict(candidate_norad=[11])},{'t':22})
