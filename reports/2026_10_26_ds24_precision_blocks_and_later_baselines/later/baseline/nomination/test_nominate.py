import unittest
import numpy as np
from nominate import local,nominate,physical_key


class NominationTests(unittest.TestCase):
    def test_exact_original_family_quartile_denominator(self):
        families=[dict(family=i,paired_score=10-i,has_eligible_owner=True) for i in range(5)]
        owners=[dict(owner=str(i),family=i,eligible=True,paired_score=10-i,receiver=0) for i in range(5)]
        owners[3]['receiver']=1
        target,control=nominate(families,owners)
        self.assertEqual(target['family'],0);self.assertEqual(control['family'],3)

    def test_missing_eligible_owner_not_replaced_by_partial(self):
        self.assertEqual(nominate([dict(family=4,paired_score=1,has_eligible_owner=False)],
            [dict(owner='partial',family=4,eligible=False)]),(None,None))

    def test_physical_probe_dedup_ignores_receiver_but_preserves_visit(self):
        p=dict(visit_index=3,probe_index=7,channel=4,window_start_counter=12345,actual_rf_hz=11.5e9)
        self.assertEqual(physical_key('rec','session',p,200000),physical_key('rec','session',dict(p,receiver_id=1),200000))
        self.assertNotEqual(physical_key('rec','session',p,200000),physical_key('rec','session',dict(p,visit_index=4),200000))

    def test_original_susceptibility_has_declared_RF_and_RMS_units(self):
        times=np.array([0.,1.,2.,3.]);q=np.full(4,1.2)
        basis=local.bias_basis(times,q)
        np.testing.assert_allclose(basis.T@basis/len(times),np.eye(3)*1.2**2,atol=1e-14)
        h=np.array([[1.,2.,3.,4.],[0.,1.,0.,1.]])/1000
        score,_,vector=local.susceptibility(h,np.array([1.,0.]),range(4),times,q)
        self.assertAlmostEqual(score,np.linalg.norm(vector));self.assertGreater(score,0)


if __name__=='__main__':unittest.main()
