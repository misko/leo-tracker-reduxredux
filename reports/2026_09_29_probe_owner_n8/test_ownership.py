import unittest
import numpy as np
from ownership import resolve


def track(name,mask):
    n=len(mask)
    return dict(track_id=name,mask=np.array(mask),training_mask=np.array(mask),y=np.arange(n),measured_hz=np.arange(n),times_s=np.arange(n),candidate_position_km=np.arange(2*3*n*3).reshape(2,3,n,3),candidate_velocity_km_s=np.ones((2,3,n,3)))


class OwnershipTest(unittest.TestCase):
    def test_partial_history_survives_and_arrays_align(self):
        a=track('a',[True,True,True,False]);b=track('b',[True,True,True,False])
        qa=[dict(track_id='a',index=i,training=bool(a['mask'][i]),source_group_id=g) for i,g in enumerate(['x','a1','a2','a3'])]
        qb=[dict(track_id='b',index=i,training=bool(b['mask'][i]),source_group_id=g) for i,g in enumerate(['x','b1','b2','b3'])]
        out,ledger=resolve(dict(tracks=[b,a]),qa+qb)
        self.assertEqual(len(out['tracks']),2)
        np.testing.assert_array_equal(out['tracks'][0]['y'],[1,2,3])
        np.testing.assert_array_equal(out['tracks'][0]['candidate_position_km'],b['candidate_position_km'][:,:,1:,:])
        self.assertEqual(len(b['y']),4)
        self.assertEqual(ledger['retained_groups'],7)

    def test_support_loss_is_ledgered(self):
        a=track('a',[True,True,False]);b=track('b',[True,True,False])
        q=[dict(track_id=t['track_id'],index=i,training=bool(t['mask'][i]),source_group_id=str(i)) for t in [a,b] for i in range(3)]
        out,ledger=resolve(dict(tracks=[a,b]),q)
        self.assertEqual(len(out['tracks']),1)
        self.assertTrue(ledger['tracks'][1]['excluded'])


if __name__=='__main__':unittest.main()
