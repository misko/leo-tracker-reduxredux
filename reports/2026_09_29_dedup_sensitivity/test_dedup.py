import unittest
import numpy as np
from dedup import deduplicate


def track(name,times,values,mask):
    return dict(track_id=name,receiver_id=0,rf_hz=1e9,times_s=np.array(times),measured_hz=np.array(values),training_mask=np.array(mask),y=np.array(values),mask=np.array(mask),candidate_position_km=np.arange(2*3*len(times)*3).reshape(2,3,len(times),3),candidate_velocity_km_s=np.ones((2,3,len(times),3)))


class DedupTest(unittest.TestCase):
    def test_owner_alignment_and_original_preservation(self):
        a=track('a',[0,1,2,3],[1,2,3,4],[True,True,True,False])
        b=track('b',[1,4,5,6],[2,8,9,10],[True,True,True,False])
        doc=dict(tracks=[b,a])
        out,removed=deduplicate(doc)
        self.assertEqual(len(removed),1)
        self.assertEqual(removed[0]['owner'],'a')
        np.testing.assert_array_equal(out['tracks'][0]['y'],[8,9,10])
        np.testing.assert_array_equal(out['tracks'][0]['candidate_position_km'],b['candidate_position_km'][:,:,1:,:])
        self.assertEqual(len(b['y']),4)

    def test_cross_split_and_support_failure_explicit(self):
        a=track('a',[0,1,2],[1,2,3],[True,True,False])
        b=track('b',[0,3,4],[1,8,9],[False,True,True])
        with self.assertRaisesRegex(ValueError,'crosses'):
            deduplicate(dict(tracks=[a,b]))
        with self.assertRaisesRegex(ValueError,'support'):
            deduplicate(dict(tracks=[a,dict(a,track_id='b')]))


if __name__=='__main__':
    unittest.main()
