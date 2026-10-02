import unittest
import numpy as np
from trajectory_mixture import fit,predict,log_density

class MixtureTests(unittest.TestCase):
    def test_normalized_mixture_not_best_branch(self):
        value=log_density(np.array([0.]),np.array([[0.,10000.]]),np.array([.25,.75]),100.)[0]
        self.assertAlmostEqual(value,-np.log(100*np.sqrt(2*np.pi))+np.log(.25))
    def test_interleaved_curves_and_invariance(self):
        t=np.arange(40.);y=3*t+.2*t*t+np.where(np.arange(40)%2,1000.,-1000.)
        a=fit(t,y);b=fit(t+123,y+50000)
        self.assertEqual(a['status'],'mixture')
        np.testing.assert_allclose(predict(a,t,y),predict(b,t+123,y+50000),atol=1e-8)
        self.assertGreater(a['mixture_loglik'],a['single_loglik']+100)
    def test_insufficient_support_fallback(self):
        t=np.arange(8.);m=fit(t,t*t)
        self.assertEqual(m['status'],'insufficient_support')
        np.testing.assert_equal(predict(m,t,t*t),predict(m,t,t*t,single=True))

if __name__=='__main__':unittest.main()
