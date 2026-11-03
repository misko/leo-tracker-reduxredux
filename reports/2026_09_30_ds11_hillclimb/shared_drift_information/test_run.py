import unittest
import numpy as np
from run import project,retention


class InformationTests(unittest.TestCase):
    def test_confounded_and_orthogonal_nuisance(self):
        jac=np.eye(6)[:,:3]
        np.testing.assert_allclose(retention(jac,np.eye(6)[:,3:4])['eigenvalues'],[1,1],atol=1e-12)
        np.testing.assert_allclose(retention(jac,jac[:,:1])['eigenvalues'],[0,1],atol=1e-12)
        np.testing.assert_allclose(retention(jac,jac[:,:2])['eigenvalues'],[0,0],atol=1e-12)

    def test_nuisance_scaling_duplicates_and_empty(self):
        rng=np.random.default_rng(1);a=rng.normal(size=(20,3));z=rng.normal(size=(20,2))
        p,rank=project(a,z);q,other=project(a,np.column_stack((z*7,z)))
        self.assertEqual(rank,other);np.testing.assert_allclose(p,q,atol=1e-12)
        np.testing.assert_array_equal(project(a,np.zeros((20,0)))[0],a)
        self.assertLess(np.linalg.norm(z.T@p),1e-10)
