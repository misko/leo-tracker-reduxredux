import unittest
import numpy as np
from run import patch
class PatchTests(unittest.TestCase):
    def test_preserve_inputs_masks_times_and_unpaired(self):
        t=dict(track_id='a',y=np.array([1.,2.]),mask=np.array([True,False]),times_s=[1,2])
        b=dict(t,track_id='b');doc=dict(tracks=[t,b]);p=patch(doc,{'a':[3.,4.]})
        np.testing.assert_array_equal(p['tracks'][0]['y'],[4,6])
        np.testing.assert_array_equal(t['y'],[1,2])
        np.testing.assert_array_equal(p['tracks'][1]['y'],b['y'])
        self.assertIs(p['tracks'][0]['mask'],t['mask'])
        self.assertIs(p['tracks'][0]['times_s'],t['times_s'])
    def test_bad_targets_and_shapes_rejected(self):
        doc=dict(tracks=[dict(track_id='a',y=np.zeros(2))])
        with self.assertRaises(AssertionError):patch(doc,{'z':[1,2]})
        with self.assertRaises(AssertionError):patch(doc,{'a':[1]})
if __name__=='__main__':unittest.main()
