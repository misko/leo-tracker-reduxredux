import itertools,unittest
import numpy as np
from shared_identity_search import select


def brute(cost,prior):
    best=float('inf');_,nt,nk=cost.shape
    for identities in itertools.product(range(nk),repeat=3):
        unique=sorted(set(identities))
        for times in itertools.product(range(nt),repeat=len(unique)):
            mapping=dict(zip(unique,times))
            value=sum(cost[g,mapping[k],k] for g,k in enumerate(identities))+sum(prior[t] for t in times)
            best=min(best,value)
    return best


class SearchTests(unittest.TestCase):
    def test_matches_exhaustive_assignments(self):
        rng=np.random.default_rng(834)
        for candidates in [1,2,4]:
            for _ in range(3):
                cost=rng.uniform(0,10,(3,3,candidates));prior=np.array([1.,0.,1.])
                self.assertAlmostEqual(select(cost,prior)['score'],brute(cost,prior),places=12)

    def test_reused_satellite_has_one_timing_and_one_prior(self):
        cost=np.array([[[0.],[100.]],[[100.],[0.]],[[0.],[100.]]])
        result=select(cost,np.array([2.,3.]))
        self.assertEqual(result['score'],102.)
        np.testing.assert_array_equal(result['timing_indices'],[0,0,0])

    def test_invisible_cells_are_not_selected(self):
        cost=np.ones((3,2,2));cost[:,:,0]=np.inf
        result=select(cost,np.array([1.,0.]))
        np.testing.assert_array_equal(result['candidate_indices'],[1,1,1])
        self.assertEqual(result['score'],3.)
        with self.assertRaises(ValueError):select(np.full((3,2,2),np.inf),np.zeros(2))


if __name__=='__main__':unittest.main()
