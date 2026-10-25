import unittest
import numpy as np

from dsx01_hierarchical_bound import hierarchical_bound
from family_score_detail import noise_gamma_by_group, prior_gamma_by_phase


class FamilyScoreTests(unittest.TestCase):
    def test_reconstructed_group_Gamma_costs_match_original_bound(self):
        rng=np.random.default_rng(983)
        groups=np.repeat(np.arange(3),[15,11,19])
        powers=np.array([.4,.8,1.])
        features=rng.normal(size=(len(groups),5))
        y=features@rng.normal(size=5)+rng.normal(size=len(groups))
        prior_groups=np.array([-1,0,1,-1,-1])
        result=hierarchical_bound(y,features,np.ones(len(y)),groups,
            prior_groups=prior_groups,powers=powers,prior_nu=5.)
        noise=noise_gamma_by_group(result['noise_precision'],np.bincount(groups),powers)
        phase=prior_gamma_by_phase(result['coefficient_prior_precision'][[1,2]],5.)
        self.assertAlmostEqual(noise.sum(),result['noise_gamma_cost'])
        self.assertAlmostEqual(phase.sum(),result['prior_gamma_cost'])
        inactive=noise_gamma_by_group(np.r_[result['noise_precision'],0],np.r_[np.bincount(groups),0],np.r_[powers,1.])
        self.assertEqual(inactive[-1],0)


if __name__=='__main__':unittest.main()
