import unittest
import numpy as np
from scipy.special import logsumexp
from doppler_pilot import candidate_factor
class CandidateFactorTests(unittest.TestCase):
    def test_identity_is_shared_and_order_is_physical(self):
        a=np.log([.9,.1]);b=np.log([.8,.2])
        result=candidate_factor(a,[10,20],b,[20,10],100)
        self.assertAlmostEqual(result,np.log((.9*.2+.1*.8)/100))
        self.assertNotAlmostEqual(result,float(logsumexp(a)+logsumexp(b)-2*np.log(100)))
    def test_disjoint_support_is_impossible_pair_not_deleted_single(self):
        self.assertEqual(candidate_factor(np.array([0.]),[1],np.array([0.]),[2],10),-np.inf)
        self.assertAlmostEqual(candidate_factor(np.array([0.]),[1],catalogue_size=10),-np.log(10))
