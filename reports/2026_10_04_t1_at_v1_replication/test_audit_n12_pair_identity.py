import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from audit_n12_pair_identity import split_windows,fit_candidate,GRID,circular,ALIAS


class IdentityAuditTests(unittest.TestCase):
    def test_random_split_is_reproducible_and_stratified(self):
        rx=np.repeat([0,1],20);ch=np.tile(np.repeat([1,2],10),2)
        a=split_windows(rx,ch,12);b=split_windows(rx,ch,12)
        np.testing.assert_array_equal(a,b)
        for r in (0,1):
            for c in (1,2):
                m=(rx==r)&(ch==c)
                self.assertTrue(a[m].any());self.assertTrue((~a[m]).any())

    def test_test_values_cannot_change_fitted_timing(self):
        data=SimpleNamespace(numbers=np.array([1]),times=np.arange(6.))
        def pred(d,i,t,p):return np.arange(6)*100+t*1000,np.ones(6,bool)
        coarse=np.array([pred(data,0,t,None)[0] for t in GRID])[:,:,None]
        visible=np.ones(coarse.shape,bool);train=np.array([True]*3+[False]*3)
        observed=pred(data,0,1.234,None)[0]
        with patch('audit_n12_pair_identity.predict',pred):
            a=fit_candidate(data,0,observed,train,np.zeros(7),coarse,visible)
            changed=observed.copy();changed[~train]+=1000
            b=fit_candidate(data,0,changed,train,np.zeros(7),coarse,visible)
        self.assertAlmostEqual(a['timing_s'],1.234,places=5)
        self.assertAlmostEqual(a['timing_s'],b['timing_s'],places=8)
        self.assertGreater(b['test_rms_hz'],999.)

    def test_alias_distance(self):
        np.testing.assert_allclose(circular([ALIAS+10,-ALIAS-10]),[10,-10])


if __name__=='__main__':unittest.main()
