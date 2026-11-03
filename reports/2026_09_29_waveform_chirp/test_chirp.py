import unittest
import numpy as np
from chirp import basis, fit, error, objective, TRAIN


class ChirpTests(unittest.TestCase):
    def test_recovery_and_held_isolation(self):
        p=np.array([137.,-3000.])
        rng=np.random.default_rng(8)
        gains=rng.normal(size=(10,3))+1j*rng.normal(size=(10,3))
        values=gains[:,None,:]*np.exp(2j*np.pi*(basis(np.arange(10),np.arange(300))@p))[:,:,None]
        result=fit(values)
        self.assertTrue(result['qualified'])
        self.assertAlmostEqual(result['linear_hz'],p[0],places=2)
        self.assertAlmostEqual(result['rate_hz_s'],p[1],places=1)
        self.assertLess(error(values[9],9,result['linear_hz'],result['rate_hz_s']),1e-10)
        changed=values.copy();changed[8:]*=17j
        self.assertEqual(fit(changed),result)

    def test_gradient(self):
        rng=np.random.default_rng(4)
        y=rng.normal(size=(8,200,3))+1j*rng.normal(size=(8,200,3))
        b=basis(np.arange(8),TRAIN);p=np.array([.1,-.1])
        _,g=objective(p,y,b,200.)
        numeric=[]
        for delta in np.eye(2)*1e-6:
            numeric.append((objective(p+delta,y,b,200.)[0]-objective(p-delta,y,b,200.)[0])/2e-6)
        np.testing.assert_allclose(g,numeric,atol=1e-8)
