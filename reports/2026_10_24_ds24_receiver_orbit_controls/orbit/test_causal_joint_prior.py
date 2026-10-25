"""Component-owned causal partition and covariance invariants."""
import unittest
import numpy as np

from causal_joint_prior import BLOCK_NS, safe_training, correlation_fit, SHRINKAGE


class CausalJointPriorTests(unittest.TestCase):
    def test_random_time_fold_still_excludes_future_and_shared_TLE_endpoints(self):
        rows = [
            dict(norad=1,validation_time_ns=BLOCK_NS+1,endpoints=['a','b','c']),
            dict(norad=2,validation_time_ns=BLOCK_NS+2,endpoints=['a','b','c']),
            dict(norad=3,validation_time_ns=2*BLOCK_NS+1,endpoints=['u','v','w']),
            dict(norad=4,validation_time_ns=4*BLOCK_NS+1,endpoints=['p','q','r'])]
        test = [dict(norad=1,validation_time_ns=3*BLOCK_NS+1,endpoints=['c','d','e'])]
        train,purged=safe_training(rows,test,'time_block',0,3,{1:0,2:1,3:1,4:1},{1:1,2:0,3:0,4:1})
        self.assertEqual([r['norad'] for r in train],[2])
        self.assertEqual(purged,1)

    def test_satellite_holdout_never_uses_any_record_of_held_satellite(self):
        rows=[dict(norad=1,validation_time_ns=1,endpoints=['a']),
              dict(norad=2,validation_time_ns=2,endpoints=['b'])]
        test=[dict(norad=1,validation_time_ns=BLOCK_NS+1,endpoints=['z'])]
        train,purged=safe_training(rows,test,'satellite',0,1,{1:0,2:1},{0:1,1:0})
        self.assertEqual([r['norad'] for r in train],[2])
        self.assertEqual(purged,0)

    def test_correlation_changes_no_marginal_variance_and_is_positive(self):
        rng=np.random.default_rng(20261025)
        z=rng.standard_t(3,size=(500,4))
        z[:,1]+=.7*z[:,0]
        proposed=(1-SHRINKAGE)*np.eye(4)+SHRINKAGE*correlation_fit(z)
        np.testing.assert_allclose(np.diag(proposed),np.ones(4),atol=1e-12)
        self.assertGreaterEqual(np.linalg.eigvalsh(proposed).min(),1-SHRINKAGE-1e-12)


if __name__=='__main__':
    unittest.main()
