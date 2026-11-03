import unittest
import numpy as np
from core import project
class ProjectionTests(unittest.TestCase):
    def test_exact_alias_and_orthogonal_height(self):
        a=np.eye(4)[:,:3]
        result=project(a,a@np.array([2.,-3.,4.]),np.ones(4))
        np.testing.assert_allclose(result['compensation_per_km_height'],[2,-3,4])
        self.assertAlmostEqual(result['retained_height_information_fraction'],0)
        self.assertAlmostEqual(project(a,np.array([0,0,0,1.]),np.ones(4))['retained_height_information_fraction'],1)
    def test_global_weight_scaling(self):
        rng=np.random.default_rng(42);a=rng.normal(size=(30,3));h=rng.normal(size=30);w=rng.uniform(.1,1,30)
        p=project(a,h,w);q=project(a,h,100*w)
        np.testing.assert_allclose(p['compensation_per_km_height'],q['compensation_per_km_height'])
        self.assertAlmostEqual(p['retained_height_information_fraction'],q['retained_height_information_fraction'])
