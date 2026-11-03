import unittest
import numpy as np
from model import MarginalModel


class Geometry:
    def prediction(self,track,x):
        return track['base']+np.einsum('cnk,k->cn',track['jac'],x),np.array([True,True])


class ModelTests(unittest.TestCase):
    def test_full_mixture_gradient_and_held_isolation(self):
        rng=np.random.default_rng(123)
        track=dict(y=rng.normal(0,70,12),mask=np.arange(12)<9,catalogue_size=20,
                   base=rng.normal(0,60,(2,12)),jac=rng.normal(0,10,(2,12,3)))
        model=MarginalModel(dict(tracks=[track]),{},geometry=Geometry());x=np.array([.1,.2,-.1])
        result=model.evaluate(x)
        for axis in range(3):
            d=np.eye(3)[axis]*1e-4
            finite=(model.evaluate(x+d,False)['score']-model.evaluate(x-d,False)['score'])/2e-4
            self.assertAlmostEqual(finite,result['gradient'][axis],places=6)
        track['y'][~track['mask']]+=1e6
        changed=model.evaluate(x)
        self.assertEqual(changed['score'],result['score'])
        np.testing.assert_array_equal(changed['gradient'],result['gradient'])

    def test_order_and_candidate_permutation(self):
        rng=np.random.default_rng(6)
        t=dict(y=rng.normal(0,80,10),mask=np.ones(10,dtype=bool),catalogue_size=40,
               base=rng.normal(0,70,(2,10)),jac=rng.normal(0,10,(2,10,3)))
        a=MarginalModel(dict(tracks=[t]),{},32,Geometry()).evaluate(np.zeros(3))
        t=dict(t,base=t['base'][::-1],jac=t['jac'][::-1])
        b=MarginalModel(dict(tracks=[t]),{},64,Geometry()).evaluate(np.zeros(3))
        self.assertAlmostEqual(a['score'],b['score'],places=8)
        np.testing.assert_allclose(a['gradient'],b['gradient'],atol=1e-8)
